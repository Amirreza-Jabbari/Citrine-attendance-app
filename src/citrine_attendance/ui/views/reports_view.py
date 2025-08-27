# src/citrine_attendance/ui/views/reports_view.py
"""View for selecting and generating reports."""
import logging
from datetime import date, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTextEdit, QMessageBox, QDateEdit, QApplication, QStyle, QFrame, QSplitter, QDialog
)
from PyQt6.QtCore import Qt, QDate, QBuffer, QByteArray
# For preview, we might use a QTableView or QTextEdit
# For PDF, we'll use export_service or reportlab directly

from ...services.attendance_service import attendance_service
from ...services.employee_service import employee_service
from ...services.export_service import export_service, ExportServiceError
from ...database import get_db_session


class ReportsView(QWidget):
    """The reports generation view widget."""

    def __init__(self, current_user):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.db_session = None

        self.init_ui()
        self.load_report_options()

    def init_ui(self):
        """Initialize the reports view UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)

        # --- Report Selection ---
        selection_layout = QHBoxLayout()
        selection_layout.addWidget(QLabel("Report Type:"))
        self.report_type_combo = QComboBox()
        # Add predefined report types
        self.report_type_combo.addItem("--- Select a Report ---", None)
        self.report_type_combo.addItem("Daily Summary", "daily_summary")
        self.report_type_combo.addItem("Monthly Employee Timesheet", "monthly_timesheet")
        self.report_type_combo.addItem("Payroll Export (CSV)", "payroll_csv")
        # Add more as needed
        selection_layout.addWidget(self.report_type_combo)
        selection_layout.addStretch()
        layout.addLayout(selection_layout)

        # --- Parameters Section ---
        self.params_frame = QFrame()
        self.params_frame.setFrameShape(QFrame.Shape.StyledPanel)
        params_layout = QVBoxLayout(self.params_frame)

        # Date Range (common for many reports)
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("Date Range:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate.currentDate().addDays(-30)) # Default 30 days
        date_layout.addWidget(self.start_date_edit)

        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate())
        date_layout.addWidget(self.end_date_edit)
        date_layout.addStretch()
        params_layout.addLayout(date_layout)

        # Employee Selection (for employee-specific reports)
        emp_layout = QHBoxLayout()
        emp_layout.addWidget(QLabel("Employee (Optional):"))
        self.employee_combo = QComboBox()
        self.employee_combo.addItem("All Employees", None)
        emp_layout.addWidget(self.employee_combo)
        emp_layout.addStretch()
        params_layout.addLayout(emp_layout)

        # Initially hide parameters until a report is selected
        self.params_frame.setVisible(False)
        layout.addWidget(self.params_frame)

        # Connect report type change to show/hide params
        self.report_type_combo.currentIndexChanged.connect(self.on_report_type_changed)

        # --- Action Buttons ---
        button_layout = QHBoxLayout()
        self.generate_button = QPushButton("Generate Preview")
        self.generate_button.clicked.connect(self.generate_preview)
        self.export_button = QPushButton("Export Report")
        self.export_button.clicked.connect(self.export_report)
        self.export_button.setEnabled(False) # Enable after preview
        button_layout.addWidget(self.generate_button)
        button_layout.addWidget(self.export_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # --- Preview Area ---
        layout.addWidget(QLabel("Preview:"))
        self.preview_area = QTextEdit() # Or QTableView for tabular data
        self.preview_area.setReadOnly(True)
        layout.addWidget(self.preview_area, 1) # Stretch to fill space

        # Load employee data for the combo box
        self.load_employee_data()

    def load_employee_data(self):
        """Load employees into the combo box."""
        try:
            session_gen = get_db_session()
            self.db_session = next(session_gen)
            employees = employee_service.get_all_employees(db=self.db_session)
            self.employee_combo.clear()
            self.employee_combo.addItem("All Employees", None)
            for emp in employees:
                display_name = f"{emp.first_name} {emp.last_name}".strip() or emp.email
                self.employee_combo.addItem(display_name, emp.id)
        except Exception as e:
            self.logger.error(f"Error loading employees for reports: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Could not load employees: {e}")
        finally:
            if self.db_session:
                self.db_session.close()
                self.db_session = None

    def load_report_options(self):
        """Load available report types and options."""
        # This is mostly handled by the combo box initialization in init_ui
        pass

    def on_report_type_changed(self, index):
        """Show/hide parameter fields based on selected report."""
        selected_type = self.report_type_combo.currentData()
        if selected_type:
            self.params_frame.setVisible(True)
            # Could further customize which params are visible based on report type
            # e.g., hide employee combo for 'Daily Summary'
        else:
            self.params_frame.setVisible(False)
            self.preview_area.clear()
            self.export_button.setEnabled(False)

    def generate_preview(self):
        """Generate a preview of the selected report."""
        report_type = self.report_type_combo.currentData()
        if not report_type:
            QMessageBox.warning(self, "No Report", "Please select a report type first.")
            return

        try:
            start_date = self.start_date_edit.date().toPyDate()
            end_date = self.end_date_edit.date().toPyDate()
            emp_id = self.employee_combo.currentData()

            # --- Call service/report logic based on type ---
            preview_text = ""
            if report_type == "daily_summary":
                preview_text = self._generate_daily_summary_preview(start_date, end_date)
            elif report_type == "monthly_timesheet":
                preview_text = self._generate_monthly_timesheet_preview(start_date, end_date, emp_id)
            elif report_type == "payroll_csv":
                preview_text = self._generate_payroll_preview(start_date, end_date, emp_id)
            else:
                preview_text = f"Preview generation for '{report_type}' is not yet implemented."

            self.preview_area.setPlainText(preview_text)
            self.export_button.setEnabled(True)
            self.logger.info(f"Preview generated for report type: {report_type}")

        except Exception as e:
            self.logger.error(f"Error generating preview for {report_type}: {e}", exc_info=True)
            QMessageBox.critical(self, "Preview Error", f"Failed to generate preview: {e}")
            self.preview_area.setPlainText("Error generating preview.")
            self.export_button.setEnabled(False)

    def _generate_daily_summary_preview(self, start_date, end_date):
        """Generate preview text for daily summary."""
        # Use attendance_service.get_daily_summary for each date in range
        # Or aggregate differently. This is a simple text example.
        lines = [f"Daily Summary Report ({start_date} to {end_date})\n"]
        lines.append("-" * 40)
        current_date = start_date
        while current_date <= end_date:
            summary = attendance_service.get_daily_summary(current_date)
            lines.append(
                f"{current_date}:\n"
                f"  Present: {summary['present']}\n"
                f"  Late: {summary['late']}\n"
                f"  Absent: {summary['absent']}\n"
                f"  Half Day: {summary['halfday']}\n"
            )
            current_date += timedelta(days=1)
        return "\n".join(lines)

    def _generate_monthly_timesheet_preview(self, start_date, end_date, emp_id):
        """Generate preview text for monthly timesheet."""
        # Fetch records for employee/date range
        # Aggregate by employee and date
        lines = [f"Monthly Timesheet Report ({start_date} to {end_date})\n"]
        if emp_id:
            emp = employee_service.get_employee_by_id(emp_id)
            lines.append(f"Employee: {emp.first_name} {emp.last_name}\n")
        else:
            lines.append("Employee: All\n")
        lines.append("-" * 40)
        # This is a simplified example, would need actual data fetching and aggregation
        lines.append("Detailed timesheet data would be shown here in a table format in the full implementation.")
        return "\n".join(lines)

    def _generate_payroll_preview(self, start_date, end_date, emp_id):
        """Generate preview text for payroll export."""
        lines = [f"Payroll Export Preview ({start_date} to {end_date})\n"]
        if emp_id:
            emp = employee_service.get_employee_by_id(emp_id)
            lines.append(f"Employee: {emp.first_name} {emp.last_name}\n")
        else:
            lines.append("Employee: All\n")
        lines.append("-" * 40)
        lines.append("This report will export a CSV suitable for payroll systems.")
        lines.append("Columns typically include: Employee Name, Date, Hours Worked, Status, Notes.")
        return "\n".join(lines)

    def export_report(self):
        """Export the generated report."""
        report_type = self.report_type_combo.currentData()
        if not report_type:
            QMessageBox.warning(self, "No Report", "Please select a report type and generate a preview first.")
            return

        # Determine export format based on report type
        export_format = "pdf" # Default
        if report_type == "payroll_csv":
            export_format = "csv"

        # Use ExportDialog or direct save
        from ..dialogs.export_dialog import ExportDialog
        default_name = f"report_{report_type}_{date.today().strftime('%Y%m%d')}"
        export_dialog = ExportDialog(default_name, self)
        # Pre-select format based on report type logic
        if export_format == "csv":
            export_dialog.format_combo.setCurrentText("CSV (.csv)")
        elif export_format == "pdf":
            export_dialog.format_combo.setCurrentText("PDF (.pdf)")
        # Force the correct format for specific reports?
        # export_dialog.format_combo.setEnabled(False) # Disable changing format?

        if export_dialog.exec() == QDialog.DialogCode.Accepted:
            options = export_dialog.get_export_options()
            selected_format = options['format']
            export_path = options['path']
            delimiter = options.get('delimiter', ',')

            # Prevent overwriting
            if export_path.exists():
                reply = QMessageBox.question(
                    self, 'Confirm Overwrite',
                    f"The file {export_path.name} already exists. Do you want to overwrite it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return

            try:
                # Get data again for export (or use cached preview data if suitable)
                start_date = self.start_date_edit.date().toPyDate()
                end_date = self.end_date_edit.date().toPyDate()
                emp_id = self.employee_combo.currentData()

                # --- Generate export data ---
                export_data = []
                if report_type == "daily_summary":
                    # Aggregate data for export
                    current_date = start_date
                    while current_date <= end_date:
                        summary = attendance_service.get_daily_summary(current_date)
                        export_data.append({
                            "Date": current_date.isoformat(),
                            "Present": summary['present'],
                            "Late": summary['late'],
                            "Absent": summary['absent'],
                            "Half Day": summary['halfday']
                        })
                        current_date += timedelta(days=1)
                    # Export
                    if selected_format == "csv":
                        export_service.export_to_csv(export_data, export_path, delimiter=delimiter)
                    elif selected_format == "xlsx":
                        export_service.export_to_xlsx(export_data, export_path)
                    elif selected_format == "pdf":
                        export_service.export_to_pdf(export_data, export_path, title="Daily Summary Report")

                elif report_type == "payroll_csv":
                    # Fetch detailed data for payroll
                    db_session = attendance_service._get_session()
                    try:
                         # Use get_attendance_for_export or similar logic tailored for payroll
                         payroll_data = attendance_service.get_attendance_for_export(
                             employee_id=emp_id, start_date=start_date, end_date=end_date, db=db_session
                         )
                         # Simplify/payroll-specific columns if needed
                    finally:
                        db_session.close()

                    if selected_format == "csv":
                        export_service.export_to_csv(payroll_data, export_path, delimiter=delimiter)
                    # Payroll is typically CSV, warn if trying other formats?
                    elif selected_format in ["xlsx", "pdf"]:
                         QMessageBox.information(self, "Info", "Payroll export is typically CSV. Exporting as requested.")
                         if selected_format == "xlsx":
                             export_service.export_to_xlsx(payroll_data, export_path)
                         elif selected_format == "pdf":
                             export_service.export_to_pdf(payroll_data, export_path, title="Payroll Export")

                # Add other report types similarly...

                QMessageBox.information(self, "Export Successful", f"Report exported to:\n{export_path}")
                self.logger.info(f"Report '{report_type}' exported to {export_path} (Format: {selected_format})")

            except ExportServiceError as e:
                self.logger.error(f"Export failed (service error): {e}", exc_info=True)
                QMessageBox.critical(self, "Export Failed", f"Export failed: {e}")
            except Exception as e:
                self.logger.error(f"Export failed (unexpected error): {e}", exc_info=True)
                QMessageBox.critical(self, "Export Error", f"An unexpected error occurred during export: {e}")

    # --- Placeholder methods ---
    # def on_export_clicked(self): pass

# Example usage (if run directly)
# if __name__ == '__main__':
#     from PyQt6.QtWidgets import QApplication, QMainWindow
#     import sys
#     from ...database import init_db, User
#     init_db()
#     app = QApplication(sys.argv)
#     user = User(username="testuser", role="admin") # or operator
#     window = QMainWindow()
#     reports_view = ReportsView(user)
#     window.setCentralWidget(reports_view)
#     window.show()
#     sys.exit(app.exec())