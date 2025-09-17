# src/citrine_attendance/ui/dialogs/add_attendance_dialog.py
import logging
from datetime import date, time, datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QPushButton, QMessageBox, QApplication, QDateEdit, QTextEdit
)
from PyQt6.QtCore import Qt, QDate, QTime, pyqtSignal
from ...services.employee_service import employee_service
from ...services.attendance_service import attendance_service, AttendanceAlreadyExistsError, LeaveBalanceExceededError
from ...services.audit_service import audit_service
from ...database import get_db_session, Attendance
from ..widgets.custom_time_edit import CustomTimeEdit
from ..widgets.jalali_date_edit import JalaliDateEdit
from ...locale import _
import jdatetime

class AttendanceDialogBase(QDialog):
    """Base dialog for adding or editing an attendance record."""
    def __init__(self, parent=None, record=None, employee_id=None, default_date=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.record = record
        self.employee_id = employee_id if employee_id is not None else (record.employee_id if record else None)
        self.default_date = default_date if default_date is not None else (record.date if record else date.today())
        self.current_user = parent.current_user if hasattr(parent, 'current_user') else None
        self.db_session = None
        self.employees = []

        self.init_ui()
        self.load_employees()
        self.update_jalali_label()

        if self.record:
            self.populate_data()
        else:
            self.set_defaults()

    def init_ui(self):
        if QApplication.instance().layoutDirection() == Qt.LayoutDirection.RightToLeft:
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        title_key = "attendance_edit_dialog_title" if self.record else "attendance_add_dialog_title"
        self.setWindowTitle(_(title_key))
        title_label = QLabel(_(title_key))
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.employee_combo = QComboBox()
        self.employee_combo.setMinimumWidth(250)
        # HEROIC CHANGE: Disable employee combo in edit mode
        if isinstance(self, EditAttendanceDialog):
            self.employee_combo.setEnabled(False)
        form_layout.addRow(_("attendance_add_dialog_employee"), self.employee_combo)
        
        date_layout = QHBoxLayout()
        self.date_edit = JalaliDateEdit()
        self.date_edit.dateChanged.connect(self.update_jalali_label)
        self.jalali_label = QLabel()
        date_layout.addWidget(self.date_edit)
        date_layout.addWidget(self.jalali_label)
        date_layout.addStretch()
        form_layout.addRow(_("attendance_add_dialog_date"), date_layout)
        
        self.time_in_edit = CustomTimeEdit()
        form_layout.addRow(_("attendance_add_dialog_time_in"), self.time_in_edit)
        
        self.time_out_edit = CustomTimeEdit()
        form_layout.addRow(_("attendance_add_dialog_time_out"), self.time_out_edit)

        self.leave_start_edit = CustomTimeEdit()
        form_layout.addRow(_("hourly_leave_start"), self.leave_start_edit)

        self.leave_end_edit = CustomTimeEdit()
        form_layout.addRow(_("hourly_leave_end"), self.leave_end_edit)
        
        self.note_edit = QTextEdit()
        form_layout.addRow(_("attendance_add_dialog_note"), self.note_edit)
        
        layout.addLayout(form_layout)
        
        button_layout = QHBoxLayout()
        button_key = "save" if self.record else "attendance_add_dialog_add_record"
        self.action_button = QPushButton(_(button_key))
        self.action_button.clicked.connect(self.handle_action)
        self.cancel_button = QPushButton(_("cancel"))
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.action_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

    def load_employees(self):
        try:
            self.db_session = next(get_db_session())
            self.employees = employee_service.get_all_employees(db=self.db_session)
            self.employee_combo.clear()
            self.employee_combo.addItem(_("--- Select an Employee ---"), None)
            for emp in self.employees:
                display_name = f"{emp.first_name} {emp.last_name}".strip() or emp.email
                self.employee_combo.addItem(display_name, emp.id)
        except Exception as e:
            self.logger.error(f"Error loading employees: {e}", exc_info=True)
        finally:
            if self.db_session: self.db_session.close()

    def set_defaults(self):
        """Set default values for a new record."""
        if self.employee_id:
            index = self.employee_combo.findData(self.employee_id)
            if index != -1: self.employee_combo.setCurrentIndex(index)
        self.date_edit.setDate(QDate(self.default_date.year, self.default_date.month, self.default_date.day))

    def populate_data(self):
        """Fill the dialog with existing record data for editing."""
        if not self.record: return
        index = self.employee_combo.findData(self.record.employee_id)
        if index != -1: self.employee_combo.setCurrentIndex(index)
        self.date_edit.setDate(QDate.fromString(str(self.record.date), "yyyy-MM-dd"))
        if self.record.time_in: self.time_in_edit.setTime(QTime.fromString(str(self.record.time_in), "HH:mm:ss"))
        if self.record.time_out: self.time_out_edit.setTime(QTime.fromString(str(self.record.time_out), "HH:mm:ss"))
        if self.record.leave_start: self.leave_start_edit.setTime(QTime.fromString(str(self.record.leave_start), "HH:mm:ss"))
        if self.record.leave_end: self.leave_end_edit.setTime(QTime.fromString(str(self.record.leave_end), "HH:mm:ss"))
        self.note_edit.setText(self.record.note or "")

    def update_jalali_label(self):
        qdate = self.date_edit.date()
        if not qdate.isNull():
            py_date = qdate.toPyDate()
            jalali_date = jdatetime.date.fromgregorian(date=py_date)
            self.jalali_label.setText(jalali_date.strftime("%Y/%m/%d"))

    def get_record_data(self):
        emp_id = self.employee_combo.currentData()
        if emp_id is None:
            QMessageBox.warning(self, _("employee_validation_error"), _("dashboard_please_select_employee"))
            return None
        
        def qtime_to_pytime(qtime_edit):
            qtime = qtime_edit.time()
            return qtime.toPyTime() if qtime != QTime(0, 0) else None

        return {
            'employee_id': emp_id,
            'date': self.date_edit.date().toPyDate(),
            'time_in': qtime_to_pytime(self.time_in_edit),
            'time_out': qtime_to_pytime(self.time_out_edit),
            'leave_start': qtime_to_pytime(self.leave_start_edit),
            'leave_end': qtime_to_pytime(self.leave_end_edit),
            'note': self.note_edit.toPlainText().strip() or None,
            'created_by': self.current_user.username if self.current_user else 'system'
        }
    
    def handle_action(self):
        raise NotImplementedError("This method should be implemented by subclasses.")


class AddAttendanceDialog(AttendanceDialogBase):
    """Dialog for adding a new attendance record."""
    record_added = pyqtSignal()
    
    def __init__(self, parent=None, employee_id=None, default_date=None):
        super().__init__(parent, record=None, employee_id=employee_id, default_date=default_date)

    def handle_action(self):
        record_data = self.get_record_data()
        if record_data:
            try:
                new_record = attendance_service.add_manual_attendance(**record_data)
                if self.current_user:
                    audit_service.log_action("attendance", new_record.id, "create", {k: str(v) for k, v in record_data.items()}, self.current_user.username)
                self.record_added.emit()
                self.accept()
            except (AttendanceAlreadyExistsError, LeaveBalanceExceededError) as e:
                 QMessageBox.warning(self, _("error"), str(e))
            except Exception as e:
                 self.logger.error(f"Error adding record: {e}", exc_info=True)
                 QMessageBox.critical(self, _("dashboard_error"), _("error_adding_record", error=e))


class EditAttendanceDialog(AttendanceDialogBase):
    """Dialog for editing an existing attendance record."""
    record_updated = pyqtSignal(int, dict)
    
    def __init__(self, record: Attendance, parent=None):
        super().__init__(parent, record=record)

    def handle_action(self):
        record_data = self.get_record_data()
        if record_data:
            self.record_updated.emit(self.record.id, record_data)
            self.accept()