# src/citrine_attendance/ui/dialogs/edit_employee_dialog.py
"""Dialog for editing an existing employee."""
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton,
    QMessageBox, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal
import re

from ...database import Employee

class EditEmployeeDialog(QDialog):
    """A dialog window for editing an existing employee."""
    employee_edited = pyqtSignal(dict)

    def __init__(self, employee: Employee, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.setWindowTitle(f"Edit Employee: {employee.first_name} {employee.last_name}")
        self.setModal(True)
        self.resize(450, 350)
        self.employee_to_edit = employee
        self.init_ui()
        self.populate_data()

    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        title_label = QLabel("Edit Employee Information")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.first_name_input = QLineEdit()
        form_layout.addRow("First Name*:", self.first_name_input)

        self.last_name_input = QLineEdit()
        form_layout.addRow("Last Name:", self.last_name_input)

        self.email_input = QLineEdit()
        form_layout.addRow("Email*:", self.email_input)

        self.phone_input = QLineEdit()
        form_layout.addRow("Phone:", self.phone_input)

        self.employee_id_input = QLineEdit()
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
        self.save_button = QPushButton("Save Changes")
        self.save_button.clicked.connect(self.handle_save)
        self.save_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        self.first_name_input.setFocus()

    def populate_data(self):
        """Fill the form with the existing employee's data."""
        self.first_name_input.setText(self.employee_to_edit.first_name)
        self.last_name_input.setText(self.employee_to_edit.last_name or "")
        self.email_input.setText(self.employee_to_edit.email)
        self.phone_input.setText(self.employee_to_edit.phone or "")
        self.employee_id_input.setText(self.employee_to_edit.employee_id or "")
        self.notes_input.setPlainText(self.employee_to_edit.notes or "")
        # HEROIC FIX: Convert minutes from DB to hours for display
        leave_hours = (self.employee_to_edit.monthly_leave_allowance_minutes or 0) // 60
        self.leave_allowance_input.setValue(leave_hours)

    def handle_save(self):
        """Handle the 'Save Changes' button click."""
        first_name = self.first_name_input.text().strip()
        last_name = self.last_name_input.text().strip() or None
        email = self.email_input.text().strip().lower()
        phone = self.phone_input.text().strip() or None
        employee_id_field = self.employee_id_input.text().strip() or None
        notes = self.notes_input.toPlainText().strip() or None
        # HEROIC FIX: Value is now in hours
        leave_allowance_hours = self.leave_allowance_input.value()

        if not first_name or not email:
            QMessageBox.warning(self, "Validation Error", "First Name and Email are required.")
            return

        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            QMessageBox.warning(self, "Validation Error", "Please enter a valid email address.")
            return

        employee_data = {
            'employee_id': self.employee_to_edit.id,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone': phone,
            'employee_id_field': employee_id_field,
            'notes': notes,
            # HEROIC FIX: Pass hours to the signal
            'monthly_leave_allowance_hours': leave_allowance_hours
        }
        self.employee_edited.emit(employee_data)