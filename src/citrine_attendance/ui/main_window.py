# src/citrine_attendance/ui/main_window.py
"""Main application window."""
import sys
import logging
from datetime import timedelta # Import timedelta for backup interval calculation
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QToolBar, QStatusBar,
    QMessageBox, QSizePolicy, QFrame, QDialog
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontDatabase, QIcon, QFont

from ..config import config
from ..utils.resources import get_font_path, get_icon_path
# Import the Login Dialog
from .dialogs.login_dialog import LoginDialog
# Import User model for role checks (if needed locally, though service can handle it)
from ..database import User
# Import Views
from .views.dashboard_view import DashboardView
from .views.employee_view import EmployeeView
from .views.attendance_view import AttendanceView
from .views.backups_view import BackupsView
from .views.reports_view import ReportsView
from .views.archive_view import ArchiveView
from .views.settings_view import SettingsView

# --- Import Backup Service for automatic backups ---
from ..services.backup_service import backup_service, BackupServiceError
from ..locale import _


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = None

        # --- Attributes for automatic backup ---
        self.backup_timer = None
        self.last_backup_check_time = None # Optional: track when we last checked/scheduled

        # --- Initial UI Setup (Before Login) ---
        self.setWindowTitle(_("app_title"))
        self.setGeometry(100, 100, 1200, 800)

        # Placeholder widget shown before login
        self.placeholder_widget = QLabel(_("status_initializing"))
        self.placeholder_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(self.placeholder_widget)
        # Initially hide the main window, only show the login dialog
        self.hide()

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(_("status_initializing"))

        # Load resources
        self.load_resources()

        # Start the login process *after* the main window object is fully constructed
        QTimer.singleShot(0, self.show_login_and_ui)

    def show_login_and_ui(self):
        """Orchestrate the login and subsequent UI setup."""
        self.show_login()
        # init_main_ui is now called from on_login_successful

    def show_login(self):
        """Show the login dialog."""
        QApplication.processEvents()
        self.login_dialog = LoginDialog(self)
        self.login_dialog.login_successful.connect(self.on_login_successful)
        login_result = self.login_dialog.exec()

        if login_result != QDialog.DialogCode.Accepted:
            self.logger.info("Login dialog closed or cancelled. Exiting application.")
            QApplication.instance().quit()

    def on_login_successful(self, user: User):
        """Slot called when user successfully logs in."""
        self.current_user = user
        self.logger.info(f"Main window updated for user: {user.username} (Role: {user.role})")
        # Now initialize the full UI that requires a logged-in user
        self.init_main_ui()
        # Update UI elements based on user role
        self.update_ui_for_user_role()
        # Connect signals between views
        self.connect_signals()
        # --- Setup automatic backups after login ---
        self.setup_automatic_backup()
        # Now that UI is set up, show the main window
        self.show()
        self.raise_()
        self.activateWindow()

    # --- Automatic Backup Logic ---
    def setup_automatic_backup(self):
        """Setup the automatic backup timer based on configuration."""
        # Ensure the user is logged in and is an admin
        if not self.current_user or self.current_user.role != "admin":
            self.logger.debug("Not setting up auto-backup: User is not an admin or not logged in.")
            return

        try:
            # Get backup frequency from config (default to 1 day)
            frequency_days = config.settings.get("backup_frequency_days", 1)
            
            # If frequency is 0 or negative, backups are disabled
            if frequency_days <= 0:
                self.logger.info("Automatic backup is disabled (frequency <= 0).")
                # Stop timer if it was running
                if self.backup_timer and self.backup_timer.isActive():
                    self.backup_timer.stop()
                    self.logger.debug("Stopped existing backup timer as backups are disabled.")
                return

            # Calculate interval in milliseconds
            interval_ms = int(timedelta(days=frequency_days).total_seconds() * 1000)
            
            # Enforce a minimum interval for safety (e.g., 1 minute)
            MIN_INTERVAL_MS = 60 * 1000 # 1 minute
            interval_ms = max(interval_ms, MIN_INTERVAL_MS)

            # Stop existing timer if any
            if self.backup_timer and self.backup_timer.isActive():
                self.backup_timer.stop()
                self.logger.debug("Stopped existing backup timer.")

            # Create and configure the new timer
            self.backup_timer = QTimer(self)
            self.backup_timer.timeout.connect(self.perform_scheduled_backup)
            
            # Start the timer with the calculated interval
            self.backup_timer.start(interval_ms)
            
            self.logger.info(f"Automatic backup scheduled every {frequency_days} day(s) ({interval_ms} ms).")
            self.status_bar.showMessage(f"Automatic backup scheduled.", 5000) # Show for 5 seconds

        except Exception as e:
            self.logger.error(f"Failed to setup automatic backup timer: {e}", exc_info=True)
            self.status_bar.showMessage("Error setting up auto-backup.", 5000)

    def perform_scheduled_backup(self):
        """Slot called by the backup timer to perform a scheduled backup."""
        # Safety check: Ensure user is still admin
        if not self.current_user or self.current_user.role != "admin":
            self.logger.warning("Skipping scheduled backup: User is not an admin.")
            return

        try:
            # Trigger the backup creation via the service
            backup_path = backup_service.create_backup(manual=False)
            self.logger.info(f"Scheduled backup created successfully: {backup_path}")
            # Optional: Brief status bar update
            # self.status_bar.showMessage(f"Backup created: {backup_path.name}", 3000)

        except BackupServiceError as e:
            self.logger.error(f"Scheduled backup failed (service error): {e}")
            self.status_bar.showMessage("Scheduled backup failed. Check logs.", 5000)
            # Consider non-modal warning to user if critical
            # QMessageBox.warning(self, "Backup Failed", f"Automatic backup failed: {e}")
        except Exception as e:
            self.logger.error(f"Scheduled backup failed (unexpected error): {e}", exc_info=True)
            self.status_bar.showMessage("Scheduled backup failed unexpectedly. Check logs.", 5000)
            # QMessageBox.critical(self, "Backup Error", f"Unexpected error during backup: {e}")

    def init_main_ui(self):
        """Initialize the main application UI after successful login."""
        self.logger.debug("Initializing main UI components...")
        # Remove placeholder and create the actual central widget
        self.takeCentralWidget()
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_h_layout = QHBoxLayout(central_widget)
        main_h_layout.setContentsMargins(0, 0, 0, 0)
        main_h_layout.setSpacing(0)

        # --- Sidebar ---
        self.create_sidebar()
        main_h_layout.addWidget(self.sidebar)

        # --- Content Area (Stacked Widget) ---
        self.stacked_widget = QStackedWidget()
        self.create_main_views()
        main_h_layout.addWidget(self.stacked_widget)

        # Set Dashboard as the initial view
        self.switch_view(0)
        self.status_bar.showMessage(_("status_ready"))
        self.logger.debug("Main UI components initialized.")

    def create_sidebar(self):
        """Create the sidebar navigation."""
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFrameShape(QFrame.Shape.StyledPanel)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.sidebar.setMaximumWidth(200)
        self.sidebar.setMinimumWidth(150)
        self.sidebar.setStyleSheet("""
            #sidebar {
                background-color: #f5f5f5;
                border-right: 1px solid #ddd;
            }
            QPushButton {
                text-align: left;
                padding: 10px;
                border: none;
                border-radius: 4px;
                background-color: transparent;
                margin: 2px 5px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: #bdbdbd;
            }
        """)

        # --- Navigation Buttons ---
        self.btn_dashboard = QPushButton(_("view_dashboard"))
        self.btn_dashboard.setObjectName("btnDashboard")
        self.btn_dashboard.clicked.connect(lambda: self.switch_view(0))
        sidebar_layout.addWidget(self.btn_dashboard)

        self.btn_employees = QPushButton(_("view_employees"))
        self.btn_employees.setObjectName("btnEmployees")
        self.btn_employees.clicked.connect(lambda: self.switch_view(1))
        sidebar_layout.addWidget(self.btn_employees)

        self.btn_attendance = QPushButton(_("view_attendance"))
        self.btn_attendance.setObjectName("btnAttendance")
        self.btn_attendance.clicked.connect(lambda: self.switch_view(2))
        sidebar_layout.addWidget(self.btn_attendance)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sidebar_layout.addWidget(spacer)

        # --- Admin-specific buttons (connected) ---
        self.btn_reports = QPushButton(_("view_reports"))
        self.btn_reports.setObjectName("btnReports")
        self.btn_reports.clicked.connect(lambda: self.switch_view(3)) # Connected
        sidebar_layout.addWidget(self.btn_reports)

        self.btn_backups = QPushButton(_("view_backups"))
        self.btn_backups.setObjectName("btnBackups")
        self.btn_backups.clicked.connect(lambda: self.switch_view(4)) # Connected
        sidebar_layout.addWidget(self.btn_backups)

        self.btn_archive = QPushButton(_("view_archive"))
        self.btn_archive.setObjectName("btnArchive")
        self.btn_archive.clicked.connect(lambda: self.switch_view(5)) # Connected
        sidebar_layout.addWidget(self.btn_archive)

        self.btn_settings = QPushButton(_("view_settings"))
        self.btn_settings.setObjectName("btnSettings")
        self.btn_settings.clicked.connect(lambda: self.switch_view(6)) # Connected
        sidebar_layout.addWidget(self.btn_settings)

        self.btn_exit = QPushButton(_("exit"))
        self.btn_exit.setObjectName("btnExit")
        self.btn_exit.clicked.connect(self.close)
        sidebar_layout.addWidget(self.btn_exit)

    def create_main_views(self):
        """Create the main content views for the stacked widget."""
        if not hasattr(self, 'stacked_widget'):
            self.logger.error("Stacked widget not found when trying to create main views.")
            return

        # Instantiate views, passing the current user
        self.dashboard_view = DashboardView(self.current_user)
        self.employees_view = EmployeeView(self.current_user)
        self.attendance_view = AttendanceView(self.current_user)
        self.reports_view = ReportsView(self.current_user)
        
        # Ensure BackupsView is only instantiated once
        if not hasattr(self, 'backups_view'): 
            self.backups_view = BackupsView(self.current_user)
            
        self.archive_view = ArchiveView(self.current_user)
        
        # Pass main window reference for potential restart logic
        if not hasattr(self, 'settings_view'):
            self.settings_view = SettingsView(self.current_user, self)

        # Add views to the stacked widget in the correct order
        # Order must match switch_view indices: 0=Dashboard, 1=Employees, etc.
        self.stacked_widget.addWidget(self.dashboard_view)
        self.stacked_widget.addWidget(self.employees_view)
        self.stacked_widget.addWidget(self.attendance_view)
        self.stacked_widget.addWidget(self.reports_view)
        self.stacked_widget.addWidget(self.backups_view)
        self.stacked_widget.addWidget(self.archive_view)
        self.stacked_widget.addWidget(self.settings_view)

    def connect_signals(self):
        """Connect signals between different views for real-time updates."""
        # When an employee is changed in EmployeeView, reload the filter data in AttendanceView
        self.employees_view.employee_changed.connect(self.attendance_view.load_filter_data)
        self.logger.debug("Connected employee_changed signal from EmployeeView to AttendanceView.")

        # Also, reload the employee list in the Dashboard's Quick Clock-In
        self.employees_view.employee_changed.connect(self.dashboard_view.load_employees)
        self.logger.debug("Connected employee_changed signal from EmployeeView to DashboardView.")

    def switch_view(self, index: int):
        """Switch the main view in the stacked widget and update button states."""
        if hasattr(self, 'stacked_widget'):
            self.stacked_widget.setCurrentIndex(index)
            view_names = {
                0: "Dashboard", 1: "Employees", 2: "Attendance",
                3: "Reports", 4: "Backups", 5: "Archive", 6: "Settings"
            }
            self.status_bar.showMessage(f"View: {view_names.get(index, 'Unknown')}")

            # --- ADD THIS BLOCK ---
            # Refresh specific views when switched to
            if index == 4 and hasattr(self, 'backups_view'):
                # Refresh the Backups view to show latest backups
                self.backups_view.refresh_view()
            # Add similar lines here for other views if needed in the future
            # e.g., elif index == 1 and hasattr(self, 'employees_view'):
            #           self.employees_view.refresh_view() # if EmployeesView had such a method
            # --- END OF ADDITION ---

            # Update sidebar button styles to indicate active view (basic implementation)
            # Make sure all buttons are accounted for
            buttons = [
                self.btn_dashboard, self.btn_employees, self.btn_attendance,
                self.btn_reports, self.btn_backups, self.btn_archive, self.btn_settings
            ]
            for i, btn in enumerate(buttons):
                if i == index:
                    btn.setStyleSheet("""
                        QPushButton {
                            text-align: left;
                            padding: 10px;
                            border: none;
                            border-radius: 4px;
                            background-color: #11563a; /* Active color */
                            color: white;
                            margin: 2px 5px;
                        }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton {
                            text-align: left;
                            padding: 10px;
                            border: none;
                            border-radius: 4px;
                            background-color: transparent;
                            margin: 2px 5px;
                        }
                        QPushButton:hover {
                            background-color: #e0e0e0;
                        }
                    """)
        else:
            self.logger.warning("Attempted to switch view, but stacked_widget is not initialized.")

    def update_ui_for_user_role(self):
        """Show or hide UI elements based on the logged-in user's role."""
        if not self.current_user:
            self.logger.warning("update_ui_for_user_role called but no user is logged in.")
            return

        is_admin = self.current_user.role == "admin"
        self.logger.debug(f"Updating UI for role: {'Admin' if is_admin else 'Operator'}")

        # Show/Hide admin-only sidebar buttons
        admin_buttons = [self.btn_reports, self.btn_backups, self.btn_archive, self.btn_settings]
        for btn in admin_buttons:
            btn.setVisible(is_admin) # Set visibility directly

        self.logger.debug(f"Admin buttons visibility set to: {is_admin}")

    def load_resources(self):
        """Load external resources like fonts and icons."""
        try:
            # --- Load Fonts ---
            font_path = get_font_path("Vazir-Regular.ttf")
            if font_path and font_path.exists():
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                if font_id != -1:
                    font_families = QFontDatabase.applicationFontFamilies(font_id)
                    if font_families:
                        font_family = font_families[0]
                        self.logger.info(f"Loaded font: {font_family}")
                        self.default_font_family = font_family
                    else:
                        self.logger.warning(f"Font loaded but no family found for {font_path}")
                else:
                    self.logger.warning(f"Failed to load font from {font_path}")
            else:
                self.logger.warning("Vazir font file not found. UI might not display Persian text correctly.")

        except Exception as e:
            self.logger.error(f"Error loading resources: {e}", exc_info=True)

    def closeEvent(self, event):
        """Handle the window close event."""
        # --- Stop the backup timer on application close ---
        if self.backup_timer and self.backup_timer.isActive():
            self.backup_timer.stop()
            self.logger.debug("Backup timer stopped on application close.")
        # ---
        
        reply = QMessageBox.question(
            self, _("confirm_exit"),
            _("are_you_sure_quit"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.logger.info("Application closed by user.")
            event.accept()
        else:
            event.ignore()

# Example usage (if run directly for testing the window *after* login logic)
# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     window = MainWindow()
#     sys.exit(app.exec())
