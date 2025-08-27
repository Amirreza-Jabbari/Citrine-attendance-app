# src/citrine_attendance/ui/dialogs/edit_employee_dialog.py
"""Dialog for editing an existing employee."""
import sys
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton,
    QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
import re

from ...database import Employee # Import Employee model to pass data
from ...services.employee_service import EmployeeServiceError, EmployeeAlreadyExistsError


class EditEmployeeDialog(QDialog):
    """A dialog window for editing an existing employee."""

    # Signal emitted when an employee is successfully edited
    employee_edited = pyqtSignal(object) # Emits the updated employee data dict

    def __init__(self, employee: Employee, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.employee_to_edit = employee # Store the Employee object to edit
        self.setWindowTitle(f"Edit Employee - {employee.first_name} {employee.last_name}")
        self.setModal(True)
        self.resize(400, 300)

        self.init_ui()
        self.populate_fields() # Fill fields with existing data

    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        title_label = QLabel("Edit Employee")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Fields (same as Add dialog)
        self.first_name_input = QLineEdit()
        self.first_name_input.setPlaceholderText("e.g., Ali")
        form_layout.addRow("First Name*:", self.first_name_input)

        self.last_name_input = QLineEdit()
        self.last_name_input.setPlaceholderText("e.g., Rezaei")
        form_layout.addRow("Last Name:", self.last_name_input)

        # Email is usually not editable, but let's allow it with a warning in the UI
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("e.g., ali.rezaei@example.com")
        # Make email read-only initially, add a button to unlock if needed
        self.email_input.setReadOnly(True)
        self.unlock_email_btn = QPushButton("Unlock")
        self.unlock_email_btn.setFixedWidth(80)
        self.unlock_email_btn.clicked.connect(self.unlock_email)
        email_layout = QHBoxLayout()
        email_layout.addWidget(self.email_input)
        email_layout.addWidget(self.unlock_email_btn)
        form_layout.addRow("Email*:", email_layout)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("e.g., +98 21 1234 5678")
        form_layout.addRow("Phone:", self.phone_input)

        self.employee_id_input = QLineEdit()
        self.employee_id_input.setPlaceholderText("Optional custom ID")
        form_layout.addRow("Employee ID:", self.employee_id_input)

        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(80)
        form_layout.addRow("Notes:", self.notes_input)

        layout.addLayout(form_layout)

        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save Changes")
        self.save_button.clicked.connect(self.handle_save)
        self.save_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

    def populate_fields(self):
        """Fill the input fields with the data from the employee object."""
        if self.employee_to_edit:
            self.first_name_input.setText(self.employee_to_edit.first_name or "")
            self.last_name_input.setText(self.employee_to_edit.last_name or "")
            self.email_input.setText(self.employee_to_edit.email or "")
            self.phone_input.setText(self.employee_to_edit.phone or "")
            self.employee_id_input.setText(self.employee_to_edit.employee_id or "")
            self.notes_input.setPlainText(self.employee_to_edit.notes or "")

    def unlock_email(self):
        """Allow editing the email field."""
        reply = QMessageBox.question(
            self, "Confirm Unlock",
            "Changing the email address can cause conflicts if another employee uses the same email. Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.email_input.setReadOnly(False)
            self.email_input.setFocus()
            self.email_input.selectAll()
            self.unlock_email_btn.setEnabled(False) # Disable button after unlock

    def handle_save(self):
        """Handle the 'Save Changes' button click."""
        first_name = self.first_name_input.text().strip()
        last_name = self.last_name_input.text().strip() or None
        email = self.email_input.text().strip().lower()
        phone = self.phone_input.text().strip() or None
        employee_id = self.employee_id_input.text().strip() or None
        notes = self.notes_input.toPlainText().strip() or None

        # --- Basic Validation ---
        if not first_name:
            QMessageBox.warning(self, "Validation Error", "First Name is required.")
            self.first_name_input.setFocus()
            return

        if not email:
            QMessageBox.warning(self, "Validation Error", "Email is required.")
            # Re-lock email if it was unlocked
            if not self.email_input.isReadOnly():
                self.email_input.setReadOnly(True)
                self.unlock_email_btn.setEnabled(True)
            self.email_input.setFocus()
            return

        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            QMessageBox.warning(self, "Validation Error", "Please enter a valid email address.")
            self.email_input.setFocus()
            return

        # --- Prepare data for update ---
        # Only include fields that have changed or are explicitly passed
        # This is important for the service update method
        employee_data = {
            'employee_id': self.employee_to_edit.id, # ID of the employee to update
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone': phone,
            'employee_id_field': employee_id, # Use different key to avoid conflict
            'notes': notes
        }

        # Emit the signal with the collected data
        self.employee_edited.emit(employee_data)

    # Dialog closing is handled by the parent view

# Example usage (if run directly for testing)
# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     # Mock employee data
#     from ...database import Employee
#     mock_emp = Employee(
#         id=1, first_name="John", last_name="Doe",
#         email="john.doe@example.com", phone="1234567890"
#     )
#     dialog = EditEmployeeDialog(mock_emp)
#     dialog.exec()
#     sys.exit(app.exec())