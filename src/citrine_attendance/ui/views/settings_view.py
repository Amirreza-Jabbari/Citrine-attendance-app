# src/citrine_attendance/ui/views/settings_view.py
import logging
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QPushButton, QMessageBox, QApplication, QFileDialog, QCheckBox,
    QLineEdit, QSpinBox, QTextEdit, QTabWidget, QGroupBox
)
from PyQt6.QtCore import Qt, QTime

from ...config import config
from ...services.user_service import user_service, UserServiceError
from ...database import User, get_db_session
from ...locale import _
from ..widgets.custom_time_edit import CustomTimeEdit

class SettingsView(QWidget):
    """The settings view widget, styled by the main window's stylesheet."""

    def __init__(self, current_user, main_window_ref=None):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.main_window = main_window_ref
        
        self.init_ui()
        self.populate_settings()

    def init_ui(self):
        """Initialize the settings view UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(25, 25, 25, 25)

        title_label = QLabel(_("settings_title"))
        title_label.setObjectName("viewTitle")
        main_layout.addWidget(title_label)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, 1)

        # --- Create Tabs ---
        self.create_general_tab()
        self.create_backups_tab()
        self.create_users_tab()
        self.create_audit_log_tab()

        # --- Save Button ---
        self.save_button = QPushButton(_("settings_save_button"))
        self.save_button.setObjectName("saveButton") # For specific styling
        self.save_button.clicked.connect(self.save_settings)
        main_layout.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignRight)

        # Initial data load for admin tabs
        self.load_users_list()
        self.load_audit_log()

    def create_general_tab(self):
        """Creates the General Settings tab."""
        self.general_tab = QWidget()
        general_layout = QFormLayout(self.general_tab)
        general_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("Persian (فارسی)", "fa")
        general_layout.addRow(_("settings_language"), self.language_combo)

        self.date_format_combo = QComboBox()
        self.date_format_combo.addItem("Jalali and Gregorian", "both")
        self.date_format_combo.addItem("Jalali Only", "jalali")
        self.date_format_combo.addItem("Gregorian Only", "gregorian")
        general_layout.addRow(_("settings_date_format"), self.date_format_combo)
        
        self.workday_hours_spinbox = QSpinBox()
        self.workday_hours_spinbox.setRange(1, 24)
        general_layout.addRow("Workday Duration (hours):", self.workday_hours_spinbox)

        self.launch_time_spinbox = QSpinBox()
        self.launch_time_spinbox.setRange(0, 240)
        general_layout.addRow("Default Launch Time (minutes):", self.launch_time_spinbox)

        self.late_threshold_edit = CustomTimeEdit()
        general_layout.addRow("Late Threshold:", self.late_threshold_edit)

        self.tabs.addTab(self.general_tab, _("settings_general_tab"))

    def create_backups_tab(self):
        """Creates the Backups Settings tab."""
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
        """Creates the User Management tab."""
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
        self.new_role_combo.addItem("Operator", "operator")
        self.new_role_combo.addItem("Admin", "admin")
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
        """Creates the Audit Log tab."""
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
        """Fill the UI controls with current settings from config."""
        settings = config.settings
        
        index = self.language_combo.findData(settings.get("language", "en"))
        if index >= 0: self.language_combo.setCurrentIndex(index)
        
        index = self.date_format_combo.findData(settings.get("date_format", "both"))
        if index >= 0: self.date_format_combo.setCurrentIndex(index)

        self.workday_hours_spinbox.setValue(settings.get("workday_hours", 8))
        self.launch_time_spinbox.setValue(settings.get("default_launch_time_minutes", 60))
        
        late_time_str = settings.get("late_threshold_time", "10:00")
        self.late_threshold_edit.setTime(QTime.fromString(late_time_str, "HH:mm"))

        self.backup_freq_spinbox.setValue(settings.get("backup_frequency_days", 1))
        self.backup_retention_spinbox.setValue(settings.get("backup_retention_count", 10))

    def save_settings(self):
        """Save the settings from the UI to the config file."""
        try:
            config.update_setting("language", self.language_combo.currentData())
            config.update_setting("date_format", self.date_format_combo.currentData())
            config.update_setting("workday_hours", self.workday_hours_spinbox.value())
            config.update_setting("default_launch_time_minutes", self.launch_time_spinbox.value())
            config.update_setting("late_threshold_time", self.late_threshold_edit.time().toString("HH:mm"))
            config.update_setting("backup_frequency_days", self.backup_freq_spinbox.value())
            config.update_setting("backup_retention_count", self.backup_retention_spinbox.value())

            QMessageBox.information(self, "Settings Saved", _("settings_saved_message"))
            self.logger.info("Settings saved by user.")

            reply = QMessageBox.question(
                self, _("settings_restart_required_title"),
                _("settings_restart_required_message"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes and self.main_window:
                self.main_window.close() # Or a more graceful restart method

        except Exception as e:
            self.logger.error(f"Error saving settings: {e}", exc_info=True)
            QMessageBox.critical(self, _("settings_save_error"), _("settings_failed_to_save", error=str(e)))

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
            user_service.create_user(username, password, role)
            QMessageBox.information(self, "Success", _("settings_user_created_success", username=username))
            self.new_username_edit.clear()
            self.new_password_edit.clear()
            self.load_users_list()
        except UserServiceError as e:
            QMessageBox.critical(self, "Error", _("settings_failed_to_create_user", error=str(e)))
    
    def load_users_list(self):
        """Load and display the list of users."""
        if self.current_user.role != "admin":
            self.tabs.setTabEnabled(self.tabs.indexOf(self.users_tab), False)
            return
        
        db = None
        try:
            db = next(get_db_session())
            users = db.query(User).all()
            user_lines = [f"{'Username':<20} {'Role':<15} {'Last Login'}"]
            user_lines.append("-" * 55)
            for user in users:
                last_login = user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else "Never"
                user_lines.append(f"{user.username:<20} {user.role:<15} {last_login}")
            self.users_list_text.setPlainText("\n".join(user_lines))
        except Exception as e:
            self.users_list_text.setPlainText(_("settings_error_loading_users", error=str(e)))
        finally:
            if db:
                db.close()

    def load_audit_log(self):
        """Load and display recent audit log entries."""
        if self.current_user.role != "admin":
            self.tabs.setTabEnabled(self.tabs.indexOf(self.audit_tab), False)
            return
        
        from ...database import AuditLog
        db = None
        try:
            db = next(get_db_session())
            entries = db.query(AuditLog).order_by(AuditLog.performed_at.desc()).limit(200).all()
            log_lines = [f"{'Timestamp':<25} {'User':<15} {'Action':<15} {'Details'}"]
            log_lines.append("-" * 80)
            for entry in entries:
                ts = entry.performed_at.strftime('%Y-%m-%d %H:%M:%S')
                details = f"Table: {entry.table_name}, ID: {entry.record_id}"
                log_lines.append(f"{ts:<25} {entry.performed_by:<15} {entry.action:<15} {details}")
            self.audit_log_text.setPlainText("\n".join(log_lines))
        except Exception as e:
            self.audit_log_text.setPlainText(_("settings_error_loading_audit_log", error=str(e)))
        finally:
            if db:
                db.close()

