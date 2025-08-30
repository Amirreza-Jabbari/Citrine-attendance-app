from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QMessageBox
from citrine_attendance.services.employee_service import EmployeeService

class EditEmployeeDialog(QDialog):
    def __init__(self, employee_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Employee")
        self.employee_id = employee_id
        self.employee_service = EmployeeService()

        # Fetch employee details
        employee = self.employee_service.get_employee_by_id(self.employee_id)

        self.layout = QVBoxLayout()

        self.name_label = QLabel("Name:")
        self.name_input = QLineEdit()
        self.name_input.setText(employee.name)
        self.layout.addWidget(self.name_label)
        self.layout.addWidget(self.name_input)

        self.group_label = QLabel("Group:")
        self.group_input = QLineEdit()
        self.group_input.setText(employee.group)
        self.layout.addWidget(self.group_label)
        self.layout.addWidget(self.group_input)

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_employee)
        self.layout.addWidget(self.save_button)

        self.setLayout(self.layout)

    def save_employee(self):
        name = self.name_input.text()
        group = self.group_input.text()
        if name and group:
            self.employee_service.update_employee(self.employee_id, name, group)
            self.accept()
        else:
            QMessageBox.warning(self, "Input Error", "Name and group cannot be empty.")