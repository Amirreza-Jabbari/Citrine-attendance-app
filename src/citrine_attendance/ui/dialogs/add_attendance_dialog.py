# src/citrine_attendance/ui/dialogs/add_attendance_dialog.py
"""Dialog for adding a manual attendance record."""
import sys
import logging
from datetime import date, time, datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QPushButton, QMessageBox, QApplication, QDateEdit, QTimeEdit, QTextEdit
)
from PyQt6.QtCore import Qt, QDate, QTime, pyqtSignal

from ...services.employee_service import employee_service
from ...database import get_db_session


class AddAttendanceDialog(QDialog):
    """A dialog window for adding a manual attendance record."""

    # Signal emitted when a record is successfully added
    record_added = pyqtSignal(object) # Emits the added record data dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.setWindowTitle("Add Manual Attendance Record")
        self.setModal(True)
        self.resize(400, 350)
        self.db_session = None
        self.employees = [] # List of Employee objects

        self.init_ui()
        self.load_employees()

    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        title_label = QLabel("Add Manual Attendance Record")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Employee selection
        self.employee_combo = QComboBox()
        self.employee_combo.setMinimumWidth(200)
        form_layout.addRow("Employee*:", self.employee_combo)

        # Date
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate()) # Default to today
        form_layout.addRow("Date*:", self.date_edit)

        # Time In
        self.time_in_edit = QTimeEdit()
        self.time_in_edit.setDisplayFormat("HH:mm")
        # Set default time in to 09:00
        self.time_in_edit.setTime(QTime(9, 0))
        form_layout.addRow("Time In:", self.time_in_edit)

        # Time Out
        self.time_out_edit = QTimeEdit()
        self.time_out_edit.setDisplayFormat("HH:mm")
        # Leave time out empty initially, or set a default like 17:00
        # self.time_out_edit.setTime(QTime(17, 0))
        # To make it truly optional, we can leave it as is (00:00) and handle it in the model/service
        # Or clear it explicitly
        self.time_out_edit.setTime(QTime(0, 0)) # Will be treated as None if not changed
        form_layout.addRow("Time Out:", self.time_out_edit)

        # Note
        self.note_edit = QTextEdit()
        self.note_edit.setMaximumHeight(80)
        form_layout.addRow("Note:", self.note_edit)

        layout.addLayout(form_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.add_button = QPushButton("Add Record")
        self.add_button.clicked.connect(self.handle_add)
        self.add_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

    def load_employees(self):
        """Load employees into the combo box."""
        try:
            session_gen = get_db_session()
            self.db_session = next(session_gen)
            self.employees = employee_service.get_all_employees(db=self.db_session)
            self.employee_combo.clear()
            self.employee_combo.addItem("--- Select an Employee ---", None)
            for emp in self.employees:
                display_name = f"{emp.first_name} {emp.last_name}".strip() or emp.email
                self.employee_combo.addItem(display_name, emp.id)
        except Exception as e:
            self.logger.error(f"Error loading employees for dialog: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Could not load employees: {e}")
        finally:
            if self.db_session:
                self.db_session.close()
                self.db_session = None

    def handle_add(self):
        """Handle the 'Add Record' button click."""
        emp_id = self.employee_combo.currentData()
        if emp_id is None:
            QMessageBox.warning(self, "Validation Error", "Please select an employee.")
            self.employee_combo.setFocus()
            return

        qdate = self.date_edit.date()
        if qdate.isNull():
            QMessageBox.warning(self, "Validation Error", "Please select a date.")
            self.date_edit.setFocus()
            return
        record_date = qdate.toPyDate()

        # Get time in/out. If time is 00:00, treat as None (optional).
        time_in_qtime = self.time_in_edit.time()
        time_in = time_in_qtime.toPyTime() if not (time_in_qtime.hour() == 0 and time_in_qtime.minute() == 0) else None

        time_out_qtime = self.time_out_edit.time()
        time_out = time_out_qtime.toPyTime() if not (time_out_qtime.hour() == 0 and time_out_qtime.minute() == 0) else None

        note = self.note_edit.toPlainText().strip() or None

        # Prepare data dictionary
        record_data = {
            'employee_id': emp_id,
            'date': record_date,
            'time_in': time_in,
            'time_out': time_out,
            'note': note
        }

        # Emit the signal with the collected data
        self.record_added.emit(record_data)

    # Dialog closing is handled by the parent view

# Example usage (if run directly for testing)
# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     from ...database import init_db
#     init_db()
#     dialog = AddAttendanceDialog()
#     dialog.exec()
#     sys.exit(app.exec())