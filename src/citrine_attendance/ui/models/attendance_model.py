# src/citrine_attendance/ui/models/attendance_model.py
import logging
from typing import List, Optional

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex, QVariant
from PyQt6.QtGui import QColor

from ...services.attendance_service import attendance_service
from ...services.employee_service import employee_service
from ...database import Attendance, get_db_session
from ...date_utils import format_date_for_display, get_jalali_month_range
from ...utils.time_utils import minutes_to_hhmm
from ...locale import _

class AttendanceTableModel(QAbstractTableModel):
    """Custom model to display and manage attendance data in a QTableView."""

    EMPLOYEE_NAME_COL = 0
    DATE_COL = 1
    TIME_IN_COL = 2
    TIME_OUT_COL = 3
    TIME_IN_2_COL = 4 # HEROIC IMPLEMENTATION
    TIME_OUT_2_COL = 5 # HEROIC IMPLEMENTATION
    LEAVE_COL = 6
    USED_LEAVE_MONTH_COL = 7
    REMAINING_LEAVE_MONTH_COL = 8
    TARDINESS_COL = 9
    EARLY_DEPARTURE_COL = 10 # HEROIC
    MAIN_WORK_COL = 11
    OVERTIME_COL = 12
    LAUNCH_TIME_COL = 13
    TOTAL_DURATION_COL = 14
    STATUS_COL = 15
    NOTE_COL = 16

    def __init__(self, config):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.attendance_data: List[Attendance] = []
        self.employee_cache = {}
        self.monthly_leave_cache = {}
        self.filters = {}
        self.column_totals = {}
        self.COLUMN_HEADERS = [
            _("attendance_header_employee"), _("attendance_header_date"),
            _("attendance_header_time_in"), _("attendance_header_time_out"),
            _("attendance_header_time_in_2"), _("attendance_header_time_out_2"), # HEROIC IMPLEMENTATION
            _("attendance_header_leave"), _("attendance_header_used_leave"),
            _("attendance_header_remaining_leave"), _("attendance_header_tardiness"),
            _("attendance_header_early_departure"), # HEROIC
            _("attendance_header_main_work"), _("attendance_header_overtime"),
            _("attendance_header_launch"), _("attendance_header_total_duration"),
            _("attendance_header_status"), _("attendance_header_notes")
        ]
        self.COLUMN_COUNT = len(self.COLUMN_HEADERS)
        self.STATUS_DISPLAY = {
            attendance_service.STATUS_PRESENT: _("attendance_filter_present"),
            attendance_service.STATUS_ABSENT: _("attendance_filter_absent"),
            attendance_service.STATUS_ON_LEAVE: _("attendance_status_on_leave"),
            attendance_service.STATUS_PARTIAL: _("attendance_status_partial"),
        }

    def load_data(self):
        """Load attendance data and pre-calculate caches for display."""
        db_session = next(get_db_session())
        try:
            self.employee_cache.clear()
            self.monthly_leave_cache.clear()
            
            records = attendance_service.get_attendance_records(db=db_session, **self.filters)

            # Populate cache with ALL employees to handle placeholders correctly
            all_employees = employee_service.get_all_employees(db=db_session)
            self.employee_cache = {
                emp.id: {
                    "name": f"{emp.first_name} {emp.last_name}".strip() or emp.email,
                    "allowance": emp.monthly_leave_allowance_minutes or 0
                } for emp in all_employees
            }

            # Pre-calculate monthly leave totals for efficiency
            unique_emp_dates = {(r.employee_id, r.date) for r in records if r.id}
            for emp_id, date_val in unique_emp_dates:
                start_of_period, _ = get_jalali_month_range(date_val)
                cache_key = (emp_id, start_of_period)
                if cache_key not in self.monthly_leave_cache:
                    used_leave = attendance_service.get_monthly_leave_taken(emp_id, date_val, db_session)
                    self.monthly_leave_cache[cache_key] = used_leave

            search_text = self.filters.get('search_text', '').lower()
            if search_text:
                records = [
                    r for r in records if
                    search_text in self.employee_cache.get(r.employee_id, {}).get("name", "").lower() or
                    search_text in (r.note or "").lower()
                ]

            self.beginResetModel()
            self.attendance_data = records
            self.calculate_column_totals()
            self.endResetModel()
            self.logger.debug(f"Loaded {len(self.attendance_data)} records into model.")

        except Exception as e:
            self.logger.error(f"Error loading attendance data: {e}", exc_info=True)
            self.beginResetModel()
            self.attendance_data = []
            self.endResetModel()
        finally:
            db_session.close()

    def calculate_column_totals(self):
        """Calculate the sum of specific columns."""
        self.column_totals = {
            'tardiness': sum(r.tardiness_minutes for r in self.attendance_data if r.tardiness_minutes),
            'early_departure': sum(r.early_departure_minutes for r in self.attendance_data if r.early_departure_minutes),
            'main_work': sum(r.main_work_minutes for r in self.attendance_data if r.main_work_minutes),
            'overtime': sum(r.overtime_minutes for r in self.attendance_data if r.overtime_minutes),
            'total_duration': sum(r.duration_minutes for r in self.attendance_data if r.duration_minutes),
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self.attendance_data)

    def columnCount(self, parent=QModelIndex()):
        return self.COLUMN_COUNT

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.attendance_data)):
            return QVariant()

        record = self.attendance_data[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.EMPLOYEE_NAME_COL:
                return self.employee_cache.get(record.employee_id, {}).get("name", f"ID:{record.employee_id}")
            elif col == self.DATE_COL:
                return format_date_for_display(record.date, format_preference=self.config.settings.get("date_format", "both"))
            elif col == self.TIME_IN_COL:
                return record.time_in.strftime("%H:%M") if record.time_in else ""
            elif col == self.TIME_OUT_COL:
                return record.time_out.strftime("%H:%M") if record.time_out else ""
            elif col == self.TIME_IN_2_COL: # HEROIC IMPLEMENTATION
                return record.time_in_2.strftime("%H:%M") if record.time_in_2 else ""
            elif col == self.TIME_OUT_2_COL: # HEROIC IMPLEMENTATION
                return record.time_out_2.strftime("%H:%M") if record.time_out_2 else ""
            elif col == self.LEAVE_COL:
                return minutes_to_hhmm(record.leave_duration_minutes)
            elif col == self.USED_LEAVE_MONTH_COL:
                if not record.id: return ""
                start_of_period, _ = get_jalali_month_range(record.date)
                used_leave = self.monthly_leave_cache.get((record.employee_id, start_of_period), 0)
                return minutes_to_hhmm(used_leave)
            elif col == self.REMAINING_LEAVE_MONTH_COL:
                if not record.id: return ""
                allowance = self.employee_cache.get(record.employee_id, {}).get("allowance", 0)
                if allowance > 0:
                    start_of_period, _ = get_jalali_month_range(record.date)
                    used_leave = self.monthly_leave_cache.get((record.employee_id, start_of_period), 0)
                    remaining = max(0, allowance - used_leave)
                    return minutes_to_hhmm(remaining)
                return "N/A"
            elif col == self.TARDINESS_COL:
                return minutes_to_hhmm(record.tardiness_minutes)
            elif col == self.EARLY_DEPARTURE_COL: # HEROIC
                return minutes_to_hhmm(record.early_departure_minutes)
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
                self.TARDINESS_COL, self.EARLY_DEPARTURE_COL, self.MAIN_WORK_COL, self.OVERTIME_COL,
                self.LAUNCH_TIME_COL, self.TOTAL_DURATION_COL
            ]
            if col in numeric_cols:
                return Qt.AlignmentFlag.AlignCenter
        
        elif role == Qt.ItemDataRole.BackgroundRole:
            if not record.id and record.status == 'absent':
                 return QColor("#F4F6F7")
            if record.id and record.status == 'absent':
                return QColor("#FADBD8")
            if record.status == 'on_leave':
                return QColor("#FAE5D3")
            if record.status == 'partial':
                return QColor("#D6EAF8")

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
        """Reloads all data from the service based on current filters."""
        self.load_data()

    def set_filters(self, **kwargs):
        """Sets new filters and triggers a data refresh."""
        self.filters = kwargs
        self.refresh()

    def add_attendance_record(self, record_data: dict):
        """Proxy to add a record via the service and then refresh."""
        try:
            attendance_service.add_manual_attendance(**record_data)
            self.refresh()
        except Exception as e:
            self.logger.error(f"Error adding record via model: {e}", exc_info=True)
            raise

    def update_attendance_record(self, record_id: int, record_data: dict):
        """Proxy to update a record via the service and then refresh."""
        try:
            attendance_service.update_attendance(attendance_id=record_id, **record_data)
            self.refresh()
        except Exception as e:
            self.logger.error(f"Error updating record via model: {e}", exc_info=True)
            raise