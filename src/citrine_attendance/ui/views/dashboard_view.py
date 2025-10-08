# src/citrine_attendance/ui/views/dashboard_view.py
"""Dashboard view with a modern UI."""
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt, QDate

from ...services.employee_service import employee_service
from ...services.attendance_service import attendance_service, AttendanceServiceError
from ...database import get_db_session
from ...locale import _

class DashboardView(QWidget):
    """The main dashboard view widget, styled by the main window's stylesheet."""

    def __init__(self, current_user):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.init_ui()
        # Load initial data for the view
        self.refresh_data()

    def init_ui(self):
        """Initialize the dashboard UI elements."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # View Title
        title_label = QLabel(_("dashboard_title"))
        title_label.setObjectName("viewTitle")
        main_layout.addWidget(title_label)
        
        # User Welcome Message
        welcome_label = QLabel(_("dashboard_welcome", username=self.current_user.username))
        main_layout.addWidget(welcome_label)

        # KPI Cards Layout (Horizontal)
        kpi_layout = self.create_kpi_cards()
        main_layout.addLayout(kpi_layout)

        # Quick Clock-In Section
        clockin_groupbox = self.create_quick_clockin_section()
        main_layout.addWidget(clockin_groupbox)

        # Spacer to push content up
        main_layout.addStretch()

        # Connect signals
        self.clockin_btn.clicked.connect(lambda: self.on_action_clicked("in"))
        self.clockout_btn.clicked.connect(lambda: self.on_action_clicked("out"))

    def create_kpi_cards(self) -> QHBoxLayout:
        """Create the KPI summary cards layout."""
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(20)

        # Initialize value labels
        self.kpi_present_value = QLabel("0")
        self.kpi_present_value.setObjectName("kpiValue")
        self.kpi_absent_value = QLabel("0")
        self.kpi_absent_value.setObjectName("kpiValue")

        # Create Present Card
        present_card = QFrame()
        present_card.setObjectName("kpiCard")
        present_card.setProperty("status", "present")
        present_card_layout = QVBoxLayout(present_card)
        present_title = QLabel(_("dashboard_present_today"))
        present_title.setObjectName("kpiTitle")
        present_card_layout.addWidget(present_title)
        present_card_layout.addWidget(self.kpi_present_value)
        kpi_layout.addWidget(present_card)
        
        # Create Absent Card
        absent_card = QFrame()
        absent_card.setObjectName("kpiCard")
        absent_card.setProperty("status", "absent")
        absent_card_layout = QVBoxLayout(absent_card)
        absent_title = QLabel(_("dashboard_absent_today"))
        absent_title.setObjectName("kpiTitle")
        absent_card_layout.addWidget(absent_title)
        absent_card_layout.addWidget(self.kpi_absent_value)
        kpi_layout.addWidget(absent_card)
        
        kpi_layout.addStretch()
        return kpi_layout

    def create_quick_clockin_section(self) -> QGroupBox:
        """Create the quick clock-in section within a styled group box."""
        clockin_groupbox = QGroupBox(_("dashboard_quick_actions"))
        
        group_layout = QVBoxLayout(clockin_groupbox)
        group_layout.setSpacing(15)

        # Employee selection
        emp_layout = QHBoxLayout()
        emp_layout.addWidget(QLabel(_("dashboard_select_employee")))
        self.employee_combo = QComboBox()
        self.employee_combo.setMinimumWidth(250)
        emp_layout.addWidget(self.employee_combo)
        emp_layout.addStretch()
        group_layout.addLayout(emp_layout)

        # Action buttons
        btn_layout = QHBoxLayout()
        self.clockin_btn = QPushButton(_("dashboard_clock_in"))
        self.clockin_btn.setObjectName("clockInButton")
        self.clockout_btn = QPushButton(_("dashboard_clock_out"))
        self.clockout_btn.setObjectName("clockOutButton")

        btn_layout.addStretch()
        btn_layout.addWidget(self.clockin_btn)
        btn_layout.addWidget(self.clockout_btn)
        group_layout.addLayout(btn_layout)

        return clockin_groupbox

    def refresh_data(self):
        """Refresh dashboard data like KPIs and employee list."""
        self.logger.debug("Refreshing dashboard view data.")
        db = None
        try:
            db = next(get_db_session())
            # Refresh KPIs
            today = QDate.currentDate().toPyDate()
            summary = attendance_service.get_daily_summary(today, db=db)
            self.kpi_present_value.setText(str(summary['present']))
            self.kpi_absent_value.setText(str(summary['absent']))
            self.logger.debug(f"Dashboard KPIs refreshed for {today}: {summary}")

            # Refresh Employee Combo Box
            current_selection = self.employee_combo.currentData()
            self.employee_combo.clear()
            self.employee_combo.addItem(_("select_employee"), None)
            employees = employee_service.get_all_employees(db=db)
            for emp in employees:
                display_name = f"{emp.first_name} {emp.last_name}".strip() or emp.email
                self.employee_combo.addItem(display_name, emp.id)
            
            # Restore previous selection if it still exists
            if current_selection:
                index = self.employee_combo.findData(current_selection)
                if index != -1:
                    self.employee_combo.setCurrentIndex(index)
            
            self.logger.debug(f"Employee combo box refreshed with {len(employees)} employees.")
        except Exception as e:
            # HEROIC FIX: avoid recursion in Python 3.13 logging
            self.logger.error(f"Error refreshing dashboard data: {e}")
            QMessageBox.critical(self, _("error"), _("dashboard_refresh_error", error=str(e)))
        finally:
            if db:
                db.close()

    def on_action_clicked(self, action_type: str):
        """Handle Clock In or Clock Out button clicks."""
        emp_id = self.employee_combo.currentData()
        if not emp_id:
            QMessageBox.warning(self, _("dashboard_no_employee_selected_title"), _("dashboard_please_select_employee"))
            return

        action_name = _("dashboard_clock_in") if action_type == "in" else _("dashboard_clock_out")
        try:
            record = None
            if action_type == "in":
                record = attendance_service.clock_in(emp_id)
            elif action_type == "out":
                record = attendance_service.clock_out(emp_id)
            
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

        except AttendanceServiceError as e:
            self.logger.warning(f"Attendance Error during {action_name} for Employee ID {emp_id}: {e}")
            QMessageBox.warning(self, _("warning"), str(e))
        except Exception as e:
            # HEROIC FIX: avoid recursion in Python 3.13 logging
            self.logger.error(f"Error during {action_name} for Employee ID {emp_id}: {e}")
            QMessageBox.critical(self, _("error"), _("dashboard_action_failed", action=action_name.lower(), error=str(e)))

