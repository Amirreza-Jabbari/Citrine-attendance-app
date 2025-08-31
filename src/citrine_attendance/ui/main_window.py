# src/citrine_attendance/ui/main_window.py
"""Main application window with a modern UI."""
import sys
import logging
from datetime import timedelta
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QStatusBar, QMessageBox,
    QSizePolicy, QFrame, QDialog
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QFontDatabase, QIcon

from ..config import config
from ..utils.resources import get_font_path, get_icon_path
from .dialogs.login_dialog import LoginDialog
from ..database import User
from .views.dashboard_view import DashboardView
from .views.employee_view import EmployeeView
from .views.attendance_view import AttendanceView
from .views.backups_view import BackupsView
from .views.reports_view import ReportsView
from .views.archive_view import ArchiveView
from .views.settings_view import SettingsView
from ..services.backup_service import backup_service, BackupServiceError
from ..locale import _

class MainWindow(QMainWindow):
    """Main application window with a modern, consistent UI."""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = None
        self.backup_timer = None
        self.nav_buttons = []

        self.setWindowTitle(_("app_title"))
        self.setGeometry(100, 100, 1280, 800)
        self.setWindowIcon(QIcon(str(get_icon_path("icon.ico"))))

        # Initial placeholder before login
        self.placeholder_widget = QLabel(_("status_initializing"))
        self.placeholder_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Apply base styling for the placeholder
        self.setStyleSheet("background-color: #2c3e50; font-family: Vazir, Segoe UI, Arial, sans-serif;")
        self.placeholder_widget.setStyleSheet("font-size: 20px; color: #bdc3c7;")
        self.setCentralWidget(self.placeholder_widget)
        
        self.hide()

        self.load_resources()
        QTimer.singleShot(0, self.show_login_and_ui)

    def show_login_and_ui(self):
        """Orchestrates the login flow and subsequent UI initialization."""
        if self.show_login():
            self.init_main_ui()
            self.update_ui_for_user_role()
            self.connect_signals()
            self.setup_automatic_backup()
            self.show()
            self.raise_()
            self.activateWindow()
        else:
            QApplication.instance().quit()

    def show_login(self) -> bool:
        """Shows the login dialog and returns True on success."""
        login_dialog = LoginDialog(self)
        login_dialog.login_successful.connect(self.on_login_successful)
        result = login_dialog.exec()
        return result == QDialog.DialogCode.Accepted

    def on_login_successful(self, user: User):
        """Handles successful login."""
        self.current_user = user
        self.logger.info(f"Main window updated for user: {user.username} (Role: {user.role})")

    def init_main_ui(self):
        """Initializes the main application UI after a successful login."""
        self.logger.debug("Initializing modern main UI components...")
        
        self.apply_stylesheet()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_h_layout = QHBoxLayout(central_widget)
        main_h_layout.setContentsMargins(0, 0, 0, 0)
        main_h_layout.setSpacing(0)

        self.create_sidebar()
        main_h_layout.addWidget(self.sidebar)

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setObjectName("contentArea")
        self.create_main_views()
        main_h_layout.addWidget(self.stacked_widget)
        
        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("statusBar")
        self.setStatusBar(self.status_bar)

        self.switch_view(0) # Default to dashboard
        self.logger.debug("Modern main UI initialized.")

    def create_sidebar(self):
        """Creates the modern sidebar navigation with icons."""
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)
        
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(10, 15, 10, 10)
        sidebar_layout.setSpacing(5)
        
        title_label = QLabel(_("company_name"))
        title_label.setObjectName("sidebarTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(title_label)
        sidebar_layout.addSpacing(20)

        # Navigation Buttons
        self.btn_dashboard = self.create_nav_button(_("view_dashboard"), "grid.svg", 0)
        self.btn_employees = self.create_nav_button(_("view_employees"), "users.svg", 1)
        self.btn_attendance = self.create_nav_button(_("view_attendance"), "clock.svg", 2)
        self.btn_reports = self.create_nav_button(_("view_reports"), "bar-chart-2.svg", 3)
        self.btn_backups = self.create_nav_button(_("view_backups"), "database.svg", 4)
        self.btn_archive = self.create_nav_button(_("view_archive"), "archive.svg", 5)
        self.btn_settings = self.create_nav_button(_("view_settings"), "settings.svg", 6)

        self.nav_buttons = [
            self.btn_dashboard, self.btn_employees, self.btn_attendance,
            self.btn_reports, self.btn_backups, self.btn_archive, self.btn_settings
        ]
        for btn in self.nav_buttons:
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        # User Info Panel
        user_frame = QFrame()
        user_frame.setObjectName("userFrame")
        user_frame_layout = QVBoxLayout(user_frame)
        self.user_label = QLabel(self.current_user.username)
        self.user_label.setObjectName("userLabel")
        self.role_label = QLabel(self.current_user.role.capitalize())
        self.role_label.setObjectName("roleLabel")
        user_frame_layout.addWidget(self.user_label)
        user_frame_layout.addWidget(self.role_label)
        sidebar_layout.addWidget(user_frame)

        # Exit Button
        self.btn_exit = self.create_nav_button(_("exit"), "log-out.svg", -1)
        self.btn_exit.clicked.connect(self.close)
        sidebar_layout.addWidget(self.btn_exit)

    def create_nav_button(self, text: str, icon_name: str, index: int) -> QPushButton:
        """Factory method for creating a sidebar navigation button."""
        button = QPushButton(text)
        button.setObjectName("navButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIconSize(QSize(20, 20))
        try:
            button.setIcon(QIcon(str(get_icon_path(icon_name))))
        except Exception as e:
            self.logger.error(f"Could not load icon {icon_name}: {e}")
        
        if index != -1: # -1 is for non-view buttons like exit
            button.clicked.connect(lambda: self.switch_view(index))
        return button

    def create_main_views(self):
        """Instantiates and adds all main views to the stacked widget."""
        self.dashboard_view = DashboardView(self.current_user)
        self.employees_view = EmployeeView(self.current_user)
        self.attendance_view = AttendanceView(self.current_user)
        self.reports_view = ReportsView(self.current_user)
        self.backups_view = BackupsView(self.current_user)
        self.archive_view = ArchiveView(self.current_user)
        self.settings_view = SettingsView(self.current_user, self)

        self.stacked_widget.addWidget(self.dashboard_view)
        self.stacked_widget.addWidget(self.employees_view)
        self.stacked_widget.addWidget(self.attendance_view)
        self.stacked_widget.addWidget(self.reports_view)
        self.stacked_widget.addWidget(self.backups_view)
        self.stacked_widget.addWidget(self.archive_view)
        self.stacked_widget.addWidget(self.settings_view)

    def switch_view(self, index: int):
        """Switches the main view and updates the active button style."""
        self.stacked_widget.setCurrentIndex(index)
        
        for i, btn in enumerate(self.nav_buttons):
            btn.setProperty("active", i == index)
            # Re-polish to apply property-based stylesheet changes
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        # Refresh specific views when they become active
        if index == 1: # Employees view
            self.employees_view.load_employees()
        elif index == 4: # Backups view
            self.backups_view.refresh_view()
        
        view_names = [_("view_dashboard"), _("view_employees"), _("view_attendance"),
                      _("view_reports"), _("view_backups"), _("view_archive"), _("view_settings")]
        self.status_bar.showMessage(f"{_('status_view')}: {view_names[index]}")

    def update_ui_for_user_role(self):
        """Shows or hides UI elements based on the user's role."""
        is_admin = self.current_user.role == "admin"
        self.logger.debug(f"Updating UI for role: {'Admin' if is_admin else 'Operator'}")
        
        self.btn_reports.setVisible(is_admin)
        self.btn_backups.setVisible(is_admin)
        self.btn_archive.setVisible(is_admin)
        self.btn_settings.setVisible(is_admin)

    def setup_automatic_backup(self):
        """Configures and starts the automatic backup timer."""
        if self.current_user.role != "admin":
            return

        try:
            frequency_days = config.settings.get("backup_frequency_days", 1)
            if frequency_days <= 0:
                self.logger.info("Automatic backup is disabled.")
                return

            interval_ms = int(timedelta(days=frequency_days).total_seconds() * 1000)
            self.backup_timer = QTimer(self)
            self.backup_timer.timeout.connect(self.perform_scheduled_backup)
            self.backup_timer.start(max(interval_ms, 60000)) # Minimum 1 minute interval
            self.logger.info(f"Automatic backup scheduled every {frequency_days} day(s).")
        except Exception as e:
            self.logger.error(f"Failed to setup automatic backup timer: {e}", exc_info=True)

    def perform_scheduled_backup(self):
        """Performs a scheduled backup via the backup service."""
        if self.current_user.role != "admin":
            return
        try:
            backup_path = backup_service.create_backup(manual=False)
            self.logger.info(f"Scheduled backup created: {backup_path}")
        except (BackupServiceError, Exception) as e:
            self.logger.error(f"Scheduled backup failed: {e}", exc_info=True)

    def connect_signals(self):
        """Connects signals between different views."""
        self.employees_view.employee_changed.connect(self.attendance_view.load_filter_data)
        self.employees_view.employee_changed.connect(self.dashboard_view.refresh_data)

    def load_resources(self):
        """Loads application-wide resources like fonts."""
        try:
            font_path = str(get_font_path("Vazir-Regular.ttf"))
            if QFontDatabase.addApplicationFont(font_path) == -1:
                self.logger.warning("Failed to load Vazir font.")
        except Exception as e:
            self.logger.error(f"Error loading resources: {e}", exc_info=True)

    def apply_stylesheet(self):
        """Applies the modern dark theme stylesheet to the main window and its children."""
        self.setStyleSheet("""
            QMainWindow, QDialog {
                background-color: #2c3e50;
                font-family: Vazir, Segoe UI, Arial, sans-serif;
                color: #ecf0f1;
            }
            #sidebar {
                background-color: #2c3e50;
                border-right: 1px solid #34495e;
            }
            #sidebarTitle {
                font-size: 24px;
                font-weight: bold;
                color: #ecf0f1;
            }
            QPushButton#navButton {
                color: #bdc3c7;
                background-color: transparent;
                border: none;
                padding: 12px;
                border-radius: 8px;
                text-align: left;
                font-size: 14px;
            }
            QPushButton#navButton:hover {
                background-color: #34495e;
                color: #ecf0f1;
            }
            QPushButton#navButton[active="true"] {
                background-color: #3498db;
                color: white;
                font-weight: bold;
            }
            #contentArea > QWidget {
                background-color: #34495e;
                color: #ecf0f1;
            }
            QStatusBar#statusBar {
                background-color: #2c3e50;
                color: #bdc3c7;
            }
            QStatusBar#statusBar::item {
                border: 0px;
            }
            #userFrame {
                border-top: 1px solid #34495e;
                padding-top: 10px;
                margin-top: 10px;
            }
            #userLabel {
                font-size: 14px;
                font-weight: bold;
                color: #ecf0f1;
            }
            #roleLabel {
                font-size: 12px;
                color: #bdc3c7;
            }

            /* === Global Widget Styles for Views === */
            QLabel {
                color: #ecf0f1;
                font-size: 14px;
                background-color: transparent;
            }
            QLabel#viewTitle {
                font-size: 22px;
                font-weight: bold;
                padding-bottom: 10px;
                border-bottom: 1px solid #4a627a;
                margin-bottom: 15px;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 10px 15px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #1f618d;
            }
            QPushButton:disabled {
                background-color: #566573;
                color: #95a5a6;
            }
            
            /* Specific Button Colors */
            QPushButton#deleteButton { background-color: #c0392b; }
            QPushButton#deleteButton:hover { background-color: #a93226; }
            QPushButton#editButton { background-color: #f39c12; }
            QPushButton#editButton:hover { background-color: #d68910; }
            QPushButton#saveButton { background-color: #27ae60; }
            QPushButton#saveButton:hover { background-color: #229954; }

            QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox {
                background-color: #2c3e50;
                color: #ecf0f1;
                border: 1px solid #4a627a;
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
            }
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus {
                border: 1px solid #3498db;
            }
            QTableView {
                background-color: #2c3e50;
                color: #ecf0f1;
                border: 1px solid #4a627a;
                gridline-color: #4a627a;
                border-radius: 8px;
                selection-background-color: #3498db;
            }
            QTableView::item {
                padding: 5px;
                border-bottom: 1px solid #4a627a;
            }
            QTableView::item:alternate {
                background-color: #34495e; /* Lighter shade for alternating rows */
            }
            QHeaderView::section {
                background-color: #34495e;
                color: #ecf0f1;
                padding: 8px;
                border: 1px solid #4a627a;
                font-weight: bold;
            }
            QGroupBox {
                border: 1px solid #4a627a;
                border-radius: 8px;
                margin-top: 10px;
                padding: 10px;
                padding-top: 25px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 10px;
                margin-left: 10px;
                color: #ecf0f1;
                font-weight: bold;
            }
            QTabWidget::pane {
                border: 1px solid #4a627a;
                border-top: none;
                background-color: #34495e;
                padding: 15px;
            }
            QTabBar::tab {
                background: #2c3e50;
                color: #bdc3c7;
                border: 1px solid #4a627a;
                border-bottom: none;
                padding: 10px 20px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 2px;
            }
            QTabBar::tab:hover {
                background: #34495e;
            }
            QTabBar::tab:selected {
                background: #34495e;
                color: #ecf0f1;
                font-weight: bold;
            }
            QTextEdit {
                background-color: #2c3e50;
                color: #ecf0f1;
                border: 1px solid #4a627a;
                border-radius: 8px;
                padding: 8px;
                font-family: "Courier New", Courier, monospace;
            }
        """)

    def closeEvent(self, event):
        """Handles the window close event."""
        if self.backup_timer and self.backup_timer.isActive():
            self.backup_timer.stop()
        
        reply = QMessageBox.question(self, _("confirm_exit"), _("are_you_sure_quit"),
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

