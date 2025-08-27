# src/citrine_attendance/ui/models/employee_model.py
"""Data model for the employee table view."""
import logging
from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex, QVariant, pyqtSignal
from PyQt6.QtGui import QFont

from ...services.employee_service import employee_service, EmployeeNotFoundError
from ...database import get_db_session


class EmployeeTableModel(QAbstractTableModel):
    """Custom model to display and manage employee data in a QTableView."""

    # Define column indices and headers
    ID_COL = 0
    NAME_COL = 1
    EMAIL_COL = 2
    PHONE_COL = 3
    NOTES_COL = 4
    COLUMN_HEADERS = ["ID", "Name", "Email", "Phone", "Notes"]
    COLUMN_COUNT = len(COLUMN_HEADERS)

    # Signal emitted when data is successfully added/edited/removed
    data_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.employee_data = [] # List of Employee objects
        self.db_session = None

    def load_data(self):
        """Load employee data from the service."""
        old_session = self.db_session # Store old session if any
        try:
            # Get a new session (using generator pattern)
            session_gen = get_db_session()
            self.db_session = next(session_gen)

            # Fetch employees using the service
            employees = employee_service.get_all_employees(db=self.db_session)

            # Begin model reset to update the view
            self.beginResetModel()
            self.employee_data = list(employees) # Ensure it's a list
            self.endResetModel()

            self.logger.debug(f"Loaded {len(self.employee_data)} employees into model.")
            self.data_changed.emit() # Notify listeners
        except Exception as e:
            self.logger.error(f"Error loading employee data: {e}", exc_info=True)
            # Re-raise or handle appropriately
            raise
        finally:
            # Close the old session if it was different
            if old_session:
                old_session.close()
            # Do not close the new session here, as it might be needed for subsequent operations
            # The model should manage its session lifecycle carefully.
            # For simplicity, we'll close it after load_data is done, but this means
            # subsequent calls (like setData) need to get a new session.
            # A better approach might be to pass the session from the view/controller.
            # Let's close it here for now, and views will request a new one if needed.
            if self.db_session:
                 self.db_session.close()
                 self.db_session = None

    def rowCount(self, parent=QModelIndex()):
        """Return the number of rows (employees)."""
        return len(self.employee_data)

    def columnCount(self, parent=QModelIndex()):
        """Return the number of columns."""
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
            elif index.column() == self.NOTES_COL:
                return employee.notes or ""
        elif role == Qt.ItemDataRole.FontRole and index.column() == self.NAME_COL:
             # Make names slightly bolder
             font = QFont()
             font.setBold(True)
             return font
        # Add other roles like TextAlignmentRole if needed

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

    def get_employee_by_id(self, emp_id):
        """Helper to get an Employee object by its database ID."""
         # Iterate through the current model data
        for emp in self.employee_data:
             if emp.id == emp_id:
                 return emp
        return None # Not found in current model data

    def refresh(self):
        """Reload data from the database."""
        self.load_data() # This handles begin/end reset

    # --- Methods for adding an employee (interacts with service) ---
    def add_employee(self, first_name, last_name, email, phone, notes, employee_id=None):
        """
        Add a new employee via the service and update the model.
        Returns the new Employee object or raises an exception.
        """
        session_gen = get_db_session()
        db_session = next(session_gen)
        try:
            # Use the service to create the employee
            new_employee = employee_service.create_employee(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                notes=notes,
                employee_id=employee_id,
                db=db_session
            )
            # Close the session used for creation
            db_session.close()

            # Update the model: Add the new employee to the list and notify views
            # Get a new session for loading (or use the one from load_data)
            self.load_data() # Reload all data to ensure consistency and correct sorting
            # Alternatively, insert the row manually:
            # self.beginInsertRows(QModelIndex(), len(self.employee_data), len(self.employee_data))
            # self.employee_data.append(new_employee)
            # self.endInsertRows()
            # self.data_changed.emit()

            self.logger.info(f"Employee added via model: {new_employee.first_name} {new_employee.last_name}")
            return new_employee

        except Exception as e:
            # Ensure session is closed even if creation fails
            if 'db_session' in locals() and db_session:
                db_session.close()
            self.logger.error(f"Error adding employee via model: {e}", exc_info=True)
            raise # Re-raise to let the caller handle the UI feedback

    def update_employee(self, employee_id, first_name=None, last_name=None, email=None,
                        phone=None, notes=None, employee_id_field=None):
        """
        Update an existing employee via the service and refresh the model.
        Returns the updated Employee object or raises an exception.
        """
        session_gen = get_db_session()
        db_session = next(session_gen)
        try:
            # Use the service to update the employee
            updated_employee = employee_service.update_employee(
                employee_id=employee_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                notes=notes,
                employee_id_field=employee_id_field, # Pass the custom ID field
                db=db_session
            )
            db_session.close()

            # Refresh the model data
            self.load_data()
            self.logger.info(f"Employee ID {employee_id} updated via model.")
            return updated_employee

        except Exception as e:
            if 'db_session' in locals() and db_session:
                db_session.close()
            self.logger.error(f"Error updating employee ID {employee_id} via model: {e}", exc_info=True)
            raise

    # --- Methods for removing an employee (interacts with service) ---
    def remove_employee(self, emp_id):
        """Remove an employee by ID via the service and update the model."""
        session_gen = get_db_session()
        db_session = next(session_gen)
        try:
            # Use the service to delete the employee
            employee_service.delete_employee(emp_id, db=db_session)
            db_session.close()

            # Refresh the model to reflect the deletion
            # Alternatively, find and remove the row manually (more efficient)
            # but reload is simpler and safer for consistency.
            self.load_data()
            self.logger.info(f"Employee ID {emp_id} removed via model.")
            self.data_changed.emit()

        except EmployeeNotFoundError:
            if 'db_session' in locals() and db_session:
                db_session.close()
            self.logger.warning(f"Employee ID {emp_id} not found for deletion.")
            raise
        except Exception as e:
            if 'db_session' in locals() and db_session:
                db_session.close()
            self.logger.error(f"Error removing employee ID {emp_id} via model: {e}", exc_info=True)
            raise

    # --- Methods for editing an employee (interacts with service) ---
    # (Similar structure to add_employee, using employee_service.update_employee)

    # --- Methods for removing an employee (interacts with service) ---
    # (Similar structure to add_employee, using employee_service.delete_employee)
    # def remove_employee(self, emp_id):
    #     """Remove an employee by ID via the service and update the model."""
    #     session_gen = get_db_session()
    #     db_session = next(session_gen)
    #     try:
    #         # Use the service to delete the employee
    #         employee_service.delete_employee(emp_id, db=db_session)
    #         db_session.close()
    #
    #         # Update the model: Find and remove the employee
    #         row_to_remove = -1
    #         for i, emp in enumerate(self.employee_data):
    #             if emp.id == emp_id:
    #                 row_to_remove = i
    #                 break
    #
    #         if row_to_remove != -1:
    #             self.beginRemoveRows(QModelIndex(), row_to_remove, row_to_remove)
    #             del self.employee_data[row_to_remove]
    #             self.endRemoveRows()
    #             self.logger.info(f"Employee ID {emp_id} removed via model.")
    #             self.data_changed.emit()
    #         else:
    #             self.logger.warning(f"Employee ID {emp_id} not found in model for removal.")
    #             # Reload data to be safe?
    #             self.load_data()
    #
    #     except EmployeeNotFoundError:
    #         if 'db_session' in locals() and db_session:
    #             db_session.close()
    #         self.logger.warning(f"Employee ID {emp_id} not found for deletion.")
    #         raise
    #     except Exception as e:
    #         if 'db_session' in locals() and db_session:
    #             db_session.close()
    #         self.logger.error(f"Error removing employee ID {emp_id} via model: {e}", exc_info=True)
    #         raise

# Example usage (if run directly)
# if __name__ == '__main__':
#     from PyQt6.QtWidgets import QApplication, QTableView
#     import sys
#     from ...database import init_db
#     init_db()
#     app = QApplication(sys.argv)
#     table_view = QTableView()
#     model = EmployeeTableModel()
#     model.load_data()
#     table_view.setModel(model)
#     table_view.show()
#     sys.exit(app.exec())