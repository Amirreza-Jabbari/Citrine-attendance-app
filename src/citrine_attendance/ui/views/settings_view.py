# src/citrine_attendance/ui/views/settings_view.py
"""View for application settings and user management."""
import logging
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QPushButton, QMessageBox, QApplication, QFileDialog, QCheckBox,
    QLineEdit, QSpinBox, QTextEdit, QTabWidget, QGroupBox, QStyle
)
from PyQt6.QtCore import Qt

from ...config import config
from ...services.user_service import user_service, UserServiceError
from ...database import get_db_session, User


class SettingsView(QWidget):
    """The settings view widget."""

    def __init__(self, current_user, main_window_ref=None):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.main_window = main_window_ref # Reference to trigger restart if needed
        self.db_session = None

        self.init_ui()
        self.populate_settings()

    def init_ui(self):
        """Initialize the settings view UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)

        title_label = QLabel("Application Settings")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)

        # --- Use Tabs for Organization ---
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1) # Stretch to fill

        # --- General Settings Tab ---
        self.general_tab = QWidget()
        general_layout = QVBoxLayout(self.general_tab)

        general_form = QFormLayout()
        # Language
        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("Persian (فارسی)", "fa")
        general_form.addRow("Language:", self.language_combo)

        # Date Format
        self.date_format_combo = QComboBox()
        self.date_format_combo.addItem("Jalali and Gregorian", "both")
        self.date_format_combo.addItem("Jalali Only", "jalali")
        self.date_format_combo.addItem("Gregorian Only", "gregorian")
        general_form.addRow("Date Format:", self.date_format_combo)

        # DB Path Override
        db_layout = QHBoxLayout()
        self.db_path_edit = QLineEdit()
        self.db_path_edit.setPlaceholderText("Leave blank to use default location")
        self.browse_db_btn = QPushButton("Browse...")
        self.browse_db_btn.clicked.connect(self.browse_db_path)
        db_layout.addWidget(self.db_path_edit)
        db_layout.addWidget(self.browse_db_btn)
        general_form.addRow("Database Path (Override):", db_layout)

        general_layout.addLayout(general_form)
        general_layout.addStretch()

        self.tabs.addTab(self.general_tab, "General")

        # --- Backup Settings Tab ---
        self.backup_tab = QWidget()
        backup_layout = QVBoxLayout(self.backup_tab)

        backup_form = QFormLayout()
        # Backup Frequency (days)
        self.backup_freq_spinbox = QSpinBox()
        self.backup_freq_spinbox.setRange(0, 365) # 0 = disabled?
        self.backup_freq_spinbox.setValue(1) # Default daily
        backup_form.addRow("Backup Frequency (Days):", self.backup_freq_spinbox)

        # Backup Retention
        self.backup_retention_spinbox = QSpinBox()
        self.backup_retention_spinbox.setRange(1, 1000)
        self.backup_retention_spinbox.setValue(10) # Default keep 10
        backup_form.addRow("Keep Last N Backups:", self.backup_retention_spinbox)

        # Backup Encryption
        self.backup_encrypt_checkbox = QCheckBox("Enable Backup Encryption (requires password)")
        self.backup_encrypt_checkbox.setEnabled(False) # Feature placeholder
        backup_form.addRow(self.backup_encrypt_checkbox)

        backup_layout.addLayout(backup_form)
        backup_layout.addStretch()

        self.tabs.addTab(self.backup_tab, "Backups")

        # --- User Management Tab (Admin Only) ---
        self.users_tab = QWidget()
        users_layout = QVBoxLayout(self.users_tab)

        self.users_info_label = QLabel("Manage user accounts. Only Admins can create/delete users.")
        users_layout.addWidget(self.users_info_label)

        # Add User Form
        self.add_user_group = QGroupBox("Add New User")
        add_user_layout = QFormLayout(self.add_user_group)

        self.new_username_edit = QLineEdit()
        add_user_layout.addRow("Username:", self.new_username_edit)

        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        add_user_layout.addRow("Password:", self.new_password_edit)

        self.new_role_combo = QComboBox()
        self.new_role_combo.addItem("Operator", "operator")
        self.new_role_combo.addItem("Admin", "admin")
        add_user_layout.addRow("Role:", self.new_role_combo)

        self.add_user_button = QPushButton("Add User")
        self.add_user_button.clicked.connect(self.add_new_user)
        add_user_layout.addRow(self.add_user_button)

        users_layout.addWidget(self.add_user_group)

        # User List/Management (Placeholder - could be a table)
        self.users_list_label = QLabel("Existing Users:")
        users_layout.addWidget(self.users_list_label)
        self.users_list_text = QTextEdit()
        self.users_list_text.setReadOnly(True)
        users_layout.addWidget(self.users_list_text, 1) # Stretch

        self.refresh_users_button = QPushButton("Refresh User List")
        self.refresh_users_button.clicked.connect(self.load_users_list)
        users_layout.addWidget(self.refresh_users_button)

        self.tabs.addTab(self.users_tab, "Users")

        # --- Audit Log Tab (Admin Only) ---
        self.audit_tab = QWidget()
        audit_layout = QVBoxLayout(self.audit_tab)
        audit_layout.addWidget(QLabel("Recent Audit Log Entries:"))
        self.audit_log_text = QTextEdit()
        self.audit_log_text.setReadOnly(True)
        audit_layout.addWidget(self.audit_log_text, 1) # Stretch
        self.refresh_audit_button = QPushButton("Refresh Audit Log")
        self.refresh_audit_button.clicked.connect(self.load_audit_log)
        audit_layout.addWidget(self.refresh_audit_button)
        self.tabs.addTab(self.audit_tab, "Audit Log")

        # --- Save Button ---
        self.save_button = QPushButton("Save Settings")
        self.save_button.setStyleSheet("background-color: #11563a; color: white; padding: 10px; font-size: 16px;")
        self.save_button.clicked.connect(self.save_settings)
        layout.addWidget(self.save_button)

        # Load initial user list and audit log
        self.load_users_list()
        self.load_audit_log()

    def populate_settings(self):
        """Fill the UI controls with current settings."""
        settings = config.settings

        # General
        lang_code = settings.get("language", "en")
        index = self.language_combo.findData(lang_code)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)

        date_fmt = settings.get("date_format", "both")
        index = self.date_format_combo.findData(date_fmt)
        if index >= 0:
            self.date_format_combo.setCurrentIndex(index)

        db_path_override = settings.get("db_path_override")
        self.db_path_edit.setText(db_path_override or "")

        # Backups
        freq = settings.get("backup_frequency_days", 1)
        self.backup_freq_spinbox.setValue(freq)

        retention = settings.get("backup_retention_count", 10)
        self.backup_retention_spinbox.setValue(retention)

        encrypt = settings.get("enable_backup_encryption", False)
        self.backup_encrypt_checkbox.setChecked(encrypt)

    def browse_db_path(self):
        """Open file dialog to select DB path."""
        current_path = self.db_path_edit.text()
        if not current_path:
            current_path = str(config.user_data_dir)
        filename, _ = QFileDialog.getSaveFileName(
            self, "Select Database File", current_path, "SQLite Database (*.db)"
        )
        if filename:
            # Normalize path
            normalized_path = Path(filename).resolve()
            self.db_path_edit.setText(str(normalized_path))

    def save_settings(self):
        """Save the settings from the UI to the config."""
        try:
            # General
            config.update_setting("language", self.language_combo.currentData())
            config.update_setting("date_format", self.date_format_combo.currentData())
            db_path_text = self.db_path_edit.text().strip()
            if db_path_text:
                config.update_setting("db_path_override", db_path_text)
            else:
                config.update_setting("db_path_override", None) # Clear override

            # Backups
            config.update_setting("backup_frequency_days", self.backup_freq_spinbox.value())
            config.update_setting("backup_retention_count", self.backup_retention_spinbox.value())
            config.update_setting("enable_backup_encryption", self.backup_encrypt_checkbox.isChecked())

            QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully.")
            self.logger.info("Settings saved by user.")

            # Check if a restart is needed (e.g., DB path, language)
            # For simplicity, always prompt for restart if critical settings change
            # A more nuanced approach would check specific values
            reply = QMessageBox.question(
                self, 'Restart Required',
                "Some settings might require a restart to take full effect. Restart now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes and self.main_window:
                self.logger.info("User requested restart after settings change.")
                QApplication.instance().quit() # Or close main window
                # The main.py script would need to handle restarting if desired

        except Exception as e:
            self.logger.error(f"Error saving settings: {e}", exc_info=True)
            QMessageBox.critical(self, "Save Error", f"Failed to save settings: {e}")

    # --- User Management ---
    def add_new_user(self):
        """Add a new user account."""
        if self.current_user.role != "admin":
            QMessageBox.warning(self, "Access Denied", "Only administrators can add users.")
            return

        username = self.new_username_edit.text().strip()
        password = self.new_password_edit.text()
        role = self.new_role_combo.currentData()

        if not username or not password:
            QMessageBox.warning(self, "Input Error", "Username and password are required.")
            return

        try:
            db_session = user_service._get_session()
            try:
                user_service.create_user(username, password, role, db=db_session)
                QMessageBox.information(self, "Success", f"User '{username}' created successfully.")
                self.logger.info(f"New user '{username}' (role: {role}) created by {self.current_user.username}.")
                # Clear input fields
                self.new_username_edit.clear()
                self.new_password_edit.clear()
                # Refresh user list
                self.load_users_list()
            finally:
                db_session.close()
        except Exception as e: # UserServiceError or IntegrityError etc.
            self.logger.error(f"Error creating user '{username}': {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to create user: {e}")

    def load_users_list(self):
        """Load and display the list of users."""
        if self.current_user.role != "admin":
            self.users_list_text.setPlainText("Access restricted to administrators.")
            return

        try:
            db_session = user_service._get_session()
            try:
                users = db_session.query(User).all()
                user_lines = [f"{'Username':<15} {'Role':<10} {'Last Login'}"]
                user_lines.append("-" * 40)
                for user in users:
                    last_login_str = user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else "Never"
                    user_lines.append(f"{user.username:<15} {user.role:<10} {last_login_str}")
                self.users_list_text.setPlainText("\n".join(user_lines))
            finally:
                db_session.close()
        except Exception as e:
            self.logger.error(f"Error loading users list: {e}", exc_info=True)
            self.users_list_text.setPlainText(f"Error loading users: {e}")

    # --- Audit Log ---
    def load_audit_log(self):
        """Load and display recent audit log entries."""
        if self.current_user.role != "admin":
            self.audit_log_text.setPlainText("Access restricted to administrators.")
            return

        try:
            # Import AuditLog model
            from ...database import AuditLog
            db_session = user_service._get_session() # Reuse service session helper
            try:
                # Get last N entries, ordered by time descending
                audit_entries = db_session.query(AuditLog).order_by(AuditLog.performed_at.desc()).limit(100).all()
                entry_lines = [f"{'Time':<20} {'User':<15} {'Action':<15} {'Table':<15} {'Record ID'}"]
                entry_lines.append("-" * 80)
                for entry in audit_entries:
                    time_str = entry.performed_at.strftime('%Y-%m-%d %H:%M:%S') if entry.performed_at else ""
                    entry_lines.append(
                        f"{time_str:<20} {entry.performed_by:<15} {entry.action:<15} "
                        f"{entry.table_name:<15} {entry.record_id}"
                    )
                self.audit_log_text.setPlainText("\n".join(entry_lines))
            finally:
                db_session.close()
        except Exception as e:
            self.logger.error(f"Error loading audit log: {e}", exc_info=True)
            self.audit_log_text.setPlainText(f"Error loading audit log: {e}")

# Example usage (if run directly)
# if __name__ == '__main__':
#     from PyQt6.QtWidgets import QApplication, QMainWindow
#     import sys
#     from ...database import init_db, User
#     init_db()
#     app = QApplication(sys.argv)
#     # Mock admin user
#     admin_user = User(username="admin", role="admin")
#     window = QMainWindow()
#     settings_view = SettingsView(admin_user)
#     window.setCentralWidget(settings_view)
#     window.show()
#     sys.exit(app.exec())