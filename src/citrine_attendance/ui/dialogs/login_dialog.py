# src/citrine_attendance/ui/dialogs/login_dialog.py
"""Modern login dialog for user authentication."""
import sys
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QMessageBox, QCheckBox, QApplication, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QKeyEvent, QFontDatabase, QIcon, QAction

from ...services.user_service import user_service, InvalidCredentialsError
from ...config import APP_NAME, APP_AUTHOR
from ...utils.resources import get_font_path, get_icon_path
from ...locale import _, translator # Import the translator

# Define keys for QSettings
SETTINGS_REMEMBER_ME = "login/remember_me"
SETTINGS_SAVED_USERNAME = "login/saved_username"

class LoginDialog(QDialog):
    """A dialog window for user login with a modern UI."""

    login_successful = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.setWindowTitle(_("login_title"))
        self.setModal(True)
        self.setFixedSize(400, 480)

        self.current_user = None
        self.settings = QSettings(APP_AUTHOR, APP_NAME)
        
        # Set layout direction based on language
        if translator.language == "fa":
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        self.load_custom_font()
        self.init_ui()
        self.apply_stylesheet()
        self.load_saved_credentials()

    def load_custom_font(self):
        """Loads the Vazir custom font from resources."""
        try:
            font_path = str(get_font_path("Vazir-Regular.ttf"))
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id == -1:
                self.logger.warning("Could not load Vazir font.")
        except Exception as e:
            self.logger.error(f"Failed to load custom font: {e}")

    def init_ui(self):
        """Initialize the modern login dialog UI."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        container = QWidget(self)
        container.setObjectName("container")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(15)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel(_("login_header"))
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        subtitle_label = QLabel(_("login_subtitle"))
        subtitle_label.setObjectName("subtitleLabel")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle_label)
        layout.addSpacing(20)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText(_("username"))
        self.username_input.setObjectName("inputField")
        self.add_icon_to_input(self.username_input, "user.svg")
        layout.addWidget(self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText(_("password"))
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setObjectName("inputField")
        self.add_icon_to_input(self.password_input, "lock.svg")
        self.setup_password_visibility_toggle()
        layout.addWidget(self.password_input)
        
        options_layout = QHBoxLayout()
        self.remember_checkbox = QCheckBox(_("remember_me"))
        self.remember_checkbox.setObjectName("rememberCheckbox")
        options_layout.addWidget(self.remember_checkbox)
        options_layout.addStretch()
        layout.addLayout(options_layout)
        layout.addSpacing(10)

        self.login_button = QPushButton(_("login"))
        self.login_button.setObjectName("loginButton")
        self.login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_button.clicked.connect(self.handle_login)
        self.login_button.setDefault(True)
        layout.addWidget(self.login_button)

        self.cancel_button = QPushButton(_("cancel"))
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)

        layout.addStretch(1)
        self.main_layout.addWidget(container)
    
    def add_icon_to_input(self, line_edit, icon_name):
        """Adds a permanent left-side icon to a QLineEdit."""
        try:
            icon_action = QAction(line_edit)
            icon_path = str(get_icon_path(icon_name))
            icon_action.setIcon(QIcon(icon_path))
            
            action_position = QLineEdit.ActionPosition.LeadingPosition
            padding_style = "padding-left: 35px; padding-right: 15px;"
            if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
                action_position = QLineEdit.ActionPosition.TrailingPosition
                padding_style = "padding-left: 15px; padding-right: 35px;"

            line_edit.addAction(icon_action, action_position)
            line_edit.setStyleSheet(f"{padding_style} padding-top: 12px; padding-bottom: 12px;")
        except Exception as e:
            self.logger.error(f"Could not add icon '{icon_name}': {e}. Ensure icons exist.")

    def setup_password_visibility_toggle(self):
        """Adds a show/hide password action to the password field."""
        try:
            self.toggle_password_action = QAction(self)
            self.toggle_password_action.setIcon(QIcon(str(get_icon_path("eye-off.svg"))))
            self.toggle_password_action.setCursor(Qt.CursorShape.PointingHandCursor)
            self.toggle_password_action.triggered.connect(self.toggle_password_visibility)
            
            action_position = QLineEdit.ActionPosition.TrailingPosition
            if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
                action_position = QLineEdit.ActionPosition.LeadingPosition

            self.password_input.addAction(self.toggle_password_action, action_position)
        except Exception as e:
            self.logger.error(f"Could not set up password visibility toggle: {e}. Ensure icons exist.")

    def toggle_password_visibility(self):
        """Toggles the password field's echo mode and icon."""
        try:
            if self.password_input.echoMode() == QLineEdit.EchoMode.Password:
                self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
                self.toggle_password_action.setIcon(QIcon(str(get_icon_path("eye.svg"))))
            else:
                self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
                self.toggle_password_action.setIcon(QIcon(str(get_icon_path("eye-off.svg"))))
        except Exception as e:
            self.logger.error(f"Could not toggle password visibility: {e}")

    def apply_stylesheet(self):
        """Applies a modern stylesheet to the dialog."""
        self.setStyleSheet("""
            #container {
                background-color: #2c3e50;
                font-family: Vazir, Segoe UI, Arial, sans-serif;
            }
            #titleLabel {
                font-size: 28px;
                font-weight: bold;
                color: #ecf0f1;
                margin-bottom: 5px;
            }
            #subtitleLabel {
                font-size: 14px;
                color: #bdc3c7;
                margin-bottom: 20px;
            }
            QLineEdit#inputField {
                background-color: #34495e;
                color: #ecf0f1;
                border: 1px solid #2c3e50;
                border-radius: 8px;
                /* Padding is now handled by add_icon_to_input */
                font-size: 14px;
            }
            QLineEdit#inputField:focus {
                border: 1px solid #3498db;
            }
            QCheckBox#rememberCheckbox {
                color: #bdc3c7;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border-radius: 4px;
                background-color: #34495e;
                border: 1px solid #4a627a;
            }
            QCheckBox::indicator:checked {
                background-color: #3498db;
                border: 1px solid #3498db;
            }
            QPushButton#loginButton {
                background-color: #3498db;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 12px;
                margin-top: 10px;
            }
            QPushButton#loginButton:hover {
                background-color: #2980b9;
            }
            QPushButton#loginButton:pressed {
                background-color: #1f618d;
            }
            QPushButton#cancelButton {
                background-color: transparent;
                color: #bdc3c7;
                font-size: 14px;
                border: none;
                padding: 8px;
            }
            QPushButton#cancelButton:hover {
                color: #ecf0f1;
                text-decoration: underline;
            }
        """)

    def load_saved_credentials(self):
        """Load saved username and 'remember me' state from QSettings."""
        remember = self.settings.value(SETTINGS_REMEMBER_ME, False, type=bool)
        saved_username = self.settings.value(SETTINGS_SAVED_USERNAME, "", type=str)

        self.remember_checkbox.setChecked(remember)
        if remember and saved_username:
            self.username_input.setText(saved_username)
            self.password_input.setFocus()
        else:
            self.username_input.setFocus()

    def save_credentials(self, username: str):
        """Save username and 'remember me' state based on checkbox."""
        if self.remember_checkbox.isChecked():
            self.settings.setValue(SETTINGS_REMEMBER_ME, True)
            self.settings.setValue(SETTINGS_SAVED_USERNAME, username)
            self.logger.debug(f"Saved username '{username}' for 'Remember Me'.")
        else:
            self.settings.setValue(SETTINGS_REMEMBER_ME, False)
            self.settings.remove(SETTINGS_SAVED_USERNAME)
            self.logger.debug("Cleared saved credentials for 'Remember Me'.")
    
    def handle_login(self):
        """Handle the login button click."""
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, _("login_failed"), _("login_enter_credentials"))
            return

        try:
            user = user_service.authenticate_user(username, password)
            if user:
                self.current_user = user
                self.save_credentials(username)
                self.logger.info(f"User '{username}' logged in successfully.")
                self.login_successful.emit(user)
                self.accept()
            else:
                raise InvalidCredentialsError(_("invalid_credentials"))

        except InvalidCredentialsError:
            self.logger.warning(f"Failed login attempt for username '{username}'.")
            QMessageBox.critical(self, _("login_failed"), _("invalid_credentials"))
            self.password_input.clear()
            self.username_input.setFocus()
        except Exception as e:
            self.logger.error(f"Unexpected error during login for '{username}': {e}", exc_info=True)
            QMessageBox.critical(self, _("login_error"), _("unexpected_error", error=e))

    def keyPressEvent(self, event: QKeyEvent):
        """Handle Enter/Return key press to trigger login."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.handle_login()
        else:
            super().keyPressEvent(event)

# Example usage for testing
if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # --- HERO IMPLEMENTATION: Set language to Persian for testing ---
    translator.set_language("fa")
    
    # Mock user service for standalone testing
    class MockUserService:
        def authenticate_user(self, username, password):
            if username == "admin" and password == "admin":
                user = type('User', (object,), {'username': 'admin', 'role': 'Administrator'})()
                return user
            raise InvalidCredentialsError(_("invalid_credentials"))

    user_service = MockUserService()
    
    def get_icon_path(icon_name):
        return f"./{icon_name}"
    
    def get_font_path(font_name):
        return f"./{font_name}"

    print("Running login dialog test in Persian...")
    
    login_dialog = LoginDialog()
    
    def on_login(user):
        print(f"Login successful signal received for user: {user.username}")

    login_dialog.login_successful.connect(on_login)
    
    if login_dialog.exec() == QDialog.DialogCode.Accepted:
        print(f"Logged in as: {login_dialog.current_user.username} (Role: {login_dialog.current_user.role})")
    else:
        print("Login cancelled or failed.")
    
    sys.exit(app.exec())