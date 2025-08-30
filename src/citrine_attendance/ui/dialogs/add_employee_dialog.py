# src/citrine_attendance/ui/dialogs/add_employee_dialog.py
"""Dialog for adding a new employee."""
import sys
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton,
    QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
import re # For email validation

# Import service error for specific handling
from ...services.employee_service import EmployeeServiceError, EmployeeAlreadyExistsError


class AddEmployeeDialog(QDialog):
    """A dialog window for adding a new employee."""

    # Signal emitted when an employee is successfully added
    employee_added = pyqtSignal(object) # Emits the Employee object

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.setWindowTitle("Add New Employee")
        self.setModal(True)
        # Set a reasonable size
        self.resize(400, 300)

        self.init_ui()

    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Title
        title_label = QLabel("Add New Employee")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        # Form Layout
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Fields
        self.first_name_input = QLineEdit()
        self.first_name_input.setPlaceholderText("e.g., Ali")
        form_layout.addRow("First Name*:", self.first_name_input)

        self.last_name_input = QLineEdit()
        self.last_name_input.setPlaceholderText("e.g., Rezaei")
        form_layout.addRow("Last Name:", self.last_name_input)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("e.g., ali.rezaei@example.com")
        form_layout.addRow("Email*:", self.email_input)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("e.g., +98 21 1234 5678")
        form_layout.addRow("Phone:", self.phone_input)

        self.employee_id_input = QLineEdit()
        self.employee_id_input.setPlaceholderText("Optional custom ID")
        form_layout.addRow("Employee ID:", self.employee_id_input)

        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(80) # Limit height
        form_layout.addRow("Notes:", self.notes_input)

        layout.addLayout(form_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.add_button = QPushButton("Add Employee")
        self.add_button.clicked.connect(self.handle_add)
        self.add_button.setDefault(True) # Enter key triggers this
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject) # Close dialog
        button_layout.addStretch()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        # Set focus to the first name field
        self.first_name_input.setFocus()

    def handle_add(self):
        """Handle the 'Add Employee' button click."""
        first_name = self.first_name_input.text().strip()
        last_name = self.last_name_input.text().strip() or None
        email = self.email_input.text().strip().lower() # Normalize email
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
            self.email_input.setFocus()
            return

        # Simple email regex (basic check)
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            QMessageBox.warning(self, "Validation Error", "Please enter a valid email address.")
            self.email_input.setFocus()
            return

        # --- Call the Model/Service to Add ---
        # The actual adding logic will be handled by the EmployeeModel or a controller
        # which will use the employee_service. For now, we emit a signal with the data.
        # The parent view (EmployeeView) will connect to this signal and perform the add.

        # Prepare data dictionary
        employee_data = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone': phone,
            'employee_id': employee_id,
            'notes': notes
        }

        # Emit the signal with the collected data
        self.employee_added.emit(employee_data)
        # The dialog will be closed by the parent view after successful addition
        # or kept open if there's an error.

    # The dialog closing (accept/reject) is handled by the parent view
    # based on the success of the operation triggered by employee_added signal.

# Example usage (if run directly for testing)
# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     dialog = AddEmployeeDialog()
#     # For testing, just show it
#     dialog.exec()
#     sys.exit(app.exec())