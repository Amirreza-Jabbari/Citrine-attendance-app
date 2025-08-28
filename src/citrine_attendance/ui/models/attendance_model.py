# src/citrine_attendance/ui/models/attendance_model.py
import logging
from datetime import date, time, datetime
from typing import List, Optional

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex, QVariant
from PyQt6.QtGui import QFont

from ...services.attendance_service import attendance_service, AttendanceServiceError
from ...database import get_db_session, Attendance, Employee
from ...date_utils import format_date_for_display
from ...utils.time_utils import minutes_to_hhmm # <-- Import the new utility
from ...locale import _ # <-- Import the translator function

class AttendanceTableModel(QAbstractTableModel):
    """Custom model to display and manage attendance data in a QTableView."""

    # --- Column Definitions ---
    EMPLOYEE_NAME_COL = 0
    DATE_COL = 1
    TIME_IN_COL = 2
    TIME_OUT_COL = 3
    TARDINESS_COL = 4
    MAIN_WORK_COL = 5
    OVERTIME_COL = 6
    LAUNCH_TIME_COL = 7
    TOTAL_DURATION_COL = 8
    STATUS_COL = 9
    NOTE_COL = 10

    def __init__(self, config):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.attendance_data: List[Attendance] = []
        self.employee_cache = {}
        self.filters = {}
        # --- Translate Column Headers ---
        self.COLUMN_HEADERS = [
            _("attendance_header_employee"),
            _("attendance_header_date"),
            _("attendance_header_time_in"),
            _("attendance_header_time_out"),
            _("attendance_header_tardiness"),
            _("attendance_header_main_work"),
            _("attendance_header_overtime"),
            _("attendance_header_launch"),
            _("attendance_header_total_duration"),
            _("attendance_header_status"),
            _("attendance_header_notes")
        ]
        self.COLUMN_COUNT = len(self.COLUMN_HEADERS)

        self.STATUS_DISPLAY = {
            attendance_service.STATUS_PRESENT: _("attendance_filter_present"),
            attendance_service.STATUS_ABSENT: _("attendance_filter_absent"),
        }
        self.STATUS_DISPLAY_INVERSE = {v: k for k, v in self.STATUS_DISPLAY.items()}


    def load_data(self):
        """Load attendance data based on current filters."""
        try:
            # The service now handles eager loading of employees
            records = attendance_service.get_attendance_records(**self.filters)

            # Populate cache from the loaded records
            self.employee_cache = {
                r.employee_id: f"{r.employee.first_name} {r.employee.last_name}".strip() or r.employee.email
                for r in records if r.employee
            }

            # Simple text search (client-side filtering after DB query)
            search_text = self.filters.get('search_text', '').lower()
            if search_text:
                filtered_records = []
                for r in records:
                    emp_name = self.employee_cache.get(r.employee_id, "").lower()
                    note = (r.note or "").lower()
                    if search_text in emp_name or search_text in note:
                        filtered_records.append(r)
                records = filtered_records

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
            # --- Use the new HH:MM formatter for all time duration columns ---
            elif col == self.TARDINESS_COL:
                return minutes_to_hhmm(record.tardiness_minutes)
            elif col == self.MAIN_WORK_COL:
                return minutes_to_hhmm(record.main_work_minutes)
            elif col == self.OVERTIME_COL:
                return minutes_to_hhmm(record.overtime_minutes)
            # --- CORRECTED: Use the correct column name from the database model ---
            elif col == self.LAUNCH_TIME_COL:
                # The database now stores launch_duration_minutes, so we use that
                return minutes_to_hhmm(record.launch_duration_minutes)
            elif col == self.TOTAL_DURATION_COL:
                return minutes_to_hhmm(record.duration_minutes)
            elif col == self.STATUS_COL:
                return self.STATUS_DISPLAY.get(record.status, record.status)
            elif col == self.NOTE_COL:
                return record.note or ""

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in [self.TIME_IN_COL, self.TIME_OUT_COL, self.TARDINESS_COL,
                       self.MAIN_WORK_COL, self.OVERTIME_COL, self.LAUNCH_TIME_COL, self.TOTAL_DURATION_COL]:
                return Qt.AlignmentFlag.AlignCenter
        
        elif role == Qt.ItemDataRole.ToolTipRole:
            if col == self.LAUNCH_TIME_COL:
                start = record.launch_start.strftime('%H:%M') if record.launch_start else "N/A"
                end = record.launch_end.strftime('%H:%M') if record.launch_end else "N/A"
                return f"Launch: {start} - {end}"

        return QVariant()

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        """Handle inline editing."""
        if not (index.isValid() and role == Qt.ItemDataRole.EditRole):
            return False

        record = self.attendance_data[index.row()]
        col = index.column()
        update_kwargs = {}

        try:
            if col == self.TIME_IN_COL:
                update_kwargs['time_in'] = datetime.strptime(value, "%H:%M").time() if value else None
            elif col == self.TIME_OUT_COL:
                update_kwargs['time_out'] = datetime.strptime(value, "%H:%M").time() if value else None
            elif col == self.NOTE_COL:
                update_kwargs['note'] = value
            else:
                return False # Column is not editable

            updated_record = attendance_service.update_attendance(record.id, **update_kwargs)
            self.attendance_data[index.row()] = updated_record
            self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), self.COLUMN_COUNT - 1))
            return True
        except Exception as e:
            self.logger.error(f"Error updating record via model: {e}", exc_info=True)
            return False

    def flags(self, index):
        """Set item flags."""
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        # Allow editing times and notes
        if index.column() in [self.TIME_IN_COL, self.TIME_OUT_COL, self.NOTE_COL]:
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.COLUMN_HEADERS[section]
        return QVariant()

    def get_attendance_at_row(self, row: int) -> Optional[Attendance]:
        if 0 <= row < len(self.attendance_data):
            return self.attendance_data[row]
        return None

    def refresh(self):
        self.load_data()

    def set_filters(self, **kwargs):
        self.filters = kwargs
        self.refresh()

    def get_aggregates(self):
        """Calculate aggregate values for the current dataset."""
        aggregates = {
            "total_duration": 0, "total_main_work": 0, "total_overtime": 0, "total_tardiness": 0,
            "present_days": 0, "absent_days": 0
        }
        for record in self.attendance_data:
            aggregates["total_duration"] += record.duration_minutes or 0
            aggregates["total_main_work"] += record.main_work_minutes or 0
            aggregates["total_overtime"] += record.overtime_minutes or 0
            aggregates["total_tardiness"] += record.tardiness_minutes or 0
            if record.status == attendance_service.STATUS_PRESENT:
                aggregates["present_days"] += 1
            elif record.status == attendance_service.STATUS_ABSENT:
                aggregates["absent_days"] += 1
        return aggregates

    def add_attendance_record(self, record_data: dict):
        """Adds a new record via the service and refreshes the model."""
        try:
            attendance_service.add_manual_attendance(**record_data)
            self.refresh()
        except Exception as e:
            self.logger.error(f"Error adding record via model: {e}", exc_info=True)
            raise

    def remove_attendance_record(self, record_id: int):
        """Removes a record via the service and refreshes the model."""
        try:
            attendance_service.delete_attendance(record_id)
            self.refresh()
        except Exception as e:
            self.logger.error(f"Error removing record via model: {e}", exc_info=True)
            raise