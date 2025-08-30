# src/citrine_attendance/ui/views/settings_view.py
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QComboBox,
    QPushButton, QMessageBox, QSpinBox, QTextEdit, QTabWidget, QGroupBox, QLineEdit
)
from PyQt6.QtCore import Qt, QTime
from ...config import config
from ...services.user_service import user_service, UserServiceError
from ...database import User, get_db_session
from ...locale import _
from ..widgets.custom_time_edit import CustomTimeEdit

class SettingsView(QWidget):
    def __init__(self, current_user, main_window_ref=None):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.main_window = main_window_ref
        self.init_ui()
        self.populate_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        title_label = QLabel(_("settings_title"))
        title_label.setObjectName("viewTitle")
        main_layout.addWidget(title_label)
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, 1)

        self.create_general_tab()
        self.create_backups_tab()
        self.create_users_tab()
        self.create_audit_log_tab()
        
        self.save_button = QPushButton(_("settings_save_button"))
        self.save_button.clicked.connect(self.save_settings)
        main_layout.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignRight)

        self.load_users_list()
        self.load_audit_log()

    def create_general_tab(self):
        self.general_tab = QWidget()
        general_layout = QFormLayout(self.general_tab)
        
        self.language_combo = QComboBox()
        self.language_combo.addItems(["English", "Persian (فارسی)"])
        self.language_combo.setItemData(0, "en")
        self.language_combo.setItemData(1, "fa")
        general_layout.addRow(_("settings_language"), self.language_combo)

        self.date_format_combo = QComboBox()
        self.date_format_combo.addItems(["Jalali and Gregorian", "Jalali Only", "Gregorian Only"])
        self.date_format_combo.setItemData(0, "both")
        self.date_format_combo.setItemData(1, "jalali")
        self.date_format_combo.setItemData(2, "gregorian")
        general_layout.addRow(_("settings_date_format"), self.date_format_combo)
        
        self.workday_hours_spinbox = QSpinBox()
        self.workday_hours_spinbox.setRange(1, 24)
        general_layout.addRow("Workday Duration (hours):", self.workday_hours_spinbox)

        # --- New Launch Time Settings ---
        self.launch_start_edit = CustomTimeEdit()
        general_layout.addRow(_("settings_launch_start"), self.launch_start_edit)
        
        self.launch_end_edit = CustomTimeEdit()
        general_layout.addRow(_("settings_launch_end"), self.launch_end_edit)

        self.late_threshold_edit = CustomTimeEdit()
        general_layout.addRow("Late Threshold:", self.late_threshold_edit)

        self.tabs.addTab(self.general_tab, _("settings_general_tab"))

    def create_backups_tab(self):
        # Unchanged, but kept for context
        self.backup_tab = QWidget()
        backup_form = QFormLayout(self.backup_tab)
        self.backup_freq_spinbox = QSpinBox()
        self.backup_freq_spinbox.setRange(0, 365)
        backup_form.addRow(_("settings_backup_frequency"), self.backup_freq_spinbox)
        self.backup_retention_spinbox = QSpinBox()
        self.backup_retention_spinbox.setRange(1, 1000)
        backup_form.addRow(_("settings_backup_retention"), self.backup_retention_spinbox)
        self.tabs.addTab(self.backup_tab, _("settings_backups_tab"))

    def create_users_tab(self):
        # Unchanged, but kept for context
        self.users_tab = QWidget()
        users_layout = QVBoxLayout(self.users_tab)
        add_user_group = QGroupBox(_("settings_add_user_group"))
        add_user_layout = QFormLayout(add_user_group)
        self.new_username_edit = QLineEdit()
        add_user_layout.addRow(_("settings_new_username"), self.new_username_edit)
        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        add_user_layout.addRow(_("settings_new_password"), self.new_password_edit)
        self.new_role_combo = QComboBox()
        self.new_role_combo.addItems(["Operator", "Admin"])
        self.new_role_combo.setItemData(0, "operator")
        self.new_role_combo.setItemData(1, "admin")
        add_user_layout.addRow(_("settings_new_role"), self.new_role_combo)
        self.add_user_button = QPushButton(_("settings_add_user_button"))
        self.add_user_button.clicked.connect(self.add_new_user)
        add_user_layout.addRow(self.add_user_button)
        existing_users_group = QGroupBox(_("settings_existing_users"))
        existing_users_layout = QVBoxLayout(existing_users_group)
        self.users_list_text = QTextEdit()
        self.users_list_text.setReadOnly(True)
        self.refresh_users_button = QPushButton(_("settings_refresh_user_list"))
        self.refresh_users_button.clicked.connect(self.load_users_list)
        existing_users_layout.addWidget(self.users_list_text, 1)
        existing_users_layout.addWidget(self.refresh_users_button)
        users_layout.addWidget(add_user_group)
        users_layout.addWidget(existing_users_group)
        self.tabs.addTab(self.users_tab, _("settings_users_tab"))

    def create_audit_log_tab(self):
        # Unchanged, but kept for context
        self.audit_tab = QWidget()
        audit_layout = QVBoxLayout(self.audit_tab)
        audit_layout.addWidget(QLabel(_("settings_audit_log_header")))
        self.audit_log_text = QTextEdit()
        self.audit_log_text.setReadOnly(True)
        audit_layout.addWidget(self.audit_log_text, 1)
        self.refresh_audit_button = QPushButton(_("settings_refresh_audit_log"))
        self.refresh_audit_button.clicked.connect(self.load_audit_log)
        audit_layout.addWidget(self.refresh_audit_button)
        self.tabs.addTab(self.audit_tab, _("settings_audit_log_tab"))

    def populate_settings(self):
        settings = config.settings
        self.language_combo.setCurrentIndex(self.language_combo.findData(settings.get("language", "en")))
        self.date_format_combo.setCurrentIndex(self.date_format_combo.findData(settings.get("date_format", "both")))
        self.workday_hours_spinbox.setValue(settings.get("workday_hours", 8))
        self.launch_start_edit.setTime(QTime.fromString(settings.get("default_launch_start_time", "12:30"), "HH:mm"))
        self.launch_end_edit.setTime(QTime.fromString(settings.get("default_launch_end_time", "13:30"), "HH:mm"))
        self.late_threshold_edit.setTime(QTime.fromString(settings.get("late_threshold_time", "10:00"), "HH:mm"))
        self.backup_freq_spinbox.setValue(settings.get("backup_frequency_days", 1))
        self.backup_retention_spinbox.setValue(settings.get("backup_retention_count", 10))

    def save_settings(self):
        try:
            config.update_setting("language", self.language_combo.currentData())
            config.update_setting("date_format", self.date_format_combo.currentData())
            config.update_setting("workday_hours", self.workday_hours_spinbox.value())
            config.update_setting("default_launch_start_time", self.launch_start_edit.time().toString("HH:mm"))
            config.update_setting("default_launch_end_time", self.launch_end_edit.time().toString("HH:mm"))
            config.update_setting("late_threshold_time", self.late_threshold_edit.time().toString("HH:mm"))
            config.update_setting("backup_frequency_days", self.backup_freq_spinbox.value())
            config.update_setting("backup_retention_count", self.backup_retention_spinbox.value())
            
            QMessageBox.information(self, "Settings Saved", _("settings_saved_message"))
            
            if QMessageBox.question(self, _("settings_restart_required_title"), _("settings_restart_required_message")) == QMessageBox.StandardButton.Yes:
                if self.main_window: self.main_window.close()
        except Exception as e:
            QMessageBox.critical(self, _("settings_save_error"), str(e))

    # Other methods (add_new_user, load_users_list, load_audit_log) remain the same...
    def add_new_user(self):
        # This method is unchanged
        if self.current_user.role != "admin":
            QMessageBox.warning(self, "Access Denied", "Only admins can add users.")
            return
        username = self.new_username_edit.text().strip()
        password = self.new_password_edit.text()
        role = self.new_role_combo.currentData()
        if not username or not password:
            QMessageBox.warning(self, "Input Error", "Username and password are required.")
            return
        try:
            user_service.create_user(username, password, role)
            QMessageBox.information(self, "Success", f"User '{username}' created.")
            self.new_username_edit.clear()
            self.new_password_edit.clear()
            self.load_users_list()
        except UserServiceError as e:
            QMessageBox.critical(self, "Error", str(e))

    def load_users_list(self):
        # This method is unchanged
        if self.current_user.role != "admin":
            self.tabs.setTabEnabled(self.tabs.indexOf(self.users_tab), False)
            return
        db = next(get_db_session())
        try:
            users = db.query(User).all()
            self.users_list_text.setPlainText("\n".join([f"{user.username} ({user.role})" for user in users]))
        finally:
            db.close()

    def load_audit_log(self):
        # This method is unchanged
        if self.current_user.role != "admin":
            self.tabs.setTabEnabled(self.tabs.indexOf(self.audit_tab), False)
            return
        from ...database import AuditLog
        db = next(get_db_session())
        try:
            entries = db.query(AuditLog).order_by(AuditLog.performed_at.desc()).limit(100).all()
            self.audit_log_text.setPlainText("\n".join([f"{e.performed_at} | {e.performed_by} | {e.action} on {e.table_name}:{e.record_id}" for e in entries]))
        finally:
            db.close()