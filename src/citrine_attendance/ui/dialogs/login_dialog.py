# src/citrine_attendance/ui/dialogs/login_dialog.py
"""Modern login dialog for user authentication (light, readable color palette)."""
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
from ...locale import _, translator

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
        self.setFixedSize(420, 520)

        self.current_user = None
        self.settings = QSettings(APP_AUTHOR, APP_NAME)

        # Set layout direction based on language (Right-to-Left for Persian)
        if getattr(translator, "language", None) == "fa":
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        self.load_custom_font()
        self.init_ui()
        self.apply_stylesheet()
        self.load_saved_credentials()

    def load_custom_font(self):
        """Loads the Vazir custom font from resources (if available)."""
        try:
            font_path = str(get_font_path("Vazir-Regular.ttf"))
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id == -1:
                self.logger.warning("Could not load Vazir font from path: %s", font_path)
        except Exception as e:
            self.logger.error(f"Failed to load custom font: {e}", exc_info=True)

    def init_ui(self):
        """Initialize the modern login dialog UI."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        container = QWidget(self)
        container.setObjectName("container")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title_label = QLabel(_("login_header"))
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        subtitle_label = QLabel(_("login_subtitle"))
        subtitle_label.setObjectName("subtitleLabel")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle_label)
        layout.addSpacing(18)

        # Username input
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText(_("username"))
        self.username_input.setObjectName("inputField")
        self.add_icon_to_input(self.username_input, get_icon_path("user.svg"))
        layout.addWidget(self.username_input)

        # Password input
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText(_("password"))
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setObjectName("inputField")
        self.add_icon_to_input(self.password_input, get_icon_path("lock.svg"))
        self.setup_password_visibility_toggle()
        layout.addWidget(self.password_input)

        # Options row
        options_layout = QHBoxLayout()
        self.remember_checkbox = QCheckBox(_("remember_me"))
        self.remember_checkbox.setObjectName("rememberCheckbox")
        options_layout.addWidget(self.remember_checkbox)
        options_layout.addStretch()
        layout.addLayout(options_layout)
        layout.addSpacing(8)

        # Primary (login) button
        self.login_button = QPushButton(_("login"))
        self.login_button.setObjectName("loginButton")
        self.login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_button.clicked.connect(self.handle_login)
        self.login_button.setDefault(True)
        layout.addWidget(self.login_button)

        # Secondary (cancel) button
        self.cancel_button = QPushButton(_("cancel"))
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)

        layout.addStretch(1)
        self.main_layout.addWidget(container)

    def add_icon_to_input(self, line_edit: QLineEdit, icon_path):
        """Adds a permanent leading/trailing icon to a QLineEdit and adjusts padding."""
        try:
            action = QAction(line_edit)
            try:
                action.setIcon(QIcon(str(icon_path)))
            except Exception:
                action.setIcon(QIcon(icon_path))

            # Determine action position based on layout direction
            if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
                position = QLineEdit.ActionPosition.TrailingPosition
                padding_style = "padding-right: 36px; padding-left: 12px;"
            else:
                position = QLineEdit.ActionPosition.LeadingPosition
                padding_style = "padding-left: 36px; padding-right: 12px;"

            line_edit.addAction(action, position)
            base_stylesheet = line_edit.styleSheet() or ""
            line_edit.setStyleSheet(f"{base_stylesheet} {padding_style}")
        except Exception as e:
            self.logger.error(f"Could not add icon to input ({icon_path}): {e}", exc_info=True)

    def setup_password_visibility_toggle(self):
        """Adds a show/hide password action to the password field."""
        try:
            self.toggle_password_action = QAction(self)
            try:
                self.toggle_password_action.setIcon(QIcon(str(get_icon_path("eye-off.svg"))))
            except Exception:
                self.toggle_password_action.setIcon(QIcon(get_icon_path("eye-off.svg")))
            self.toggle_password_action.triggered.connect(self.toggle_password_visibility)

            if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
                position = QLineEdit.ActionPosition.LeadingPosition
            else:
                position = QLineEdit.ActionPosition.TrailingPosition

            self.password_input.addAction(self.toggle_password_action, position)
        except Exception as e:
            self.logger.error(f"Could not set up password visibility toggle: {e}", exc_info=True)

    def toggle_password_visibility(self):
        """Toggles the password field's echo mode and updates the icon."""
        try:
            if self.password_input.echoMode() == QLineEdit.EchoMode.Password:
                self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
                try:
                    self.toggle_password_action.setIcon(QIcon(str(get_icon_path("eye.svg"))))
                except Exception:
                    self.toggle_password_action.setIcon(QIcon(get_icon_path("eye.svg")))
            else:
                self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
                try:
                    self.toggle_password_action.setIcon(QIcon(str(get_icon_path("eye-off.svg"))))
                except Exception:
                    self.toggle_password_action.setIcon(QIcon(get_icon_path("eye-off.svg")))
        except Exception as e:
            self.logger.error(f"Could not toggle password visibility: {e}", exc_info=True)

    def apply_stylesheet(self):
        """Applies a modern, light and readable stylesheet to the dialog."""
        self.setStyleSheet("""
            /* Container */
            #container {
                background-color: #ffffff;
                font-family: Vazir, 'Segoe UI', Arial, sans-serif;
            }

            /* Title & subtitle */
            #titleLabel {
                font-size: 26px;
                font-weight: 700;
                color: #0f172a;
                margin-bottom: 6px;
            }
            #subtitleLabel {
                font-size: 13px;
                color: #6b7280;
                margin-bottom: 8px;
            }

            /* Input fields */
            QLineEdit#inputField {
                background-color: #ffffff;
                color: #0b1220;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding-top: 10px;
                padding-bottom: 10px;
                font-size: 14px;
                min-height: 40px;
            }
            QLineEdit#inputField:focus {
                border: 1px solid #0b6df3;
                box-shadow: none;
            }

            /* Checkbox */
            QCheckBox#rememberCheckbox {
                color: #475569;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
            }
            QCheckBox::indicator:checked {
                background-color: #0b6df3;
                border: 1px solid #0b6df3;
            }

            /* Primary login button (blue) */
            QPushButton#loginButton {
                background-color: #0b6df3;
                color: white;
                font-size: 15px;
                font-weight: 700;
                border: none;
                border-radius: 8px;
                padding: 10px;
                margin-top: 6px;
                min-height: 42px;
            }
            QPushButton#loginButton:hover {
                background-color: #095bd0;
            }
            QPushButton#loginButton:pressed {
                background-color: #084bb0;
            }
            QPushButton#loginButton:disabled {
                background-color: #9fbef9;
                color: #ffffff;
            }

            /* Cancel button (secondary) */
            QPushButton#cancelButton {
                background-color: transparent;
                color: #475569;
                font-size: 14px;
                border: none;
                padding: 8px;
                text-align: center;
            }
            QPushButton#cancelButton:hover {
                color: #0b6df3;
                text-decoration: underline;
            }

            /* Accessibility */
            QPushButton, QComboBox, QLineEdit, QSpinBox {
                min-height: 36px;
            }
        """)

    def load_saved_credentials(self):
        """Load saved username and 'remember me' state from QSettings."""
        try:
            remember = self.settings.value(SETTINGS_REMEMBER_ME, False, type=bool)
        except Exception:
            remember = False

        try:
            saved_username = self.settings.value(SETTINGS_SAVED_USERNAME, "", type=str)
        except Exception:
            saved_username = ""

        self.remember_checkbox.setChecked(bool(remember))
        if remember and saved_username:
            self.username_input.setText(saved_username)
            self.password_input.setFocus()
        else:
            self.username_input.setFocus()

    def save_credentials(self, username: str):
        """Save username and 'remember me' state based on checkbox."""
        try:
            if self.remember_checkbox.isChecked():
                self.settings.setValue(SETTINGS_REMEMBER_ME, True)
                self.settings.setValue(SETTINGS_SAVED_USERNAME, username)
                self.logger.debug(f"Saved username '{username}' for 'Remember Me'.")
            else:
                self.settings.setValue(SETTINGS_REMEMBER_ME, False)
                self.settings.remove(SETTINGS_SAVED_USERNAME)
                self.logger.debug("Cleared saved credentials for 'Remember Me'.")
        except Exception as e:
            self.logger.error(f"Could not save credentials: {e}", exc_info=True)

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
            try:
                QMessageBox.critical(self, _("login_error"), _("unexpected_error", error=str(e)))
            except Exception:
                QMessageBox.critical(self, _("login_error"), _("unexpected_error", error=""))

    def keyPressEvent(self, event: QKeyEvent):
        """Handle Enter/Return key press to trigger login."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.handle_login()
        else:
            super().keyPressEvent(event)


# Test block for running the dialog standalone
if __name__ == '__main__':
    app = QApplication(sys.argv)

    # If translator supports runtime language switching in tests
    try:
        translator.set_language("fa")
    except Exception:
        pass

    class MockUserService:
        def authenticate_user(self, username, password):
            if username == "admin" and password == "admin":
                user = type('User', (object,), {'username': 'admin', 'role': 'Administrator'})()
                return user
            raise InvalidCredentialsError(_("invalid_credentials"))

    # Temporarily override the real user_service for the test
    user_service = MockUserService()

    login_dialog = LoginDialog()

    def on_login(user):
        print(f"Login successful signal received for user: {user.username}")

    login_dialog.login_successful.connect(on_login)

    if login_dialog.exec() == QDialog.DialogCode.Accepted:
        print(f"Logged in as: {login_dialog.current_user.username} (Role: {login_dialog.current_user.role})")
    else:
        print("Login cancelled or failed.")

    sys.exit(app.exec())
