# src/citrine_attendance/ui/views/dashboard_view.py
"""Dashboard view for the main window."""
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QDateEdit, QMessageBox
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont
import jdatetime
import datetime

from ...services.employee_service import employee_service
from ...services.attendance_service import attendance_service
from ...database import get_db_session
from ...date_utils import gregorian_to_jalali, format_jalali_date
from ...locale import _


class DashboardView(QWidget):
    """The main dashboard view widget."""

    def __init__(self, current_user):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.db_session = None # Will get session when needed
        self.init_ui()
        self.refresh_data() # Load initial data

    def init_ui(self):
        """Initialize the dashboard UI elements."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20) # Add some margins

        # Welcome/User Info Card
        welcome_card = self.create_welcome_card()
        main_layout.addWidget(welcome_card)

        # KPI Cards Layout (Horizontal)
        kpi_cards_layout = self.create_kpi_cards()
        main_layout.addLayout(kpi_cards_layout)

        # Quick Actions Section
        actions_label = QLabel(_("dashboard_quick_actions"))
        actions_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        main_layout.addWidget(actions_label)

        # Quick Clock-In Section
        clockin_section = self.create_quick_clockin_section()
        main_layout.addWidget(clockin_section)

        # Spacer to push content up
        main_layout.addStretch()

        self.clockin_btn.clicked.connect(lambda: self.on_action_clicked("in"))
        self.clockout_btn.clicked.connect(lambda: self.on_action_clicked("out"))

    def create_welcome_card(self):
        """Create the welcome/user info card."""
        welcome_card = QFrame()
        welcome_card.setFrameShape(QFrame.Shape.StyledPanel)
        welcome_card.setStyleSheet("""
            background-color: #ffffff;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
        """)
        welcome_layout = QHBoxLayout(welcome_card)
        welcome_label = QLabel(_("dashboard_welcome", username=self.current_user.username))
        welcome_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        role_label = QLabel(_("dashboard_role", role=self.current_user.role.capitalize()))
        role_label.setStyleSheet("color: #757575;")
        # Spacer to push role label to the right
        welcome_layout.addWidget(welcome_label)
        welcome_layout.addStretch()
        welcome_layout.addWidget(role_label)
        return welcome_card

    def create_kpi_cards(self):
        """Create the KPI summary cards layout."""
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(15)

        # Initialize with 0s, will be updated by refresh_data
        self.kpi_present_value = QLabel("0")
        self.kpi_absent_value = QLabel("0")

        kpi_data = [
            {"title": _("dashboard_present_today"), "value_label": self.kpi_present_value, "color": "#c8e6c9", "tooltip": "Employees clocked in today"},
            {"title": _("dashboard_absent_today"), "value_label": self.kpi_absent_value, "color": "#ffcdd2", "tooltip": "Employees not clocked in today"},
        ]

        self.kpi_cards = [] # Keep references to cards for potential styling updates
        for data in kpi_data:
            kpi_card = QFrame()
            kpi_card.setFrameShape(QFrame.Shape.StyledPanel)
            kpi_card.setStyleSheet(f"""
                background-color: {data['color']};
                padding: 15px;
                border-radius: 8px;
                min-width: 150px;
            """)
            kpi_card.setToolTip(data['tooltip'])
            kpi_card_layout = QVBoxLayout(kpi_card)
            kpi_title = QLabel(data["title"])
            kpi_title.setStyleSheet("font-size: 14px; color: #616161;")
            # Use the pre-created label for value
            data["value_label"].setStyleSheet("font-size: 24px; font-weight: bold;")
            kpi_card_layout.addWidget(kpi_title)
            kpi_card_layout.addWidget(data["value_label"])
            kpi_layout.addWidget(kpi_card)
            self.kpi_cards.append(kpi_card)

        # Add stretch to push cards to the left
        kpi_layout.addStretch()
        return kpi_layout

    def create_quick_clockin_section(self):
        """Create the quick clock-in section."""
        clockin_frame = QFrame()
        clockin_frame.setFrameShape(QFrame.Shape.StyledPanel)
        clockin_frame.setStyleSheet("""
            background-color: #ffffff;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
        """)
        clockin_layout = QVBoxLayout(clockin_frame)

        title_layout = QHBoxLayout()
        title_label = QLabel(_("dashboard_quick_clock_in_out"))
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        clockin_layout.addLayout(title_layout)

        # Employee selection
        emp_layout = QHBoxLayout()
        emp_layout.addWidget(QLabel(_("dashboard_select_employee")))
        self.employee_combo = QComboBox()
        self.employee_combo.setMinimumWidth(200)
        emp_layout.addWidget(self.employee_combo)
        emp_layout.addStretch()
        clockin_layout.addLayout(emp_layout)

        # Action buttons
        btn_layout = QHBoxLayout()
        self.clockin_btn = QPushButton(_("dashboard_clock_in"))
        self.clockin_btn.setStyleSheet(self.get_button_style("#11563a")) # Brand color

        self.clockout_btn = QPushButton(_("dashboard_clock_out"))
        self.clockout_btn.setStyleSheet(self.get_button_style("#ffa500")) # Secondary color

        btn_layout.addWidget(self.clockin_btn)
        btn_layout.addWidget(self.clockout_btn)
        btn_layout.addStretch()
        clockin_layout.addLayout(btn_layout)

        return clockin_frame

    def get_button_style(self, bg_color):
        """Helper to get consistent button styles."""
        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {self.darken_color(bg_color)};
            }}
            QPushButton:disabled {{
                background-color: #bdbdbd;
                color: #9e9e9e;
            }}
        """

    def darken_color(self, color_hex):
        """Simple function to darken a hex color for hover effects."""
        color_hex = color_hex.lstrip('#')
        rgb = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))
        darker_rgb = tuple(max(0, int(c * 0.9)) for c in rgb)
        return f"#{darker_rgb[0]:02x}{darker_rgb[1]:02x}{darker_rgb[2]:02x}"

    def refresh_data(self):
        """Refresh dashboard data like KPIs and employee list."""
        try:
            session_gen = get_db_session()
            self.db_session = next(session_gen)

            # --- Refresh KPIs ---
            today = QDate.currentDate().toPyDate()
            summary = attendance_service.get_daily_summary(today, db=self.db_session)

            self.kpi_present_value.setText(str(summary['present']))
            self.kpi_absent_value.setText(str(summary['absent']))
            self.logger.debug(f"Dashboard KPIs refreshed for {today}: {summary}")

            # --- Refresh Employee Combo Box ---
            self.employee_combo.clear()
            self.employee_combo.addItem("--- Select an Employee ---", None)
            employees = employee_service.get_all_employees(db=self.db_session)
            for emp in employees:
                display_name = f"{emp.first_name} {emp.last_name}".strip() or emp.email
                self.employee_combo.addItem(display_name, emp.id)
            self.logger.debug(f"Employee combo box refreshed with {len(employees)} employees.")

        except Exception as e:
            self.logger.error(f"Error refreshing dashboard data: {e}", exc_info=True)
        finally:
            if self.db_session:
                self.db_session.close()
                self.db_session = None

    def on_action_clicked(self, action_type):
        """Handle Clock In or Clock Out button clicks."""
        emp_id = self.employee_combo.currentData()
        if not emp_id:
            QMessageBox.warning(self, _("dashboard_no_employee_selected"), _("dashboard_please_select_employee"))
            return

        action_name = "Clock-In" if action_type == "in" else "Clock-Out"

        try:
            record = None
            if action_type == "in":
                record = attendance_service.clock_in(emp_id)
            elif action_type == "out":
                record = attendance_service.clock_out(emp_id)
            else:
                self.logger.warning(f"Unknown action type '{action_type}' requested.")
                return

            # Determine the relevant timestamp for the success message
            timestamp = record.time_out if action_type == "out" and record.time_out else record.time_in

            QMessageBox.information(
                self,
                _("dashboard_success"),
                _("dashboard_action_recorded",
                  action=action_name,
                  employee=self.employee_combo.currentText(),
                  date=record.date.strftime('%Y-%m-%d'),
                  time=timestamp.strftime('%H:%M:%S'))
            )
            self.logger.info(f"{action_name} successful for Employee ID {emp_id}.")
            self.refresh_data()

        except Exception as e:
            self.logger.error(f"Error during {action_name} for Employee ID {emp_id}: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to record {action_name.lower()}: {e}")
