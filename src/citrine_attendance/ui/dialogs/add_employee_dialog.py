# src/citrine_attendance/ui/dialogs/add_employee_dialog.py
"""Dialog for adding a new employee."""
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton,
    QMessageBox, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal
import re

class AddEmployeeDialog(QDialog):
    """A dialog window for adding a new employee."""
    employee_added = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.setWindowTitle("Add New Employee")
        self.setModal(True)
        self.resize(450, 350)
        self.init_ui()

    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        title_label = QLabel("Add New Employee")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.first_name_input = QLineEdit(placeholderText="e.g., Ali")
        form_layout.addRow("First Name*:", self.first_name_input)

        self.last_name_input = QLineEdit(placeholderText="e.g., Rezaei")
        form_layout.addRow("Last Name:", self.last_name_input)

        self.email_input = QLineEdit(placeholderText="e.g., ali.rezaei@example.com")
        form_layout.addRow("Email*:", self.email_input)

        self.phone_input = QLineEdit(placeholderText="e.g., +98 21 1234 5678")
        form_layout.addRow("Phone:", self.phone_input)

        self.employee_id_input = QLineEdit(placeholderText="Optional custom ID")
        form_layout.addRow("Employee ID:", self.employee_id_input)

        # HEROIC FIX: Changed to hours with new range and suffix
        self.leave_allowance_input = QSpinBox()
        self.leave_allowance_input.setRange(0, 240)
        self.leave_allowance_input.setSuffix(" hours")
        form_layout.addRow("Monthly Leave Allowance:", self.leave_allowance_input)

        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(80)
        form_layout.addRow("Notes:", self.notes_input)
        layout.addLayout(form_layout)

        button_layout = QHBoxLayout()
        self.add_button = QPushButton("Add Employee")
        self.add_button.clicked.connect(self.handle_add)
        self.add_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        self.first_name_input.setFocus()

    def handle_add(self):
        """Handle the 'Add Employee' button click."""
        first_name = self.first_name_input.text().strip()
        last_name = self.last_name_input.text().strip() or None
        email = self.email_input.text().strip().lower()
        phone = self.phone_input.text().strip() or None
        employee_id = self.employee_id_input.text().strip() or None
        notes = self.notes_input.toPlainText().strip() or None
        # HEROIC FIX: Value is now in hours
        leave_allowance_hours = self.leave_allowance_input.value()

        if not first_name:
            QMessageBox.warning(self, "Validation Error", "First Name is required.")
            self.first_name_input.setFocus()
            return

        if not email:
            QMessageBox.warning(self, "Validation Error", "Email is required.")
            self.email_input.setFocus()
            return

        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            QMessageBox.warning(self, "Validation Error", "Please enter a valid email address.")
            self.email_input.setFocus()
            return

        employee_data = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone': phone,
            'employee_id': employee_id,
            'notes': notes,
            # HEROIC FIX: Pass hours to the signal
            'monthly_leave_allowance_hours': leave_allowance_hours
        }
        self.employee_added.emit(employee_data)