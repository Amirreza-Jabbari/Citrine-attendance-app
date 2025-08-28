# src/citrine_attendance/ui/views/settings_view.py
import logging
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QPushButton, QMessageBox, QApplication, QFileDialog, QCheckBox,
    QLineEdit, QSpinBox, QTextEdit, QTabWidget, QGroupBox, QTimeEdit
)
from PyQt6.QtCore import Qt, QTime

from ...config import config
from ...services.user_service import user_service
from ...database import User
from ...locale import _


class SettingsView(QWidget):
    """The settings view widget."""

    def __init__(self, current_user, main_window_ref=None):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.main_window = main_window_ref
        
        self.init_ui()
        self.populate_settings()

    def init_ui(self):
        """Initialize the settings view UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)

        title_label = QLabel(_("settings_title"))
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # --- General Settings Tab ---
        self.general_tab = QWidget()
        general_layout = QVBoxLayout(self.general_tab)
        general_form = QFormLayout()

        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("Persian (فارسی)", "fa")
        general_form.addRow(_("settings_language"), self.language_combo)

        self.date_format_combo = QComboBox()
        self.date_format_combo.addItem("Jalali and Gregorian", "both")
        self.date_format_combo.addItem("Jalali Only", "jalali")
        self.date_format_combo.addItem("Gregorian Only", "gregorian")
        general_form.addRow(_("settings_date_format"), self.date_format_combo)
        
        # --- New Settings ---
        self.workday_hours_spinbox = QSpinBox()
        self.workday_hours_spinbox.setRange(1, 24)
        self.workday_hours_spinbox.setSuffix(" hours")
        general_form.addRow("Workday Duration:", self.workday_hours_spinbox)

        self.launch_time_spinbox = QSpinBox()
        self.launch_time_spinbox.setRange(0, 240)
        self.launch_time_spinbox.setSuffix(" minutes")
        general_form.addRow("Default Launch Time:", self.launch_time_spinbox)

        self.late_threshold_edit = QTimeEdit()
        self.late_threshold_edit.setDisplayFormat("HH:mm")
        general_form.addRow("Late Threshold:", self.late_threshold_edit)

        db_layout = QHBoxLayout()
        self.db_path_edit = QLineEdit()
        self.browse_db_btn = QPushButton(_("settings_browse"))
        self.browse_db_btn.clicked.connect(self.browse_db_path)
        db_layout.addWidget(self.db_path_edit)
        db_layout.addWidget(self.browse_db_btn)
        general_form.addRow(_("settings_db_path"), db_layout)
        
        general_layout.addLayout(general_form)
        general_layout.addStretch()
        self.tabs.addTab(self.general_tab, _("settings_general_tab"))

        # ... (Backup, Users, Audit tabs remain the same)
        # --- Backup Settings Tab ---
        self.backup_tab = QWidget()
        backup_layout = QVBoxLayout(self.backup_tab)

        backup_form = QFormLayout()
        self.backup_freq_spinbox = QSpinBox()
        self.backup_freq_spinbox.setRange(0, 365)
        self.backup_freq_spinbox.setValue(1)
        backup_form.addRow(_("settings_backup_frequency"), self.backup_freq_spinbox)

        self.backup_retention_spinbox = QSpinBox()
        self.backup_retention_spinbox.setRange(1, 1000)
        self.backup_retention_spinbox.setValue(10)
        backup_form.addRow(_("settings_backup_retention"), self.backup_retention_spinbox)

        self.backup_encrypt_checkbox = QCheckBox(_("settings_backup_encryption"))
        self.backup_encrypt_checkbox.setEnabled(False)
        backup_form.addRow(self.backup_encrypt_checkbox)

        backup_layout.addLayout(backup_form)
        backup_layout.addStretch()

        self.tabs.addTab(self.backup_tab, _("settings_backups_tab"))
        
        # --- User Management Tab (Admin Only) ---
        self.users_tab = QWidget()
        users_layout = QVBoxLayout(self.users_tab)

        self.add_user_group = QGroupBox(_("settings_add_user_group"))
        add_user_layout = QFormLayout(self.add_user_group)

        self.new_username_edit = QLineEdit()
        add_user_layout.addRow(_("settings_new_username"), self.new_username_edit)

        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        add_user_layout.addRow(_("settings_new_password"), self.new_password_edit)

        self.new_role_combo = QComboBox()
        self.new_role_combo.addItem("Operator", "operator")
        self.new_role_combo.addItem("Admin", "admin")
        add_user_layout.addRow(_("settings_new_role"), self.new_role_combo)

        self.add_user_button = QPushButton(_("settings_add_user_button"))
        self.add_user_button.clicked.connect(self.add_new_user)
        add_user_layout.addRow(self.add_user_button)

        users_layout.addWidget(self.add_user_group)
        self.users_list_text = QTextEdit()
        self.users_list_text.setReadOnly(True)
        users_layout.addWidget(self.users_list_text, 1)

        self.refresh_users_button = QPushButton(_("settings_refresh_user_list"))
        self.refresh_users_button.clicked.connect(self.load_users_list)
        users_layout.addWidget(self.refresh_users_button)

        self.tabs.addTab(self.users_tab, _("settings_users_tab"))

        # --- Audit Log Tab (Admin Only) ---
        self.audit_tab = QWidget()
        audit_layout = QVBoxLayout(self.audit_tab)
        self.audit_log_text = QTextEdit()
        self.audit_log_text.setReadOnly(True)
        audit_layout.addWidget(self.audit_log_text, 1)
        self.refresh_audit_button = QPushButton(_("settings_refresh_audit_log"))
        self.refresh_audit_button.clicked.connect(self.load_audit_log)
        audit_layout.addWidget(self.refresh_audit_button)
        self.tabs.addTab(self.audit_tab, _("settings_audit_log_tab"))


        # --- Save Button ---
        self.save_button = QPushButton(_("settings_save_button"))
        self.save_button.setStyleSheet("background-color: #11563a; color: white; padding: 10px; font-size: 16px;")
        self.save_button.clicked.connect(self.save_settings)
        layout.addWidget(self.save_button)

        self.load_users_list()
        self.load_audit_log()

    def populate_settings(self):
        """Fill the UI controls with current settings."""
        settings = config.settings

        # ... (Existing settings population) ...
        lang_code = settings.get("language", "en")
        index = self.language_combo.findData(lang_code)
        if index >= 0: self.language_combo.setCurrentIndex(index)
        
        date_fmt = settings.get("date_format", "both")
        index = self.date_format_combo.findData(date_fmt)
        if index >= 0: self.date_format_combo.setCurrentIndex(index)

        self.db_path_edit.setText(settings.get("db_path_override", ""))
        self.backup_freq_spinbox.setValue(settings.get("backup_frequency_days", 1))
        self.backup_retention_spinbox.setValue(settings.get("backup_retention_count", 10))
        self.backup_encrypt_checkbox.setChecked(settings.get("enable_backup_encryption", False))

        # Populate new settings
        self.workday_hours_spinbox.setValue(settings.get("workday_hours", 8))
        self.launch_time_spinbox.setValue(settings.get("default_launch_time_minutes", 60))
        
        late_time_str = settings.get("late_threshold_time", "10:00")
        self.late_threshold_edit.setTime(QTime.fromString(late_time_str, "HH:mm"))

    def browse_db_path(self):
        # ... (no changes here) ...
        current_path = self.db_path_edit.text() or str(config.user_data_dir)
        filename, _ = QFileDialog.getSaveFileName(self, "Select Database File", current_path, "SQLite Database (*.db)")
        if filename:
            self.db_path_edit.setText(str(Path(filename).resolve()))

    def save_settings(self):
        """Save the settings from the UI to the config."""
        try:
            # ... (Save existing settings) ...
            config.update_setting("language", self.language_combo.currentData())
            config.update_setting("date_format", self.date_format_combo.currentData())
            config.update_setting("db_path_override", self.db_path_edit.text().strip() or None)
            config.update_setting("backup_frequency_days", self.backup_freq_spinbox.value())
            config.update_setting("backup_retention_count", self.backup_retention_spinbox.value())
            config.update_setting("enable_backup_encryption", self.backup_encrypt_checkbox.isChecked())

            # Save new settings
            config.update_setting("workday_hours", self.workday_hours_spinbox.value())
            config.update_setting("default_launch_time_minutes", self.launch_time_spinbox.value())
            config.update_setting("late_threshold_time", self.late_threshold_edit.time().toString("HH:mm"))

            QMessageBox.information(self, "Settings Saved", _("settings_saved_message"))
            self.logger.info("Settings saved by user.")

            reply = QMessageBox.question(
                self, _("settings_restart_required_title"),
                _("settings_restart_required_message"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes and self.main_window:
                QApplication.instance().quit()

        except Exception as e:
            self.logger.error(f"Error saving settings: {e}", exc_info=True)
            QMessageBox.critical(self, _("settings_save_error"), _("settings_failed_to_save", error=e))

    # --- User Management & Audit Log (no changes here) ---
    def add_new_user(self):
        """Add a new user account."""
        if self.current_user.role != "admin":
            QMessageBox.warning(self, _("settings_access_denied"), _("settings_only_admins_add_users"))
            return

        username = self.new_username_edit.text().strip()
        password = self.new_password_edit.text()
        role = self.new_role_combo.currentData()

        if not username or not password:
            QMessageBox.warning(self, _("settings_input_error"), _("settings_username_password_required"))
            return

        try:
            db_session = user_service._get_session()
            user_service.create_user(username, password, role, db=db_session)
            db_session.close()
            QMessageBox.information(self, "Success", _("settings_user_created_success", username=username))
            self.new_username_edit.clear()
            self.new_password_edit.clear()
            self.load_users_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", _("settings_failed_to_create_user", error=e))
    
    def load_users_list(self):
        """Load and display the list of users."""
        if self.current_user.role != "admin":
            self.users_list_text.setPlainText(_("settings_access_restricted_to_admins"))
            self.add_user_group.setEnabled(False)
            self.refresh_users_button.setEnabled(False)
            return
        
        try:
            db_session = user_service._get_session()
            users = db_session.query(User).all()
            db_session.close()
            user_lines = [f"{'Username':<20} {'Role':<15} {'Last Login'}"]
            user_lines.append("-" * 50)
            for user in users:
                last_login = user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else "Never"
                user_lines.append(f"{user.username:<20} {user.role:<15} {last_login}")
            self.users_list_text.setPlainText("\n".join(user_lines))
        except Exception as e:
            self.users_list_text.setPlainText(_("settings_error_loading_users", error=e))

    def load_audit_log(self):
        """Load and display recent audit log entries."""
        if self.current_user.role != "admin":
            self.audit_log_text.setPlainText(_("settings_access_restricted_to_admins"))
            self.refresh_audit_button.setEnabled(False)
            return
        
        from ...database import AuditLog
        try:
            db_session = user_service._get_session()
            entries = db_session.query(AuditLog).order_by(AuditLog.performed_at.desc()).limit(200).all()
            db_session.close()
            log_lines = [f"{'Timestamp':<25} {'User':<15} {'Action':<15} {'Details'}"]
            log_lines.append("-" * 80)
            for entry in entries:
                ts = entry.performed_at.strftime('%Y-%m-%d %H:%M:%S')
                details = f"Table: {entry.table_name}, ID: {entry.record_id}"
                log_lines.append(f"{ts:<25} {entry.performed_by:<15} {entry.action:<15} {details}")
            self.audit_log_text.setPlainText("\n".join(log_lines))
        except Exception as e:
            self.audit_log_text.setPlainText(_("settings_error_loading_audit_log", error=e))