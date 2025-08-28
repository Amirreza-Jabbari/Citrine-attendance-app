# src/citrine_attendance/ui/views/reports_view.py
import logging
from datetime import date, timedelta
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTextEdit, QMessageBox, QDateEdit, QDialog, QFileDialog
)
from PyQt6.QtCore import Qt, QDate

from ...services.attendance_service import attendance_service
from ...services.employee_service import employee_service
from ...services.export_service import export_service, ExportServiceError
from ...database import get_db_session
from ...locale import _


class ReportsView(QWidget):
    """The reports generation view widget."""

    def __init__(self, current_user):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.last_generated_data = [] # Cache the data for export

        self.init_ui()
        self.load_employee_data()

    def init_ui(self):
        """Initialize the reports view UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)

        # --- Parameters Section ---
        params_layout = QHBoxLayout()
        
        # Date Range
        params_layout.addWidget(QLabel(_("reports_date_range")))
        self.start_date_edit = QDateEdit(calendarPopup=True)
        self.start_date_edit.setDate(QDate.currentDate().addDays(-30))
        params_layout.addWidget(self.start_date_edit)
        self.end_date_edit = QDateEdit(calendarPopup=True)
        self.end_date_edit.setDate(QDate.currentDate())
        params_layout.addWidget(self.end_date_edit)
        
        # Employee Selection
        params_layout.addWidget(QLabel(_("reports_employee_optional")))
        self.employee_combo = QComboBox()
        self.employee_combo.setMinimumWidth(200)
        params_layout.addWidget(self.employee_combo)
        params_layout.addStretch()
        layout.addLayout(params_layout)

        # --- Action Buttons ---
        button_layout = QHBoxLayout()
        self.generate_button = QPushButton(_("reports_generate_preview"))
        self.generate_button.clicked.connect(self.generate_preview)
        self.export_button = QPushButton(_("reports_export_report"))
        self.export_button.clicked.connect(self.export_report)
        self.export_button.setEnabled(False)
        button_layout.addWidget(self.generate_button)
        button_layout.addWidget(self.export_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # --- Preview Area ---
        layout.addWidget(QLabel(_("reports_preview")))
        self.preview_area = QTextEdit()
        self.preview_area.setReadOnly(True)
        self.preview_area.setFontFamily("Monospace") # Better for text tables
        layout.addWidget(self.preview_area, 1)

    def load_employee_data(self):
        """Load employees into the combo box."""
        try:
            db_session = next(get_db_session())
            employees = employee_service.get_all_employees(db=db_session)
            db_session.close()
            self.employee_combo.clear()
            self.employee_combo.addItem(_("reports_all_employees"), None)
            for emp in employees:
                display_name = f"{emp.first_name} {emp.last_name}".strip() or emp.email
                self.employee_combo.addItem(display_name, emp.id)
        except Exception as e:
            self.logger.error(f"Error loading employees for reports: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Could not load employees: {e}")

    def generate_preview(self):
        """Generate a preview of the detailed timesheet report."""
        try:
            start_date = self.start_date_edit.date().toPyDate()
            end_date = self.end_date_edit.date().toPyDate()
            emp_id = self.employee_combo.currentData()
            
            db_session = next(get_db_session())
            # Fetch the rich data from the service
            self.last_generated_data = attendance_service.get_attendance_for_export(
                employee_id=emp_id, start_date=start_date, end_date=end_date, db=db_session
            )
            db_session.close()

            if not self.last_generated_data:
                self.preview_area.setPlainText("No data found for the selected criteria.")
                self.export_button.setEnabled(False)
                return

            # Format for preview
            headers = self.last_generated_data[0].keys()
            # Define column widths for alignment
            col_widths = {
                "Employee Name": 20, "Date": 12, "Time In": 8, "Time Out": 9,
                "Tardiness (min)": 10, "Main Work (min)": 10, "Overtime (min)": 10,
                "Launch Time (min)": 10, "Total Duration (min)": 10, "Status": 10
            }
            
            header_line = " ".join([h.ljust(col_widths.get(h, 15)) for h in headers if h != 'Note'])
            lines = [header_line, "-" * len(header_line)]

            for row in self.last_generated_data:
                row_line = " ".join([
                    str(row.get(h, "")).ljust(col_widths.get(h, 15)) for h in headers if h != 'Note'
                ])
                lines.append(row_line)

            self.preview_area.setPlainText("\n".join(lines))
            self.export_button.setEnabled(True)
            self.logger.info("Detailed timesheet preview generated.")

        except Exception as e:
            self.logger.error(f"Error generating preview: {e}", exc_info=True)
            QMessageBox.critical(self, "Preview Error", f"Failed to generate preview: {e}")
            self.preview_area.setPlainText("Error generating preview.")
            self.export_button.setEnabled(False)

    def export_report(self):
        """Export the generated report data."""
        if not self.last_generated_data:
            QMessageBox.warning(self, "No Data", "Please generate a preview first.")
            return

        default_name = f"attendance_report_{date.today().strftime('%Y%m%d')}"
        file_path_str, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Report", default_name, 
            "Excel XLSX (*.xlsx);;CSV File (*.csv);;PDF Document (*.pdf)"
        )

        if not file_path_str:
            return

        export_path = Path(file_path_str)
        
        try:
            if "xlsx" in selected_filter:
                export_service.export_to_xlsx(self.last_generated_data, export_path)
            elif "csv" in selected_filter:
                export_service.export_to_csv(self.last_generated_data, export_path)
            elif "pdf" in selected_filter:
                title = f"Attendance Report ({self.start_date_edit.date().toString('yyyy-MM-dd')} to {self.end_date_edit.date().toString('yyyy-MM-dd')})"
                export_service.export_to_pdf(self.last_generated_data, export_path, title=title)
            
            QMessageBox.information(self, "Export Successful", f"Report exported to:\n{export_path}")
            self.logger.info(f"Report exported to {export_path}")

        except ExportServiceError as e:
            self.logger.error(f"Export failed (service error): {e}", exc_info=True)
            QMessageBox.critical(self, "Export Failed", f"Export failed: {e}")
        except Exception as e:
            self.logger.error(f"Export failed (unexpected error): {e}", exc_info=True)
            QMessageBox.critical(self, "Export Error", f"An unexpected error occurred: {e}")