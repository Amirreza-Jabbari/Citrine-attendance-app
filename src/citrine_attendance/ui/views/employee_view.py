# src/citrine_attendance/ui/views/employee_view.py
"""Employee management view with a modern UI."""
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableView,
    QMessageBox, QHeaderView, QAbstractItemView, QDialog, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal

from ..models.employee_model import EmployeeTableModel
from ..dialogs.add_employee_dialog import AddEmployeeDialog
from ..dialogs.edit_employee_dialog import EditEmployeeDialog
from ...services.employee_service import (
    EmployeeServiceError, EmployeeAlreadyExistsError, EmployeeNotFoundError
)
from ...locale import _

class EmployeeView(QWidget):
    """The employee directory view, styled by the main window's stylesheet."""

    employee_changed = pyqtSignal()

    def __init__(self, current_user):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.employee_model = EmployeeTableModel()
        self.add_dialog = None
        self.edit_dialog = None

        self.init_ui()
        self.load_employees() # Load initial data when the view is created

    def init_ui(self):
        """Initialize the employee view UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(25, 25, 25, 25)

        # View Title
        title_label = QLabel(_("employee_view_title"))
        title_label.setObjectName("viewTitle")
        main_layout.addWidget(title_label)

        # --- Top Bar with action buttons ---
        top_layout = QHBoxLayout()
        
        self.add_btn = QPushButton(_("employee_add"))
        self.add_btn.clicked.connect(self.open_add_employee_dialog)
        top_layout.addWidget(self.add_btn)

        self.edit_btn = QPushButton(_("employee_edit"))
        self.edit_btn.setObjectName("editButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.open_edit_employee_dialog)
        top_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton(_("employee_delete"))
        self.delete_btn.setObjectName("deleteButton")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self.delete_selected_employee)
        top_layout.addWidget(self.delete_btn)

        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # --- Employee Table ---
        self.employee_table = QTableView()
        self.employee_table.setModel(self.employee_model)
        self.employee_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.employee_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.employee_table.setSortingEnabled(True)
        self.employee_table.setAlternatingRowColors(True)

        # Configure header
        header = self.employee_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        # Connect selection changes to button states
        self.employee_table.selectionModel().selectionChanged.connect(self.on_selection_changed)

        main_layout.addWidget(self.employee_table)

    def load_employees(self):
        """Load or refresh employee data into the table model."""
        try:
            self.employee_model.load_data()
            self.logger.debug("Employee view: Data reloaded into model.")
        except Exception as e:
            self.logger.error(f"Employee view: Error loading employees: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load employees: {e}")

    def on_selection_changed(self):
        """Enable/disable edit/delete buttons based on selection."""
        has_selection = self.employee_table.selectionModel().hasSelection()
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    def open_add_employee_dialog(self):
        """Open the dialog to add a new employee."""
        self.add_dialog = AddEmployeeDialog(self)
        self.add_dialog.employee_added.connect(self.handle_employee_added)
        self.add_dialog.exec()

    def handle_employee_added(self, employee_data_dict):
        """Handle the signal from the AddEmployeeDialog."""
        try:
            new_employee = self.employee_model.add_employee(**employee_data_dict)
            if self.add_dialog:
                self.add_dialog.accept()

            QMessageBox.information(
                self, "Success",
                f"Employee '{new_employee.first_name} {new_employee.last_name}' added successfully."
            )
            self.logger.info(f"Employee added via UI: {new_employee.first_name} {new_employee.last_name}")
            self.employee_changed.emit()

        except EmployeeAlreadyExistsError as e:
            self.logger.warning(f"Add Employee failed (duplicate): {e}")
            QMessageBox.critical(self.add_dialog, "Error", f"Add Employee failed: {e}")
            if self.add_dialog: self.add_dialog.email_input.setFocus()
        except EmployeeServiceError as e:
            self.logger.error(f"Add Employee failed (service): {e}", exc_info=True)
            QMessageBox.critical(self.add_dialog, "Error", f"Add Employee failed: {e}")
        except Exception as e:
            self.logger.error(f"Add Employee failed (unexpected): {e}", exc_info=True)
            QMessageBox.critical(
                self.add_dialog, "Unexpected Error",
                f"An unexpected error occurred: {e}"
            )

    def open_edit_employee_dialog(self):
        """Open the dialog to edit the selected employee."""
        selected_rows = self.employee_table.selectionModel().selectedRows()
        if not selected_rows: return

        row = selected_rows[0].row()
        employee_to_edit = self.employee_model.get_employee_at_row(row)
        if not employee_to_edit:
            QMessageBox.warning(self, "Error", "Could not find selected employee data.")
            return

        self.edit_dialog = EditEmployeeDialog(employee_to_edit, self)
        self.edit_dialog.employee_edited.connect(self.handle_employee_edited)
        self.edit_dialog.exec()

    def handle_employee_edited(self, employee_data_dict):
        """Handle the signal from the EditEmployeeDialog."""
        try:
            if 'employee_id' not in employee_data_dict:
                raise ValueError("Employee ID is missing for update.")

            updated_employee = self.employee_model.update_employee(**employee_data_dict)
            if self.edit_dialog:
                self.edit_dialog.accept()

            QMessageBox.information(
                self, "Success",
                f"Employee '{updated_employee.first_name} {updated_employee.last_name}' updated successfully."
            )
            self.logger.info(f"Employee updated via UI: ID {updated_employee.id}")
            self.employee_changed.emit()

        except EmployeeAlreadyExistsError as e:
            self.logger.warning(f"Edit Employee failed (duplicate email): {e}")
            QMessageBox.critical(self.edit_dialog, "Error", f"Edit Employee failed: {e}")
            if self.edit_dialog: self.edit_dialog.email_input.setFocus()
        except EmployeeServiceError as e:
            self.logger.error(f"Edit Employee failed (service): {e}", exc_info=True)
            QMessageBox.critical(self.edit_dialog, "Error", f"Edit Employee failed: {e}")
        except Exception as e:
            self.logger.error(f"Edit Employee failed (unexpected): {e}", exc_info=True)
            QMessageBox.critical(
                self.edit_dialog, "Unexpected Error",
                f"An unexpected error occurred: {e}"
            )

    def delete_selected_employee(self):
        """Delete the selected employee after confirmation."""
        selected_rows = self.employee_table.selectionModel().selectedRows()
        if not selected_rows: return

        row = selected_rows[0].row()
        employee_to_delete = self.employee_model.get_employee_at_row(row)
        if not employee_to_delete:
            QMessageBox.warning(self, "Error", "Could not find selected employee data.")
            return

        reply = QMessageBox.question(
            self, 'Confirm Delete',
            _("employee_confirm_delete", 
              employee_name=f"{employee_to_delete.first_name} {employee_to_delete.last_name}", 
              email=employee_to_delete.email),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.employee_model.remove_employee(employee_to_delete.id)
                QMessageBox.information(
                    self, "Success",
                    _("employee_deleted_success", 
                      employee_name=f"{employee_to_delete.first_name} {employee_to_delete.last_name}")
                )
                self.logger.info(f"Employee deleted via UI: ID {employee_to_delete.id}")
                self.employee_changed.emit()
            except EmployeeNotFoundError:
                self.logger.warning(f"Delete failed: Employee ID {employee_to_delete.id} not found.")
                QMessageBox.warning(self, "Not Found", _("employee_not_found"))
                self.load_employees() # Refresh view from db
            except Exception as e:
                self.logger.error(f"Delete Employee failed: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to delete employee: {e}")

