# src/citrine_attendance/ui/models/employee_model.py
"""Data model for the employee table view."""
import logging
from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex, QVariant, pyqtSignal
from PyQt6.QtGui import QFont

from ...services.employee_service import employee_service, EmployeeNotFoundError
from ...database import get_db_session
from ...utils.time_utils import minutes_to_hhmm

class EmployeeTableModel(QAbstractTableModel):
    """Custom model to display and manage employee data in a QTableView."""

    # HEROIC FIX: Added column for leave allowance
    ID_COL = 0
    NAME_COL = 1
    EMAIL_COL = 2
    PHONE_COL = 3
    LEAVE_ALLOWANCE_COL = 4
    NOTES_COL = 5
    COLUMN_HEADERS = ["ID", "Name", "Email", "Phone", "Monthly Leave (H:M)", "Notes"]
    COLUMN_COUNT = len(COLUMN_HEADERS)

    data_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.employee_data = [] # List of Employee objects
        self.db_session = None

    def load_data(self):
        """Load employee data from the service."""
        try:
            session_gen = get_db_session()
            self.db_session = next(session_gen)
            employees = employee_service.get_all_employees(db=self.db_session)
            self.beginResetModel()
            self.employee_data = list(employees)
            self.endResetModel()
            self.logger.debug(f"Loaded {len(self.employee_data)} employees into model.")
            self.data_changed.emit()
        except Exception as e:
            self.logger.error(f"Error loading employee data: {e}", exc_info=True)
            raise
        finally:
            if self.db_session:
                 self.db_session.close()
                 self.db_session = None

    def rowCount(self, parent=QModelIndex()):
        return len(self.employee_data)

    def columnCount(self, parent=QModelIndex()):
        return self.COLUMN_COUNT

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Return data for a specific cell."""
        if not index.isValid() or index.row() >= len(self.employee_data):
            return QVariant()

        employee = self.employee_data[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == self.ID_COL:
                return employee.id
            elif index.column() == self.NAME_COL:
                return f"{employee.first_name} {employee.last_name}".strip()
            elif index.column() == self.EMAIL_COL:
                return employee.email
            elif index.column() == self.PHONE_COL:
                return employee.phone or ""
            elif index.column() == self.LEAVE_ALLOWANCE_COL:
                # HEROIC FIX: Display leave allowance in H:M format
                return minutes_to_hhmm(employee.monthly_leave_allowance_minutes)
            elif index.column() == self.NOTES_COL:
                return employee.notes or ""
        elif role == Qt.ItemDataRole.FontRole and index.column() == self.NAME_COL:
             font = QFont()
             font.setBold(True)
             return font
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() == self.LEAVE_ALLOWANCE_COL:
                return Qt.AlignmentFlag.AlignCenter

        return QVariant()

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        """Return data for the header."""
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < self.COLUMN_COUNT:
                return self.COLUMN_HEADERS[section]
        return QVariant()

    def get_employee_at_row(self, row):
        """Helper to get the Employee object for a given row."""
        if 0 <= row < len(self.employee_data):
            return self.employee_data[row]
        return None

    def add_employee(self, **kwargs):
        """
        Add a new employee via the service and update the model.
        Returns the new Employee object or raises an exception.
        """
        session_gen = get_db_session()
        db_session = next(session_gen)
        try:
            new_employee = employee_service.create_employee(db=db_session, **kwargs)
            db_session.close()
            self.load_data()
            self.logger.info(f"Employee added via model: {new_employee.first_name}")
            return new_employee
        except Exception as e:
            if 'db_session' in locals() and db_session.is_active:
                db_session.close()
            self.logger.error(f"Error adding employee via model: {e}", exc_info=True)
            raise

    def update_employee(self, **kwargs):
        """
        Update an existing employee via the service and refresh the model.
        Returns the updated Employee object or raises an exception.
        """
        session_gen = get_db_session()
        db_session = next(session_gen)
        try:
            updated_employee = employee_service.update_employee(db=db_session, **kwargs)
            db_session.close()
            self.load_data()
            self.logger.info(f"Employee ID {updated_employee.id} updated via model.")
            return updated_employee
        except Exception as e:
            if 'db_session' in locals() and db_session.is_active:
                db_session.close()
            self.logger.error(f"Error updating employee ID {kwargs.get('employee_id')} via model: {e}", exc_info=True)
            raise

    def remove_employee(self, emp_id):
        """Remove an employee by ID via the service and update the model."""
        session_gen = get_db_session()
        db_session = next(session_gen)
        try:
            employee_service.delete_employee(emp_id, db=db_session)
            db_session.close()
            self.load_data()
            self.logger.info(f"Employee ID {emp_id} removed via model.")
            self.data_changed.emit()
        except EmployeeNotFoundError:
            if 'db_session' in locals() and db_session.is_active:
                db_session.close()
            self.logger.warning(f"Employee ID {emp_id} not found for deletion.")
            raise
        except Exception as e:
            if 'db_session' in locals() and db_session.is_active:
                db_session.close()
            self.logger.error(f"Error removing employee ID {emp_id} via model: {e}", exc_info=True)
            raise