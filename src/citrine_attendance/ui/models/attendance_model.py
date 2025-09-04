# src/citrine_attendance/ui/models/attendance_model.py
import logging
from typing import List, Optional

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex, QVariant
from PyQt6.QtGui import QColor

from ...services.attendance_service import attendance_service, AttendanceServiceError
from ...database import Attendance
from ...date_utils import format_date_for_display, get_jalali_month_range
from ...utils.time_utils import minutes_to_hhmm
from ...locale import _

class AttendanceTableModel(QAbstractTableModel):
    """Custom model to display and manage attendance data in a QTableView."""

    EMPLOYEE_NAME_COL = 0
    DATE_COL = 1
    TIME_IN_COL = 2
    TIME_OUT_COL = 3
    LEAVE_COL = 4
    # HEROIC FIX: Added new columns for monthly leave tracking
    USED_LEAVE_MONTH_COL = 5
    REMAINING_LEAVE_MONTH_COL = 6
    TARDINESS_COL = 7
    MAIN_WORK_COL = 8
    OVERTIME_COL = 9
    LAUNCH_TIME_COL = 10
    TOTAL_DURATION_COL = 11
    STATUS_COL = 12
    NOTE_COL = 13

    def __init__(self, config):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.attendance_data: List[Attendance] = []
        self.employee_cache = {}
        self.monthly_leave_cache = {} # Cache for monthly leave data
        self.filters = {}
        self.COLUMN_HEADERS = [
            _("attendance_header_employee"),
            _("attendance_header_date"),
            _("attendance_header_time_in"),
            _("attendance_header_time_out"),
            _("attendance_header_leave"),
            _("attendance_header_used_leave"), # Use translation key
            _("attendance_header_remaining_leave"), # Use translation key
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
            attendance_service.STATUS_ON_LEAVE: _("attendance_status_on_leave"),
        }

    def load_data(self):
        """Load attendance data and pre-calculate monthly leave."""
        try:
            # Clear caches
            self.employee_cache.clear()
            self.monthly_leave_cache.clear()
            
            records = attendance_service.get_attendance_records(**self.filters)

            # Populate employee cache
            self.employee_cache = {
                r.employee_id: {
                    "name": f"{r.employee.first_name} {r.employee.last_name}".strip() or r.employee.email,
                    "allowance": r.employee.monthly_leave_allowance_minutes
                }
                for r in records if r.employee
            }

            # HEROIC FIX: Pre-calculate monthly leave totals using the correct Jalali month range
            db_session = attendance_service._get_session()
            try:
                for record in records:
                    start_of_period, _ = get_jalali_month_range(record.date)
                    cache_key = (record.employee_id, start_of_period)
                    
                    if cache_key not in self.monthly_leave_cache:
                        used_leave = attendance_service.get_monthly_leave_taken(record.employee_id, record.date, db_session)
                        self.monthly_leave_cache[cache_key] = used_leave
            finally:
                db_session.close()

            search_text = self.filters.get('search_text', '').lower()
            if search_text:
                records = [
                    r for r in records if
                    search_text in self.employee_cache.get(r.employee_id, {}).get("name", "").lower() or
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
        if not index.isValid() or index.row() >= len(self.attendance_data):
            return QVariant()

        record = self.attendance_data[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.EMPLOYEE_NAME_COL:
                return self.employee_cache.get(record.employee_id, {}).get("name", f"ID:{record.employee_id}")
            elif col == self.DATE_COL:
                return format_date_for_display(record.date, self.config.settings.get("date_format", "both"))
            elif col == self.TIME_IN_COL:
                return record.time_in.strftime("%H:%M") if record.time_in else ""
            elif col == self.TIME_OUT_COL:
                return record.time_out.strftime("%H:%M") if record.time_out else ""
            elif col == self.LEAVE_COL:
                return minutes_to_hhmm(record.leave_duration_minutes)
            # HEROIC FIX: Display calculated monthly leave data from the corrected cache
            elif col == self.USED_LEAVE_MONTH_COL:
                start_of_period, _ = get_jalali_month_range(record.date)
                used_leave = self.monthly_leave_cache.get((record.employee_id, start_of_period), 0)
                return minutes_to_hhmm(used_leave)
            elif col == self.REMAINING_LEAVE_MONTH_COL:
                allowance = self.employee_cache.get(record.employee_id, {}).get("allowance", 0)
                if allowance > 0:
                    start_of_period, _ = get_jalali_month_range(record.date)
                    used_leave = self.monthly_leave_cache.get((record.employee_id, start_of_period), 0)
                    remaining = max(0, allowance - used_leave)
                    return minutes_to_hhmm(remaining)
                return "N/A" # Not applicable if no allowance is set
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
            numeric_cols = [
                self.LEAVE_COL, self.USED_LEAVE_MONTH_COL, self.REMAINING_LEAVE_MONTH_COL,
                self.TARDINESS_COL, self.MAIN_WORK_COL, self.OVERTIME_COL,
                self.LAUNCH_TIME_COL, self.TOTAL_DURATION_COL
            ]
            if col in numeric_cols:
                return Qt.AlignmentFlag.AlignCenter
        
        elif role == Qt.ItemDataRole.BackgroundRole:
            if record.status == 'absent':
                return QColor("#641E16")
            if record.status == 'on_leave':
                return QColor("#7E5109")

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
        self.load_data()

    def set_filters(self, **kwargs):
        self.filters = kwargs
        self.refresh()

    def add_attendance_record(self, record_data: dict):
        try:
            attendance_service.add_manual_attendance(**record_data)
            self.refresh()
        except Exception as e:
            self.logger.error(f"Error adding record via model: {e}", exc_info=True)
            raise

    def update_attendance_record(self, record_id: int, record_data: dict):
        try:
            attendance_service.update_attendance(attendance_id=record_id, **record_data)
            self.refresh()
        except Exception as e:
            self.logger.error(f"Error updating record via model: {e}", exc_info=True)
            raise