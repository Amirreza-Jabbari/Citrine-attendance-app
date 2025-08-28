# src/citrine_attendance/ui/dialogs/add_attendance_dialog.py
"""Dialog for adding a manual attendance record."""
import sys
import logging
from datetime import date, time, datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QPushButton, QMessageBox, QApplication, QDateEdit, QTextEdit
)
from PyQt6.QtCore import Qt, QDate, QTime, pyqtSignal

from ...services.employee_service import employee_service
from ...database import get_db_session
from ..widgets.custom_time_edit import CustomTimeEdit
from ...locale import _
import jdatetime


class AddAttendanceDialog(QDialog):
    """A dialog window for adding a manual attendance record."""

    record_added = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.setWindowTitle(_("attendance_add_dialog_title"))
        self.setModal(True)
        self.resize(450, 450)
        self.db_session = None
        self.employees = []

        self.init_ui()
        self.load_employees()
        self.update_jalali_label()

    def init_ui(self):
        """Initialize the dialog UI."""
        # Set layout direction based on current language
        if QApplication.instance().layoutDirection() == Qt.LayoutDirection.RightToLeft:
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        title_label = QLabel(_("attendance_add_dialog_title"))
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Employee
        self.employee_combo = QComboBox()
        self.employee_combo.setMinimumWidth(250)
        form_layout.addRow(_("attendance_add_dialog_employee"), self.employee_combo)

        # Date
        date_layout = QHBoxLayout()
        self.date_edit = QDateEdit(calendarPopup=True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(self.update_jalali_label)
        self.jalali_label = QLabel()
        self.jalali_label.setStyleSheet("font-size: 11px; color: gray; padding-left: 10px;")

        # Adjust order for RTL
        if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            date_layout.addWidget(self.jalali_label)
            date_layout.addWidget(self.date_edit)
        else:
            date_layout.addWidget(self.date_edit)
            date_layout.addWidget(self.jalali_label)
        date_layout.addStretch()
        form_layout.addRow(_("attendance_add_dialog_date"), date_layout)

        # Time In/Out
        self.time_in_edit = CustomTimeEdit()
        self.time_in_edit.setTime(QTime(9, 0))
        form_layout.addRow(_("attendance_add_dialog_time_in"), self.time_in_edit)

        self.time_out_edit = CustomTimeEdit()
        form_layout.addRow(_("attendance_add_dialog_time_out"), self.time_out_edit)

        # Launch Time Fields
        self.launch_start_edit = CustomTimeEdit()
        self.launch_start_edit.setTime(QTime(12, 30))
        form_layout.addRow(_("attendance_launch_start"), self.launch_start_edit)

        self.launch_end_edit = CustomTimeEdit()
        self.launch_end_edit.setTime(QTime(13, 30))
        form_layout.addRow(_("attendance_launch_end"), self.launch_end_edit)

        # Note
        self.note_edit = QTextEdit()
        self.note_edit.setMaximumHeight(80)
        form_layout.addRow(_("attendance_add_dialog_note"), self.note_edit)

        layout.addLayout(form_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.add_button = QPushButton(_("attendance_add_dialog_add_record"))
        self.add_button.clicked.connect(self.handle_add)
        self.add_button.setDefault(True)
        self.cancel_button = QPushButton(_("cancel"))
        self.cancel_button.clicked.connect(self.reject)

        # Adjust button order for LTR/RTL
        button_layout.addStretch()
        if self.layoutDirection() == Qt.LayoutDirection.LeftToRight:
            button_layout.addWidget(self.add_button)
            button_layout.addWidget(self.cancel_button)
        else:
            button_layout.addWidget(self.cancel_button)
            button_layout.addWidget(self.add_button)

        layout.addLayout(button_layout)

    def load_employees(self):
        """Load employees into the combo box."""
        try:
            session_gen = get_db_session()
            self.db_session = next(session_gen)
            self.employees = employee_service.get_all_employees(db=self.db_session)
            self.employee_combo.clear()
            self.employee_combo.addItem(_("--- Select an Employee ---"), None)
            for emp in self.employees:
                display_name = f"{emp.first_name} {emp.last_name}".strip() or emp.email
                self.employee_combo.addItem(display_name, emp.id)
        except Exception as e:
            self.logger.error(f"Error loading employees for dialog: {e}", exc_info=True)
            QMessageBox.critical(self, _("dashboard_error"), _("unexpected_error").format(error=e))
        finally:
            if self.db_session:
                self.db_session.close()
                self.db_session = None

    def update_jalali_label(self):
        """Update the label with the Jalali equivalent of the selected date."""
        qdate = self.date_edit.date()
        if not qdate.isNull():
            try:
                py_date = qdate.toPyDate()
                jalali_date = jdatetime.date.fromgregorian(date=py_date)
                # Use Persian digits for display
                digit_map = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
                day_str = str(jalali_date.day).translate(digit_map)
                month_name = jalali_date.j_months_fa[jalali_date.month - 1]
                year_str = str(jalali_date.year).translate(digit_map)
                self.jalali_label.setText(f"{day_str} {month_name} {year_str}")
            except Exception as e:
                self.logger.warning(f"Error converting date to Jalali: {e}")
                self.jalali_label.setText("")
        else:
            self.jalali_label.setText("")


    def handle_add(self):
        """Handle the 'Add Record' button click."""
        emp_id = self.employee_combo.currentData()
        if emp_id is None:
            QMessageBox.warning(self, _("employee_validation_error"), _("dashboard_please_select_employee"))
            return

        record_date = self.date_edit.date().toPyDate()

        def qtime_to_pytime(qtime_edit):
            qtime = qtime_edit.time()
            # Consider time as null only if it's midnight
            return qtime.toPyTime() if qtime != QTime(0, 0) else None

        time_in = qtime_to_pytime(self.time_in_edit)
        time_out = qtime_to_pytime(self.time_out_edit)
        launch_start = qtime_to_pytime(self.launch_start_edit)
        launch_end = qtime_to_pytime(self.launch_end_edit)

        note = self.note_edit.toPlainText().strip() or None

        record_data = {
            'employee_id': emp_id,
            'date': record_date,
            'time_in': time_in,
            'time_out': time_out,
            'launch_start': launch_start,
            'launch_end': launch_end,
            'note': note
        }

        self.record_added.emit(record_data)
        self.accept()