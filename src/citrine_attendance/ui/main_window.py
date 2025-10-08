# src/citrine_attendance/ui/main_window.py
"""Main application window with a modern UI (light, readable color palette)."""
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
    """Main application window with a modern, light and readable UI."""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = None
        self.backup_timer = None
        self.nav_buttons = []

        self.setWindowTitle(_("app_title"))
        self.setGeometry(100, 100, 1280, 800)
        try:
            self.setWindowIcon(QIcon(str(get_icon_path("icon.ico"))))
        except Exception:
            # ignore if icon missing during development
            pass

        # Initial placeholder before login
        self.placeholder_widget = QLabel(_("status_initializing"))
        self.placeholder_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Apply base styling for the placeholder (light theme)
        self.setStyleSheet("background-color: #ffffff; font-family: Vazir, 'Segoe UI', Arial, sans-serif;")
        self.placeholder_widget.setStyleSheet("font-size: 20px; color: #6b7280;")
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

        self.switch_view(0)  # Default to dashboard
        self.logger.debug("Modern main UI initialized.")

    def create_sidebar(self):
        """Creates the modern sidebar navigation with icons (light palette)."""
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(240)  # a bit wider for better spacing
        
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 12)
        sidebar_layout.setSpacing(8)
        
        title_label = QLabel(_("company_name"))
        title_label.setObjectName("sidebarTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(title_label)
        sidebar_layout.addSpacing(12)

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
        # Guard against None current_user in some paths
        username_text = getattr(self.current_user, "username", _("guest")) if self.current_user else _("guest")
        role_text = getattr(self.current_user, "role", "operator").capitalize() if self.current_user else _("operator")
        self.user_label = QLabel(username_text)
        self.user_label.setObjectName("userLabel")
        self.role_label = QLabel(role_text)
        self.role_label.setObjectName("roleLabel")
        user_frame_layout.addWidget(self.user_label)
        user_frame_layout.addWidget(self.role_label)
        sidebar_layout.addWidget(user_frame)

        # Exit Button
        self.btn_exit = self.create_nav_button(_("exit"), "log-out.svg", -1)
        self.btn_exit.clicked.connect(self.close)
        sidebar_layout.addWidget(self.btn_exit)

    def create_nav_button(self, text: str, icon_name: str, index: int) -> QPushButton:
        """Factory method for creating a sidebar navigation button (light theme friendly)."""
        button = QPushButton(text)
        button.setObjectName("navButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIconSize(QSize(18, 18))
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        try:
            button.setIcon(QIcon(str(get_icon_path(icon_name))))
        except Exception as e:
            self.logger.error(f"Could not load icon {icon_name}: {e}")
        
        if index != -1:  # -1 is for non-view buttons like exit
            button.clicked.connect(lambda _, i=index: self.switch_view(i))
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
        if index == 1:  # Employees view
            try:
                self.employees_view.load_employees()
            except Exception:
                self.logger.exception("Failed to refresh employees view.")
        elif index == 4:  # Backups view
            try:
                self.backups_view.refresh_view()
            except Exception:
                self.logger.exception("Failed to refresh backups view.")
        
        view_names = [_("view_dashboard"), _("view_employees"), _("view_attendance"),
                      _("view_reports"), _("view_backups"), _("view_archive"), _("view_settings")]
        # ensure index in range
        if 0 <= index < len(view_names):
            self.status_bar.showMessage(f"{_('status_view')}: {view_names[index]}")
        else:
            self.status_bar.clearMessage()

    def update_ui_for_user_role(self):
        """Shows or hides UI elements based on the user's role."""
        is_admin = getattr(self.current_user, "role", "") == "admin"
        self.logger.debug(f"Updating UI for role: {'Admin' if is_admin else 'Operator'}")
        
        # Hide admin-only buttons for non-admins
        self.btn_reports.setVisible(is_admin)
        self.btn_backups.setVisible(is_admin)
        self.btn_archive.setVisible(is_admin)
        self.btn_settings.setVisible(is_admin)

    def setup_automatic_backup(self):
        """Configures and starts the automatic backup timer."""
        if getattr(self.current_user, "role", "") != "admin":
            return

        try:
            frequency_days = config.settings.get("backup_frequency_days", 1)
            if frequency_days <= 0:
                self.logger.info("Automatic backup is disabled.")
                return

            interval_ms = int(timedelta(days=frequency_days).total_seconds() * 1000)
            self.backup_timer = QTimer(self)
            self.backup_timer.timeout.connect(self.perform_scheduled_backup)
            self.backup_timer.start(max(interval_ms, 60000))  # Minimum 1 minute interval
            self.logger.info(f"Automatic backup scheduled every {frequency_days} day(s).")
        except Exception as e:
            # HEROIC FIX: avoid recursion in Python 3.13 logging
            self.logger.error(f"Failed to setup automatic backup timer: {e}")

    def perform_scheduled_backup(self):
        """Performs a scheduled backup via the backup service."""
        if getattr(self.current_user, "role", "") != "admin":
            return
        try:
            backup_path = backup_service.create_backup(manual=False)
            self.logger.info(f"Scheduled backup created: {backup_path}")
        except (BackupServiceError, Exception) as e:
            # HEROIC FIX: avoid recursion in Python 3.13 logging
            self.logger.error(f"Scheduled backup failed: {e}")

    def connect_signals(self):
        """Connects signals between different views."""
        try:
            self.employees_view.employee_changed.connect(self.attendance_view.load_filter_data)
            self.employees_view.employee_changed.connect(self.dashboard_view.refresh_data)
            # HEROIC FIX: Connect language change signal
            self.settings_view.language_changed.connect(self.on_language_changed)
        except Exception:
            self.logger.debug("Could not connect some signals (views may not implement expected signals).", exc_info=True)

    def on_language_changed(self, language):
        """HEROIC FIX: Handle language change - update all UI elements."""
        try:
            self.logger.info(f"Language changed to: {language}")
            
            # Update window title
            self.setWindowTitle(_("app_title"))
            
            # Update layout direction for RTL languages
            if language == "fa":
                QApplication.instance().setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            else:
                QApplication.instance().setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            
            # Update sidebar elements
            self.update_sidebar_texts()
            
            # Update status bar if needed
            current_index = self.stacked_widget.currentIndex()
            view_names = [_("view_dashboard"), _("view_employees"), _("view_attendance"),
                          _("view_reports"), _("view_backups"), _("view_archive"), _("view_settings")]
            if 0 <= current_index < len(view_names):
                self.status_bar.showMessage(f"{_('status_view')}: {view_names[current_index]}")
            
            # Force refresh all views to update their text
            self.refresh_all_views()
            
        except Exception as e:
            # HEROIC FIX: avoid recursion in Python 3.13 logging
            self.logger.error(f"Error handling language change: {e}")
    
    def update_sidebar_texts(self):
        """HEROIC FIX: Update all sidebar button texts."""
        try:
            # Update navigation buttons
            self.btn_dashboard.setText(_("view_dashboard"))
            self.btn_employees.setText(_("view_employees"))
            self.btn_attendance.setText(_("view_attendance"))
            self.btn_reports.setText(_("view_reports"))
            self.btn_backups.setText(_("view_backups"))
            self.btn_archive.setText(_("view_archive"))
            self.btn_settings.setText(_("view_settings"))
            self.btn_exit.setText(_("exit"))
            
            # Update sidebar title (company name doesn't need translation usually)
            # But we can update it if needed
            
        except Exception as e:
            # HEROIC FIX: avoid recursion in Python 3.13 logging
            self.logger.error(f"Error updating sidebar texts: {e}")
    
    def refresh_all_views(self):
        """HEROIC FIX: Refresh all views to update their translated texts."""
        try:
            # Refresh each view that has data or UI elements
            if hasattr(self.dashboard_view, 'refresh_data'):
                self.dashboard_view.refresh_data()
            
            if hasattr(self.employees_view, 'load_employees'):
                self.employees_view.load_employees()
            
            if hasattr(self.attendance_view, 'load_filter_data'):
                self.attendance_view.load_filter_data()
                if hasattr(self.attendance_view, 'load_attendance_data'):
                    self.attendance_view.load_attendance_data()
            
            if hasattr(self.archive_view, 'refresh_view'):
                self.archive_view.refresh_view()
            
            if hasattr(self.backups_view, 'refresh_view'):
                self.backups_view.refresh_view()
            
            # Force widget update to apply new layout direction
            self.update()
            QApplication.processEvents()
            
        except Exception as e:
            # HEROIC FIX: avoid recursion in Python 3.13 logging
            self.logger.error(f"Error refreshing views: {e}")
    
    def load_resources(self):
        """Loads application-wide resources like fonts."""
        try:
            font_path = str(get_font_path("Vazir-Regular.ttf"))
            if QFontDatabase.addApplicationFont(font_path) == -1:
                self.logger.warning("Failed to load Vazir font.")
        except Exception as e:
            # HEROIC FIX: avoid recursion in Python 3.13 logging
            self.logger.error(f"Error loading resources: {e}")

    def apply_stylesheet(self):
        """Applies a modern light theme stylesheet to the main window and its children."""
        # Color choices aimed for: high contrast text, calm light backgrounds, clear accents.
        self.setStyleSheet("""
            /* --- Window + Dialogs --- */
            QMainWindow, QDialog {
                background-color: #ffffff; /* base white */
                font-family: Vazir, 'Segoe UI', Arial, sans-serif;
                color: #0f172a; /* dark slate for high contrast */
            }

            /* --- Sidebar --- */
            #sidebar {
                background-color: #f4f6f8; /* light gray */
                border-right: 1px solid #e6edf3;
            }
            #sidebarTitle {
                font-size: 20px;
                font-weight: 700;
                color: #0f172a; /* strong heading color */
                padding: 6px 0;
            }

            /* --- Navigation Buttons --- */
            QPushButton#navButton {
                color: #0f172a;
                background-color: transparent;
                border: none;
                padding: 10px 14px;
                border-radius: 8px;
                text-align: left;
                font-size: 14px;
                min-height: 40px;
            }
            /* remove default dotted focus look and replace with subtle highlight */
            QPushButton#navButton:focus {
                outline: none;
                border-left: 4px solid rgba(11,109,243,0.08);
                background-color: #f7fbff;
            }
            QPushButton#navButton:hover {
                background-color: #f0f6ff; /* soft blue hover */
                color: #0b6df3; /* accent color on hover */
            }
            /* property-based active state (Qt turns booleans into "true"/"false") */
            QPushButton#navButton[active="true"] {
                background-color: #eaf4ff; /* subtle active background */
                color: #0b6df3;
                font-weight: 700;
                border-left: 4px solid #0b6df3;
                padding-left: 12px;
            }

            /* --- Content Area --- */
            #contentArea > QWidget {
                background-color: #ffffff;
                color: #0f172a;
            }

            /* --- Status Bar --- */
            QStatusBar#statusBar {
                background-color: #ffffff;
                color: #475569;
                border-top: 1px solid #eef2f7;
                padding: 4px 8px;
            }
            QStatusBar#statusBar::item {
                border: 0px;
            }

            /* --- User Panel --- */
            #userFrame {
                border-top: 1px solid #eef2f7;
                padding-top: 12px;
                margin-top: 12px;
            }
            #userLabel {
                font-size: 14px;
                font-weight: 700;
                color: #0f172a;
            }
            #roleLabel {
                font-size: 12px;
                color: #6b7280;
            }

            /* === Global Widget Styles for Views (light + readable) === */
            QLabel {
                color: #0f172a;
                font-size: 14px;
                background-color: transparent;
            }
            QLabel#viewTitle {
                font-size: 22px;
                font-weight: 700;
                padding-bottom: 10px;
                border-bottom: 1px solid #e6edf3;
                margin-bottom: 14px;
                color: #0b2545;
            }

            /* Primary buttons (blue) */
            QPushButton {
                background-color: #0b6df3; /* accessible, saturated blue */
                color: white;
                font-size: 14px;
                font-weight: 600;
                border: none;
                border-radius: 8px;
                padding: 8px 14px;
                min-height: 36px;
            }
            QPushButton:hover {
                background-color: #095bd0;
            }
            QPushButton:pressed {
                background-color: #084bb0;
            }
            QPushButton:disabled {
                background-color: #c7d2e8;
                color: #6b7280;
            }

            /* Specific Button Colors */
            QPushButton#deleteButton { background-color: #ef4444; } /* red */
            QPushButton#deleteButton:hover { background-color: #dc2626; }
            QPushButton#editButton { background-color: #f59e0b; } /* amber */
            QPushButton#editButton:hover { background-color: #d97706; }
            QPushButton#saveButton { background-color: #10b981; } /* green */
            QPushButton#saveButton:hover { background-color: #059669; }

            /* Form inputs - light with clear borders */
            QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox {
                background-color: #ffffff;
                color: #0b1220;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
                min-height: 34px;
            }
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus {
                border: 1px solid #0b6df3; /* blue focus ring */
            }

            /* Dropdown arrow color + popup background */
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #0b1220;
                selection-background-color: #e6f0ff;
            }

            /* Table styling - white rows + subtle stripes */
            QTableView {
                background-color: #ffffff;
                color: #0b1220;
                border: 1px solid #e6edf3;
                gridline-color: #e6edf3;
                border-radius: 8px;
                selection-background-color: #d6e9ff;
                selection-color: #0b2545;
            }
            QTableView::item {
                padding: 6px;
                border-bottom: 1px solid #f1f5f9;
            }
            QTableView::item:alternate {
                background-color: #fbfdff; /* very subtle alternate */
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #0f172a;
                padding: 8px;
                border: 1px solid #e6edf3;
                font-weight: 600;
            }

            /* Group boxes and tabs */
            QGroupBox {
                border: 1px solid #e6edf3;
                border-radius: 8px;
                margin-top: 10px;
                padding: 10px;
                padding-top: 25px;
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 10px;
                margin-left: 10px;
                color: #0f172a;
                font-weight: 700;
            }
            QTabWidget::pane {
                border: 1px solid #e6edf3;
                border-top: none;
                background-color: #ffffff;
                padding: 12px;
            }
            QTabBar::tab {
                background: #f4f6f8;
                color: #0f172a;
                border: 1px solid #e6edf3;
                border-bottom: none;
                padding: 8px 16px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 4px;
            }
            QTabBar::tab:hover {
                background: #eef6ff;
                color: #0b6df3;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #0b6df3;
                font-weight: 700;
            }

            QTextEdit {
                background-color: #ffffff;
                color: #0b1220;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 8px;
                font-family: "Courier New", Courier, monospace;
            }

            /* Accessibility helpers: increase clickable area for small widgets */
            QPushButton, QComboBox, QLineEdit, QSpinBox {
                min-height: 36px;
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

# If run directly (for development/testing), allow starting the app:
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    app = QApplication(sys.argv)
    mw = MainWindow()
    # For quick testing without login dialog, you can inject a fake user:
    # try:
    #     mw.on_login_successful(User(username="dev", role="admin"))
    # except Exception:
    #     pass
    mw.show()
    sys.exit(app.exec())
