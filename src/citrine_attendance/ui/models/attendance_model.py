# src/citrine_attendance/ui/models/attendance_model.py
import logging
from typing import List, Optional

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex, QVariant

from ...services.attendance_service import attendance_service, AttendanceServiceError
from ...database import Attendance
from ...date_utils import format_date_for_display
from ...utils.time_utils import minutes_to_hhmm
from ...locale import _

class AttendanceTableModel(QAbstractTableModel):
    """Custom model to display and manage attendance data in a QTableView."""

    # --- Updated Column Definitions ---
    EMPLOYEE_NAME_COL = 0
    DATE_COL = 1
    TIME_IN_COL = 2
    TIME_OUT_COL = 3
    LEAVE_COL = 4  # New column for leave
    TARDINESS_COL = 5
    MAIN_WORK_COL = 6
    OVERTIME_COL = 7
    LAUNCH_TIME_COL = 8
    TOTAL_DURATION_COL = 9
    STATUS_COL = 10
    NOTE_COL = 11

    def __init__(self, config):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.attendance_data: List[Attendance] = []
        self.employee_cache = {}
        self.filters = {}
        # --- Updated Column Headers ---
        self.COLUMN_HEADERS = [
            _("attendance_header_employee"),
            _("attendance_header_date"),
            _("attendance_header_time_in"),
            _("attendance_header_time_out"),
            _("attendance_header_leave"),  # New header
            _("attendance_header_tardiness"),
            _("attendance_header_main_work"),
            _("attendance_header_overtime"),
            _("attendance_header_launch"),
            _("attendance_header_total_duration"),
            _("attendance_header_status"),
            _("attendance_header_notes")
        ]
        self.COLUMN_COUNT = len(self.COLUMN_HEADERS)

        # --- Updated Status Display ---
        self.STATUS_DISPLAY = {
            attendance_service.STATUS_PRESENT: _("attendance_filter_present"),
            attendance_service.STATUS_ABSENT: _("attendance_filter_absent"),
            attendance_service.STATUS_ON_LEAVE: _("attendance_status_on_leave"),
        }

    def load_data(self):
        """Load attendance data based on current filters."""
        try:
            records = attendance_service.get_attendance_records(**self.filters)

            self.employee_cache = {
                r.employee_id: f"{r.employee.first_name} {r.employee.last_name}".strip() or r.employee.email
                for r in records if r.employee
            }

            search_text = self.filters.get('search_text', '').lower()
            if search_text:
                records = [
                    r for r in records if
                    search_text in self.employee_cache.get(r.employee_id, "").lower() or
                    search_text in (r.note or "").lower()
                ]

            self.beginResetModel()
            self.attendance_data = records
            self.endResetModel()
            self.logger.debug(f"Loaded {len(self.attendance_data)} records into model.")

        except Exception as e:
            self.logger.error(f"Error loading attendance data: {e}", exc_info=True)
            self.beginResetModel()
            self.attendance_data = []
            self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self.attendance_data)

    def columnCount(self, parent=QModelIndex()):
        return self.COLUMN_COUNT

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Return data for a specific cell."""
        if not index.isValid() or index.row() >= len(self.attendance_data):
            return QVariant()

        record = self.attendance_data[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.EMPLOYEE_NAME_COL:
                return self.employee_cache.get(record.employee_id, f"ID:{record.employee_id}")
            elif col == self.DATE_COL:
                return format_date_for_display(record.date, self.config.settings.get("date_format", "both"))
            elif col == self.TIME_IN_COL:
                return record.time_in.strftime("%H:%M") if record.time_in else ""
            elif col == self.TIME_OUT_COL:
                return record.time_out.strftime("%H:%M") if record.time_out else ""
            elif col == self.LEAVE_COL:
                return minutes_to_hhmm(record.leave_duration_minutes)
            elif col == self.TARDINESS_COL:
                return minutes_to_hhmm(record.tardiness_minutes)
            elif col == self.MAIN_WORK_COL:
                return minutes_to_hhmm(record.main_work_minutes)
            elif col == self.OVERTIME_COL:
                return minutes_to_hhmm(record.overtime_minutes)
            elif col == self.LAUNCH_TIME_COL:
                return minutes_to_hhmm(record.launch_duration_minutes)
            elif col == self.TOTAL_DURATION_COL:
                return minutes_to_hhmm(record.duration_minutes)
            elif col == self.STATUS_COL:
                return self.STATUS_DISPLAY.get(record.status, record.status)
            elif col == self.NOTE_COL:
                return record.note or ""

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col > self.TIME_OUT_COL and col < self.STATUS_COL:
                return Qt.AlignmentFlag.AlignCenter

        return QVariant()

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.COLUMN_HEADERS[section]
        return QVariant()

    def get_attendance_at_row(self, row: int) -> Optional[Attendance]:
        if 0 <= row < len(self.attendance_data):
            return self.attendance_data[row]
        return None

    def refresh(self):
        """Reloads all data from the database based on current filters."""
        self.load_data()

    def set_filters(self, **kwargs):
        """Sets the filters and triggers a data refresh."""
        self.filters = kwargs
        self.refresh()

    def add_attendance_record(self, record_data: dict):
        """Adds a new record via the service and refreshes the model."""
        try:
            attendance_service.add_manual_attendance(**record_data)
            self.refresh()
        except Exception as e:
            self.logger.error(f"Error adding record via model: {e}", exc_info=True)
            raise  # Re-raise to be caught by the UI

    def update_attendance_record(self, record_id: int, record_data: dict):
        """Updates an existing record via the service and refreshes the model."""
        try:
            attendance_service.update_attendance(attendance_id=record_id, **record_data)
            self.refresh()
        except Exception as e:
            self.logger.error(f"Error updating record via model: {e}", exc_info=True)
            raise  # Re-raise to be caught by the UI