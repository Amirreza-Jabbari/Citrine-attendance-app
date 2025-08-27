# src/citrine_attendance/ui/dialogs/login_dialog.py
"""Login dialog for user authentication."""
import sys
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QMessageBox, QCheckBox, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings # Import QSettings
from PyQt6.QtGui import QKeyEvent

from ...services.user_service import user_service, InvalidCredentialsError
# Import config for app name/author used in QSettings
from ...config import APP_NAME, APP_AUTHOR

# Define keys for QSettings
SETTINGS_REMEMBER_ME = "login/remember_me"
SETTINGS_SAVED_USERNAME = "login/saved_username"

class LoginDialog(QDialog):
    """A dialog window for user login."""

    # Signal emitted when login is successful, passing the user object
    login_successful = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.setWindowTitle("Login - Citrine Attendance")
        self.setModal(True)
        self.setFixedSize(350, 220) # Slightly increase height for checkbox

        self.current_user = None
        self.settings = QSettings(APP_AUTHOR, APP_NAME) # Initialize QSettings
        self.init_ui()
        self.load_saved_credentials() # Load saved state on init

    def init_ui(self):
        """Initialize the login dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15) # Add some space between elements

        # Title Label
        title_label = QLabel("Citrine Attendance")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)

        # Username input
        self.username_label = QLabel("Username:")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your username")
        layout.addWidget(self.username_label)
        layout.addWidget(self.username_input)

        # Password input
        self.password_label = QLabel("Password:")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password) # Hide password characters
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)

        # --- Remember me checkbox (IMPLEMENTED) ---
        self.remember_checkbox = QCheckBox("Remember my username") # Changed text slightly
        # Remove the line that disabled it
        # self.remember_checkbox.setEnabled(False) 
        layout.addWidget(self.remember_checkbox)

        # Buttons layout
        buttons_layout = QHBoxLayout()
        self.login_button = QPushButton("Login")
        self.login_button.clicked.connect(self.handle_login)
        self.login_button.setDefault(True) # Make it the default button (Enter key)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject) # Close dialog on cancel
        buttons_layout.addWidget(self.login_button)
        buttons_layout.addWidget(self.cancel_button)
        # Add stretch to push buttons to the right
        buttons_layout.addStretch()

        layout.addLayout(buttons_layout)

        # Set focus to username field for quick typing
        # Focus will be set in load_saved_credentials if username is pre-filled

    def load_saved_credentials(self):
        """Load saved username and 'remember me' state from QSettings."""
        remember = self.settings.value(SETTINGS_REMEMBER_ME, False, type=bool)
        saved_username = self.settings.value(SETTINGS_SAVED_USERNAME, "", type=str)

        self.remember_checkbox.setChecked(remember)
        if remember and saved_username:
            self.username_input.setText(saved_username)
            # Set focus to password if username is pre-filled
            self.password_input.setFocus()
        else:
            # Set focus to username if nothing is pre-filled
            self.username_input.setFocus()

    def save_credentials(self, username: str):
        """Save username and 'remember me' state based on checkbox."""
        if self.remember_checkbox.isChecked():
            self.settings.setValue(SETTINGS_REMEMBER_ME, True)
            self.settings.setValue(SETTINGS_SAVED_USERNAME, username)
            self.logger.debug(f"Saved username '{username}' for 'Remember Me'.")
        else:
            # If unchecked, clear saved data
            self.settings.setValue(SETTINGS_REMEMBER_ME, False)
            self.settings.remove(SETTINGS_SAVED_USERNAME) # Remove the saved username
            self.logger.debug("Cleared saved credentials for 'Remember Me'.")

    def clear_saved_credentials(self):
        """Explicitly clear saved credentials (e.g., on logout if implemented)."""
        self.settings.setValue(SETTINGS_REMEMBER_ME, False)
        self.settings.remove(SETTINGS_SAVED_USERNAME)
        self.logger.debug("Explicitly cleared saved credentials.")

    def handle_login(self):
        """Handle the login button click."""
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Login Failed", "Please enter both username and password.")
            return

        try:
            # Authenticate using the user service
            user = user_service.authenticate_user(username, password)
            if user:
                self.current_user = user
                # --- Save credentials if 'Remember Me' is checked ---
                self.save_credentials(username)
                # ---
                self.logger.info(f"User '{username}' logged in successfully.")
                # Emit the signal with the user object
                self.login_successful.emit(user)
                # Accept the dialog (closes it and returns QDialog.DialogCode.Accepted)
                self.accept()
            else:
                # Authentication failed (authenticate_user returns None)
                raise InvalidCredentialsError("Invalid username or password.")

        except InvalidCredentialsError:
            self.logger.warning(f"Failed login attempt for username '{username}'.")
            QMessageBox.critical(self, "Login Failed", "Invalid username or password.")
            # Clear password field for security
            self.password_input.clear()
            # --- Clear saved credentials on failed login attempt? ---
            # Optional: Clear saved state if login fails for the saved user
            # This prevents getting stuck with a wrong saved username.
            # However, it might be annoying if it's just a typo.
            # Let's keep it simple for now and only clear on explicit user action (uncheck + login)
            # self.clear_saved_credentials() 
            # ---
            self.username_input.setFocus() # Return focus to username
        except Exception as e:
            self.logger.error(f"Unexpected error during login for '{username}': {e}", exc_info=True)
            QMessageBox.critical(self, "Login Error", f"An unexpected error occurred: {e}")

    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press events (e.g., Enter key)."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # If focus is on login button, clicking it handles the login
            # Otherwise, trigger the login if inputs are focused
            if self.login_button.hasFocus():
                self.handle_login()
            elif self.username_input.hasFocus() or self.password_input.hasFocus():
                 self.handle_login()
            else:
                super().keyPressEvent(event) # Pass other Enter presses to parent
        else:
            super().keyPressEvent(event) # Pass other keys to parent

# Example usage (if run directly for testing)
# (No changes needed in the example section)
# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     # ... (rest of example code)
#     login_dialog = LoginDialog()
#     login_dialog.exec()
#     if login_dialog.current_user:
#         print(f"Logged in as: {login_dialog.current_user.username} (Role: {login_dialog.current_user.role})")
#     else:
#         print("Login cancelled or failed.")
#     sys.exit(app.exec())