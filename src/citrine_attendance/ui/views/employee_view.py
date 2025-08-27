# src/citrine_attendance/ui/views/employee_view.py
"""Employee management view."""
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableView,
    QMessageBox, QHeaderView, QAbstractItemView, QDialog, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal

# Import the model and dialogs
from ..models.employee_model import EmployeeTableModel
from ..dialogs.add_employee_dialog import AddEmployeeDialog
from ..dialogs.edit_employee_dialog import EditEmployeeDialog # Import the Edit dialog

# Import service errors and models for handling
from ...services.employee_service import (
    EmployeeServiceError, EmployeeAlreadyExistsError, EmployeeNotFoundError
)
from ...database import Employee # Import Employee model if needed for type hints
from ...locale import _


class EmployeeView(QWidget):
    """The employee directory view widget."""

    employee_changed = pyqtSignal() # Signal for broader app updates if needed

    def __init__(self, current_user):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.employee_model = EmployeeTableModel() # Create the model instance
        # References to dialogs to interact with them
        self.add_dialog = None
        self.edit_dialog = None
        # Connect the model's data_changed signal to refresh the view if needed
        # self.employee_model.data_changed.connect(self.on_model_data_changed)

        self.init_ui()
        self.load_employees() # Load data into the model/view

    def init_ui(self):
        """Initialize the employee view UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- Top Bar ---
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)

        self.add_btn = QPushButton(_("employee_add"))
        self.add_btn.setStyleSheet(self.get_button_style("#11563a")) # Brand color
        self.add_btn.clicked.connect(self.open_add_employee_dialog)
        top_layout.addWidget(self.add_btn)

        self.edit_btn = QPushButton(_("employee_edit"))
        self.edit_btn.setStyleSheet(self.get_button_style("#ffa500"))
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.open_edit_employee_dialog)
        top_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton(_("employee_delete"))
        self.delete_btn.setStyleSheet(self.get_button_style("#d32f2f")) # Red
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self.delete_selected_employee)
        top_layout.addWidget(self.delete_btn)

        self.import_btn = QPushButton(_("employee_import_csv"))
        self.import_btn.setStyleSheet(self.get_button_style("#4caf50")) # Green
        # self.import_btn.clicked.connect(self.import_employees_from_csv)
        top_layout.addWidget(self.import_btn)

        top_layout.addStretch()
        layout.addLayout(top_layout)

        # --- Employee Table ---
        self.employee_table = QTableView()
        self.employee_table.setAlternatingRowColors(True)
        self.employee_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.employee_table.setModel(self.employee_model) # Set the model

        # Configure header
        header = self.employee_table.horizontalHeader()
        header.setStretchLastSection(True) # Stretch 'Notes' column
        header.setSectionsClickable(True)
        self.employee_table.setSortingEnabled(True)

        # Selection handling
        self.employee_table.selectionModel().selectionChanged.connect(self.on_selection_changed)

        layout.addWidget(self.employee_table)

    def get_button_style(self, bg_color):
        """Helper for consistent button styles."""
        hover_color = self.darken_color(bg_color)
        return f"""
        QPushButton {{
            background-color: {bg_color};
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 5px;
            font-size: 14px;
        }}
        QPushButton:hover {{
            background-color: {hover_color};
        }}
        QPushButton:disabled {{
            background-color: #bdbdbd;
            color: #9e9e9e;
        }}
        """

    def darken_color(self, color_hex):
        """Simple hex color darkener."""
        color_hex = color_hex.lstrip('#')
        rgb = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))
        darker_rgb = tuple(max(0, int(c * 0.9)) for c in rgb)
        return f"#{darker_rgb[0]:02x}{darker_rgb[1]:02x}{darker_rgb[2]:02x}"

    def load_employees(self):
        """Load employee data into the table model."""
        try:
            self.employee_model.load_data()
            self.logger.debug("Employee view: Data loaded into model.")
        except Exception as e:
            self.logger.error(f"Employee view: Error loading employees: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load employees: {e}")

    def on_selection_changed(self):
        """Enable/disable edit/delete buttons based on selection."""
        has_selection = len(self.employee_table.selectionModel().selectedRows()) > 0
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    # --- Add Employee Methods ---
    def open_add_employee_dialog(self):
        """Open the dialog to add a new employee."""
        self.add_dialog = AddEmployeeDialog(self) # Parent to this view
        # Connect the dialog's signal to a local handler
        self.add_dialog.employee_added.connect(self.handle_employee_added)
        # Execute the dialog modally
        dialog_result = self.add_dialog.exec()
        # Handle result if needed (e.g., cleanup)
        if dialog_result == QDialog.DialogCode.Accepted:
            self.logger.debug("Add Employee Dialog was accepted.")
        else:
            self.logger.debug("Add Employee Dialog was cancelled.")

    def handle_employee_added(self, employee_data_dict):
        """Handle the signal from the AddEmployeeDialog when 'Add' is clicked."""
        try:
            # Use the model to add the employee via the service
            new_employee = self.employee_model.add_employee(**employee_data_dict)

            # If successful, close the dialog and show confirmation
            if self.add_dialog:
                self.add_dialog.accept() # Close the dialog

            QMessageBox.information(
                self, "Success",
                f"Employee '{new_employee.first_name} {new_employee.last_name}' added successfully."
            )
            self.logger.info(f"Employee added via UI: {new_employee.first_name} {new_employee.last_name}")

        except EmployeeAlreadyExistsError as e:
            self.logger.warning(f"Add Employee failed (duplicate): {e}")
            QMessageBox.critical(self.add_dialog, "Error", f"Add Employee failed: {e}")
            # Keep the dialog open for correction
            if self.add_dialog:
                self.add_dialog.email_input.setFocus()
                self.add_dialog.email_input.selectAll()

        except EmployeeServiceError as e:
            self.logger.error(f"Add Employee failed (service): {e}", exc_info=True)
            QMessageBox.critical(self.add_dialog, "Error", f"Add Employee failed: {e}")

        except Exception as e:
            self.logger.error(f"Add Employee failed (unexpected): {e}", exc_info=True)
            QMessageBox.critical(
                self.add_dialog, "Unexpected Error",
                f"An unexpected error occurred while adding the employee: {e}"
            )

    # --- Edit Employee Methods ---
    def open_edit_employee_dialog(self):
        """Open the dialog to edit the selected employee."""
        selected_rows = self.employee_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select an employee to edit.")
            return

        # Get the first selected row (single edit for now)
        row = selected_rows[0].row()
        employee_to_edit = self.employee_model.get_employee_at_row(row)

        if not employee_to_edit:
            QMessageBox.warning(self, "Error", "Could not find the selected employee data.")
            return

        self.edit_dialog = EditEmployeeDialog(employee_to_edit, self)
        self.edit_dialog.employee_edited.connect(self.handle_employee_edited)
        dialog_result = self.edit_dialog.exec()

    def handle_employee_edited(self, employee_data_dict):
        """Handle the signal from the EditEmployeeDialog when 'Save Changes' is clicked."""
        try:
            # Extract the ID of the employee to update
            emp_id = employee_data_dict.get('employee_id')
            if not emp_id:
                 raise ValueError("Employee ID is missing for update.")

            # Use the model to update the employee via the service
            updated_employee = self.employee_model.update_employee(**employee_data_dict)

            # If successful, close the dialog and show confirmation
            if self.edit_dialog:
                self.edit_dialog.accept()

            QMessageBox.information(
                self, "Success",
                f"Employee '{updated_employee.first_name} {updated_employee.last_name}' updated successfully."
            )
            self.logger.info(f"Employee updated via UI: ID {updated_employee.id}")

            # The model's update_employee calls load_data which refreshes the view.

        except EmployeeAlreadyExistsError as e:
            self.logger.warning(f"Edit Employee failed (duplicate email): {e}")
            QMessageBox.critical(self.edit_dialog, "Error", f"Edit Employee failed: {e}")
            if self.edit_dialog:
                self.edit_dialog.email_input.setFocus()
                self.edit_dialog.email_input.selectAll()

        except EmployeeServiceError as e:
            self.logger.error(f"Edit Employee failed (service): {e}", exc_info=True)
            QMessageBox.critical(self.edit_dialog, "Error", f"Edit Employee failed: {e}")

        except Exception as e:
            self.logger.error(f"Edit Employee failed (unexpected): {e}", exc_info=True)
            QMessageBox.critical(
                self.edit_dialog, "Unexpected Error",
                f"An unexpected error occurred while updating the employee: {e}"
            )

    # --- Delete Employee Method ---
    def delete_selected_employee(self):
        """Delete the selected employee after confirmation."""
        selected_rows = self.employee_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select an employee to delete.")
            return

        # Get the first selected row
        row = selected_rows[0].row()
        employee_to_delete = self.employee_model.get_employee_at_row(row)

        if not employee_to_delete:
            QMessageBox.warning(self, "Error", "Could not find the selected employee data.")
            return

        # Confirmation dialog
        reply = QMessageBox.question(
            self, 'Confirm Delete',
            _("employee_confirm_delete", employee_name=f"{employee_to_delete.first_name} {employee_to_delete.last_name}", email=employee_to_delete.email),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Use the model to delete the employee via the service
                self.employee_model.remove_employee(employee_to_delete.id)

                QMessageBox.information(
                    self, "Success",
                    _("employee_deleted_success", employee_name=f"{employee_to_delete.first_name} {employee_to_delete.last_name}")
                )
                self.logger.info(f"Employee deleted via UI: ID {employee_to_delete.id}")

                # Model refresh handled by remove_employee
                # Disable buttons as selection is now invalid
                self.edit_btn.setEnabled(False)
                self.delete_btn.setEnabled(False)

            except EmployeeNotFoundError:
                self.logger.warning(f"Delete failed: Employee ID {employee_to_delete.id} not found.")
                QMessageBox.warning(self, "Not Found", _("employee_not_found"))
                # Refresh the list to reflect the actual state
                self.load_employees()

            except Exception as e:
                self.logger.error(f"Delete Employee failed: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to delete employee: {e}")

    # --- Placeholder methods ---
    # def import_employees_from_csv(self): pass
    # def on_model_data_changed(self): pass # If needed

# Example usage (if run directly)
# if __name__ == '__main__':
#     from PyQt6.QtWidgets import QApplication, QMainWindow
#     import sys
#     from ...database import init_db, User
#     init_db()
#     app = QApplication(sys.argv)
#     user = User(username="testuser", role="admin")
#     window = QMainWindow()
#     emp_view = EmployeeView(user)
#     window.setCentralWidget(emp_view)
#     window.show()
#     sys.exit(app.exec())