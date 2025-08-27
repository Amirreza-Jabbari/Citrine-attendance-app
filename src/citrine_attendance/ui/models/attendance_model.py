# src/citrine_attendance/ui/models/attendance_model.py
"""Data model for the attendance table view."""
import logging
from datetime import date, time, datetime
from typing import List, Optional, Any

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex, QVariant, QDate, QTime
from PyQt6.QtGui import QFont

# Import the updated attendance service
from ...services.attendance_service import attendance_service, AttendanceServiceError
from ...services.employee_service import employee_service
from ...database import get_db_session, Attendance, Employee
from ...date_utils import gregorian_to_jalali, format_date_for_display


class AttendanceTableModel(QAbstractTableModel):
    """Custom model to display and manage attendance data in a QTableView."""

    # Define column indices and headers
    # --- EMPLOYEE_NAME_COL is already added ---
    EMPLOYEE_NAME_COL = 0
    DATE_COL = 1
    TIME_IN_COL = 2
    TIME_OUT_COL = 3
    DURATION_COL = 4
    STATUS_COL = 5
    NOTE_COL = 6
    # Columns not directly editable in the main table but part of the model
    EMPLOYEE_ID_COL = 7 # Hidden column for internal use
    ID_COL = 8 # Hidden column for the attendance record ID

    # --- UPDATE COLUMN_HEADERS (remains the same, Status column still exists but shows Present/Absent) ---
    COLUMN_HEADERS = ["Employee Name", "Date", "Time In", "Time Out", "Duration (min)", "Status", "Note"]
    COLUMN_COUNT = len(COLUMN_HEADERS)
    # Add two for the hidden columns (Employee ID and Record ID)
    TOTAL_COLUMN_COUNT = COLUMN_COUNT + 2 

    # --- UPDATE STATUS_DISPLAY to reflect only Present and Absent ---
    # Status display names - Defined as class attributes
    # Use the constants from the updated attendance_service
    STATUS_DISPLAY = {
        attendance_service.STATUS_PRESENT: "Present",
        attendance_service.STATUS_ABSENT: "Absent",
        # Late and Half Day entries removed
    }

    # --- UPDATE STATUS_DISPLAY_INVERSE to match the new STATUS_DISPLAY ---
    # Inverse status lookup - Defined as class attribute
    # Create the inverse dictionary using a dictionary comprehension
    # This will now only map "Present" -> "present" and "Absent" -> "absent"
    STATUS_DISPLAY_INVERSE = {v: k for k, v in STATUS_DISPLAY.items()}

    def __init__(self, config):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.config = config # For date format preferences
        self.attendance_data: List[Attendance] = []
        self.employee_cache = {} # Cache employee names {id: "First Last"}
        self.db_session = None
        # Filters
        self.filter_employee_id: Optional[int] = None
        self.filter_start_date: Optional[date] = None
        self.filter_end_date: Optional[date] = None
        self.filter_statuses: List[str] = [] # This will now only hold 'present' or 'absent'
        self.search_text: str = ""

    def load_data(self):
        """Load attendance data based on current filters."""
        old_session = self.db_session
        try:
            session_gen = get_db_session()
            self.db_session = next(session_gen)

            # Fetch attendance records using the service with filters
            # The service now only handles 'present' and 'absent'
            records = attendance_service.get_attendance_records(
                employee_id=self.filter_employee_id,
                start_date=self.filter_start_date,
                end_date=self.filter_end_date,
                statuses=self.filter_statuses if self.filter_statuses else None,
                db=self.db_session
            )

            # Filter by search text (simple, case-insensitive search in notes/status/employee name)
            if self.search_text:
                search_lower = self.search_text.lower()
                # Need to check employee name in search. Ensure cache is populated first.
                if records:
                    employee_ids = {r.employee_id for r in records}
                    if employee_ids and not self.employee_cache:
                        # Populate cache if empty and we have records to filter
                        employees = self.db_session.query(Employee).filter(Employee.id.in_(employee_ids)).all()
                        self.employee_cache = {emp.id: f"{emp.first_name} {emp.last_name}".strip() for emp in employees}
                    
                records = [
                    r for r in records
                    if search_lower in (r.note or "").lower() or
                       search_lower in self.STATUS_DISPLAY.get(r.status, r.status).lower() or
                       search_lower in self.employee_cache.get(r.employee_id, "").lower()
                ]

            # Load employee names for display (cache them)
            # This should happen for all records fetched, regardless of search filter
            if records: # Only fetch if there are records
                employee_ids = {r.employee_id for r in records}
                if employee_ids:
                     employees = self.db_session.query(Employee).filter(Employee.id.in_(employee_ids)).all()
                     self.employee_cache = {emp.id: f"{emp.first_name} {emp.last_name}".strip() for emp in employees}

            # Begin model reset to update the view
            self.beginResetModel()
            self.attendance_data = list(records)
            self.endResetModel()

            self.logger.debug(f"Loaded {len(self.attendance_data)} attendance records into model.")

        except Exception as e:
            self.logger.error(f"Error loading attendance data: {e}", exc_info=True)
            raise
        finally:
            if old_session:
                old_session.close()
            if self.db_session:
                # Keep session open for potential edits? Or close and re-open?
                # For simplicity, close it. Views will request a new one if needed for edits.
                self.db_session.close()
                self.db_session = None

    def rowCount(self, parent=QModelIndex()):
        """Return the number of rows (attendance records)."""
        return len(self.attendance_data)

    def columnCount(self, parent=QModelIndex()):
        """Return the number of visible columns."""
        return self.COLUMN_COUNT

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Return data for a specific cell."""
        if not index.isValid() or index.row() >= len(self.attendance_data):
            return QVariant()

        record = self.attendance_data[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            # --- EMPLOYEE_NAME_COL handling (already implemented) ---
            if col == self.EMPLOYEE_NAME_COL:
                # Use the cached employee name
                return self.employee_cache.get(record.employee_id, f"ID:{record.employee_id}")
            elif col == self.DATE_COL:
                if record.date:
                    # Format based on user preference
                    format_pref = self.config.settings.get("date_format", "both")
                    return format_date_for_display(record.date, format_preference=format_pref)
                return ""
            elif col == self.TIME_IN_COL:
                if record.time_in:
                    return record.time_in.strftime("%H:%M")
                return ""
            elif col == self.TIME_OUT_COL:
                if record.time_out:
                    return record.time_out.strftime("%H:%M")
                return ""
            elif col == self.DURATION_COL:
                if record.duration_minutes is not None:
                    return str(record.duration_minutes)
                return ""
            elif col == self.STATUS_COL:
                # Return human-readable status using the UPDATED class attribute
                # This will now only show "Present" or "Absent"
                return self.STATUS_DISPLAY.get(record.status, record.status)
            elif col == self.NOTE_COL:
                return record.note or ""
            # Hidden columns data (if needed for internal logic, but usually not displayed)
            elif col == self.EMPLOYEE_ID_COL:
                return record.employee_id
            elif col == self.ID_COL:
                return record.id

        elif role == Qt.ItemDataRole.ToolTipRole:
            if col == self.DATE_COL and record.date:
                # Tooltip with ISO date/time
                iso_date_str = record.date.isoformat() if record.date else ""
                time_in_str = record.time_in.strftime("%H:%M:%S") if record.time_in else ""
                time_out_str = record.time_out.strftime("%H:%M:%S") if record.time_out else ""
                return f"{iso_date_str} In: {time_in_str} Out: {time_out_str}"
            elif col == self.STATUS_COL:
                 return record.status # Show raw status in tooltip
            # --- Tooltip for Employee Name (already implemented) ---
            elif col == self.EMPLOYEE_NAME_COL:
                emp = self.db_session.query(Employee).filter(Employee.id == record.employee_id).first() if self.db_session else None
                if emp:
                    return f"{emp.email}\nID: {emp.employee_id or 'N/A'}"

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in [self.TIME_IN_COL, self.TIME_OUT_COL, self.DURATION_COL]:
                return Qt.AlignmentFlag.AlignCenter
            # --- Align Employee Name to the left (already implemented) ---
            elif col == self.EMPLOYEE_NAME_COL:
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        # Add font role for status if desired (e.g., bold for absent)
        # elif role == Qt.ItemDataRole.FontRole and col == self.STATUS_COL:
        #     # Example: Make 'Absent' status bold
        #     if record.status == attendance_service.STATUS_ABSENT:
        #         font = QFont()
        #         font.setBold(True)
        #         return font

        return QVariant()

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        """Set data for a specific cell (for inline editing)."""
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False

        row = index.row()
        col = index.column()
        if row >= len(self.attendance_data):
            return False

        record = self.attendance_data[row]
        update_kwargs = {}

        try:
            # --- Prevent editing of Employee Name (already implemented) ---
            if col == self.EMPLOYEE_NAME_COL:
                 return False # Employee name is not editable in this table

            if col == self.TIME_IN_COL:
                # Parse time input (expecting HH:MM format)
                if value:
                    new_time_in = datetime.strptime(value, "%H:%M").time()
                else:
                    new_time_in = None
                update_kwargs['time_in'] = new_time_in

            elif col == self.TIME_OUT_COL:
                # Parse time input
                if value:
                    new_time_out = datetime.strptime(value, "%H:%M").time()
                else:
                    new_time_out = None
                update_kwargs['time_out'] = new_time_out

            elif col == self.NOTE_COL:
                update_kwargs['note'] = value if value else None

            else:
                # Other columns are not editable directly in the table
                return False

            # Perform the update via the service
            # Get a new session for the update
            session_gen = get_db_session()
            update_session = next(session_gen)
            try:
                updated_record = attendance_service.update_attendance(
                    attendance_id=record.id,
                    db=update_session,
                    **update_kwargs
                )
                # Update the model's record with the returned updated record
                # This ensures duration/status are also updated in the model
                self.attendance_data[row] = updated_record
                # Emit dataChanged signal for the updated cell(s) - duration/status might change
                # For simplicity, emit for the whole row
                first_col_idx = self.index(row, 0)
                last_col_idx = self.index(row, self.COLUMN_COUNT - 1)
                self.dataChanged.emit(first_col_idx, last_col_idx, [Qt.ItemDataRole.DisplayRole])
                self.logger.info(f"Attendance record ID {record.id} updated via model.")
                return True
            finally:
                update_session.close()

        except ValueError as e: # For time parsing errors
            self.logger.warning(f"Invalid time format for editing: {e}")
            # TODO: How to report this error to the view? Maybe a signal?
            return False
        except AttendanceServiceError as e:
            self.logger.error(f"Error updating attendance record ID {record.id} via service: {e}", exc_info=True)
            # TODO: Report error to view
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error updating attendance record ID {record.id}: {e}", exc_info=True)
            return False

    def flags(self, index):
        """Return the item flags for a given index (enables editing for specific cells)."""
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        col = index.column()
        # Make Time In, Time Out, and Note columns editable
        # --- EMPLOYEE_NAME_COL is NOT editable (already implemented) ---
        if col in [self.TIME_IN_COL, self.TIME_OUT_COL, self.NOTE_COL]:
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        else:
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable # Read-only

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        """Return data for the header."""
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < self.COLUMN_COUNT:
                return self.COLUMN_HEADERS[section]
        return QVariant()

    def get_attendance_at_row(self, row: int) -> Optional[Attendance]:
        """Helper to get the Attendance object for a given row."""
        if 0 <= row < len(self.attendance_data):
            return self.attendance_data[row]
        return None

    def refresh(self):
        """Reload data from the database based on current filters."""
        self.load_data()

    def set_filters(self, employee_id=None, start_date=None, end_date=None, statuses=None, search_text=""):
        """Set the filters and trigger a data reload."""
        self.filter_employee_id = employee_id
        self.filter_start_date = start_date
        self.filter_end_date = end_date
        # --- Ensure only valid statuses ('present', 'absent') are passed ---
        # The view should only pass these, but this adds robustness
        if statuses:
            valid_statuses = [attendance_service.STATUS_PRESENT, attendance_service.STATUS_ABSENT]
            self.filter_statuses = [s for s in statuses if s in valid_statuses]
        else:
            self.filter_statuses = []
        self.search_text = search_text
        self.refresh()

    # --- UPDATE get_aggregates to reflect only Present and Absent counts ---
    def get_aggregates(self):
        """Calculate and return aggregate values for the current data set."""
        total_minutes = 0
        present_days = 0
        absent_days = 0
        # late_days and halfday_days are removed

        for record in self.attendance_data:
            if record.duration_minutes is not None:
                total_minutes += record.duration_minutes
            # Count statuses
            if record.status == attendance_service.STATUS_PRESENT:
                present_days += 1
            elif record.status == attendance_service.STATUS_ABSENT:
                absent_days += 1
            # Counting for late and halfday removed

        return {
            "total_minutes": total_minutes,
            "present_days": present_days,
            "absent_days": absent_days,
            # late_days and halfday_days removed
        }

    # --- Methods for adding/removing records (interacts with service) ---
    # add_attendance_record and remove_attendance_record remain largely the same
    # as they interact with the service which handles the logic.
    def add_attendance_record(self, employee_id: int, date: date, time_in: Optional[time],
                              time_out: Optional[time], note: Optional[str]):
        """Add a new manual attendance record."""
        session_gen = get_db_session()
        db_session = next(session_gen)
        try:
            # Use service to add
            new_record = attendance_service.add_manual_attendance(
                employee_id=employee_id,
                date=date,
                time_in=time_in,
                time_out=time_out,
                note=note,
                # created_by should ideally come from the logged-in user context
                created_by="UI_Manual_Entry",
                db=db_session
            )
            db_session.close()

            # Refresh model data
            self.load_data()
            self.logger.info(f"Manual attendance record added via model: ID {new_record.id}")
            return new_record

        except Exception as e:
            if 'db_session' in locals() and db_session:
                db_session.close()
            self.logger.error(f"Error adding manual attendance via model: {e}", exc_info=True)
            raise

    def remove_attendance_record(self, record_id: int):
        """Remove an attendance record by ID."""
        session_gen = get_db_session()
        db_session = next(session_gen)
        try:
            attendance_service.delete_attendance(record_id, db=db_session)
            db_session.close()

            # Refresh model data
            self.load_data()
            self.logger.info(f"Attendance record ID {record_id} removed via model.")

        except Exception as e:
            if 'db_session' in locals() and db_session:
                db_session.close()
            self.logger.error(f"Error removing attendance record ID {record_id} via model: {e}", exc_info=True)
            raise

# Example usage (if run directly)
# if __name__ == '__main__':
#     from PyQt6.QtWidgets import QApplication, QTableView
#     import sys
#     from ...database import init_db
#     from ...config import config
#     init_db()
#     app = QApplication(sys.argv)
#     table_view = QTableView()
#     model = AttendanceTableModel(config)
#     # Set some filters for testing
#     # model.set_filters(start_date=date(2023, 1, 1), end_date=date(2023, 12, 31))
#     model.load_data()
#     table_view.setModel(model)
#     table_view.show()
#     sys.exit(app.exec())