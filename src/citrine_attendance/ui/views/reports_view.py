# src/citrine_attendance/ui/views/reports_view.py
import logging
from datetime import date, time
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QMessageBox, QDateEdit, QFileDialog, QTableView, QHeaderView
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QStandardItemModel, QStandardItem

from ...services.attendance_service import attendance_service
from ...services.employee_service import employee_service
from ...services.export_service import export_service, ExportServiceError
from ...database import get_db_session
from ...locale import _, translator


class ReportsView(QWidget):
    """The reports generation view widget."""

    def __init__(self, current_user):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.last_generated_data = []  # Cache the data for export

        # Define the order and mapping of report columns
        self.column_map = {
            "Employee Name": "report_header_employee_name",
            "Date": "report_header_date",
            "Time In": "report_header_time_in",
            "Time Out": "report_header_time_out",
            "Status": "report_header_status",
            "Tardiness (min)": "report_header_tardiness",
            "Main Work (min)": "report_header_main_work",
            "Overtime (min)": "report_header_overtime",
            "Launch Time (min)": "report_header_launch_time",
            "Total Duration (min)": "report_header_total_duration",
            "Note": "report_header_note",
        }

        self.init_ui()
        self.load_employee_data()
        self.update_ui_language()

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

        # --- Preview Area (Using QTableView) ---
        layout.addWidget(QLabel(_("reports_preview")))
        self.preview_table = QTableView()
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.preview_model = QStandardItemModel()
        self.preview_table.setModel(self.preview_model)
        layout.addWidget(self.preview_table, 1)

    def update_ui_language(self):
        """Update UI element text based on the current language."""
        self.start_date_edit.parent().findChild(QLabel).setText(_("reports_date_range"))
        self.employee_combo.parent().findChild(QLabel).setText(_("reports_employee_optional"))
        # Update combo box item for "All Employees"
        if self.employee_combo.count() > 0:
            self.employee_combo.setItemText(0, _("reports_all_employees"))
        self.generate_button.setText(_("reports_generate_preview"))
        self.export_button.setText(_("reports_export_report"))
        self.preview_table.parent().findChild(QLabel).setText(_("reports_preview"))

        # Right-to-Left layout for Persian
        if translator.language == 'fa':
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.preview_table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.preview_table.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        # Regenerate headers if data exists
        if self.preview_model.columnCount() > 0:
            self.populate_preview_table()


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
        """Generate a preview of the detailed timesheet report and populate the table."""
        try:
            start_date = self.start_date_edit.date().toPyDate()
            end_date = self.end_date_edit.date().toPyDate()
            emp_id = self.employee_combo.currentData()

            db_session = next(get_db_session())
            self.last_generated_data = attendance_service.get_attendance_for_export(
                employee_id=emp_id, start_date=start_date, end_date=end_date, db=db_session
            )
            db_session.close()

            self.populate_preview_table()

            if not self.last_generated_data:
                QMessageBox.information(self, _("reports_preview"), _("reports_no_data"))
                self.export_button.setEnabled(False)
            else:
                self.export_button.setEnabled(True)
                self.logger.info("Detailed timesheet preview generated.")

        except Exception as e:
            self.logger.error(f"Error generating preview: {e}", exc_info=True)
            QMessageBox.critical(self, _("reports_preview_error_title"), _("reports_preview_error_message", e=e))
            self.preview_model.clear()
            self.export_button.setEnabled(False)

    def _format_cell_value(self, value):
        """Correctly formats a value for display, especially time objects."""
        if isinstance(value, time):
            return value.strftime('%H:%M')
        if value is None:
            return ""
        return str(value)

    def populate_preview_table(self):
        """Fills the QTableView with the cached report data."""
        self.preview_model.clear()

        if not self.last_generated_data:
            return

        headers = [_(self.column_map.get(key, key)) for key in self.column_map.keys()]
        self.preview_model.setHorizontalHeaderLabels(headers)

        for row_data in self.last_generated_data:
            row_items = []
            for original_key in self.column_map.keys():
                value = row_data.get(original_key)
                
                # Translate status values before formatting
                if original_key == "Status" and value in ["present", "absent"]:
                    display_value = _(value)
                else:
                    # Format everything else for display
                    display_value = self._format_cell_value(value)
                
                item = QStandardItem(display_value)
                row_items.append(item)
            self.preview_model.appendRow(row_items)

        self.preview_table.resizeColumnsToContents()
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.preview_table.horizontalHeader().setStretchLastSection(True)


    def export_report(self):
        """Export the generated report data."""
        if not self.last_generated_data:
            QMessageBox.warning(self, _("reports_no_data_to_export_title"), _("reports_no_data_to_export_message"))
            return

        default_name = f"attendance_report_{date.today().strftime('%Y%m%d')}"
        file_path_str, selected_filter = QFileDialog.getSaveFileName(
            self, _("reports_export_report"), default_name,
            "Excel XLSX (*.xlsx);;CSV File (*.csv);;PDF Document (*.pdf)"
        )

        if not file_path_str:
            return

        export_path = Path(file_path_str)

        try:
            # HEROIC FIX: Prepare data for export.
            # We translate headers and specific text values (like status),
            # but critically, we pass numeric values (like minutes) as raw numbers.
            export_ready_data = []
            for row in self.last_generated_data:
                processed_row = {}
                for original_key, translation_key in self.column_map.items():
                    translated_header = _(translation_key)
                    value = row.get(original_key)

                    # Logic to determine the final value for the export file
                    if original_key == "Status" and value in ["present", "absent"]:
                        # Translate status text
                        final_value = _(value)
                    elif isinstance(value, time):
                        # Format time objects to strings
                        final_value = value.strftime('%H:%M')
                    else:
                        # Keep numbers as numbers (int, float) and other values as they are
                        final_value = value
                    
                    processed_row[translated_header] = final_value
                export_ready_data.append(processed_row)

            if "xlsx" in selected_filter:
                export_service.export_to_xlsx(export_ready_data, export_path)
            elif "csv" in selected_filter:
                export_service.export_to_csv(export_ready_data, export_path)
            elif "pdf" in selected_filter:
                title = _("reports_monthly_timesheet") + f" ({self.start_date_edit.date().toString('yyyy-MM-dd')} to {self.end_date_edit.date().toString('yyyy-MM-dd')})"
                # PDF export often expects string data, so we can format everything here
                pdf_data = []
                for row in export_ready_data:
                    pdf_data.append({k: str(v) if v is not None else "" for k, v in row.items()})
                export_service.export_to_pdf(pdf_data, export_path, title=title)

            QMessageBox.information(self, _("reports_export_success_title"), _("reports_export_success_message", export_path=export_path))
            self.logger.info(f"Report exported to {export_path}")

        except ExportServiceError as e:
            self.logger.error(f"Export failed (service error): {e}", exc_info=True)
            QMessageBox.critical(self, _("reports_export_failed_title"), _("reports_export_failed_message", e=e))
        except Exception as e:
            self.logger.error(f"Export failed (unexpected error): {e}", exc_info=True)
            QMessageBox.critical(self, _("reports_export_error_title"), _("reports_export_error_message", e=e))