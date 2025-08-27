# src/citrine_attendance/ui/views/archive_view.py
"""View for browsing archived attendance records."""
import logging
from datetime import date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QLineEdit, QTableView, QHeaderView, QAbstractItemView,
    QMessageBox, QApplication, QStyle, QDateEdit, QFrame, QSplitter, QInputDialog, QDialog
)
from PyQt6.QtCore import Qt, QDate

# Import our model and related services/config
from ..models.attendance_model import AttendanceTableModel
from ...services.employee_service import employee_service
from ...services.attendance_service import attendance_service
from ...database import get_db_session, Employee
from ...config import config


class ArchiveView(QWidget):
    """The archive view widget."""

    def __init__(self, current_user):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        # Reuse the model, but it will be populated with archived data
        self.archive_model = AttendanceTableModel(config)
        self.db_session = None

        self.init_ui()
        self.load_filter_data()
        self.load_archive_data() # Load initial archived data

    def init_ui(self):
        """Initialize the archive view UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- Filter Bar ---
        self.create_filter_bar()
        layout.addWidget(self.filter_bar)

        # --- Table View for Archived Records ---
        self.archive_table = QTableView()
        self.archive_table.setAlternatingRowColors(True)
        self.archive_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.archive_table.setSortingEnabled(False) # Sorting handled by model filters
        self.archive_table.setModel(self.archive_model)

        # Configure header
        header = self.archive_table.horizontalHeader()
        header.setStretchLastSection(True)

        layout.addWidget(self.archive_table)

        # --- Action Buttons ---
        button_layout = QHBoxLayout()
        self.unarchive_button = QPushButton("Unarchive Selected")
        self.unarchive_button.clicked.connect(self.unarchive_selected)
        self.export_button = QPushButton("Export Archived")
        self.export_button.clicked.connect(self.export_archived)
        button_layout.addWidget(self.unarchive_button)
        button_layout.addWidget(self.export_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # --- Simple Info Label ---
        self.info_label = QLabel("Showing archived records. These are read-only.")
        self.info_label.setStyleSheet("font-weight: bold; padding: 5px; color: #666;")
        layout.addWidget(self.info_label)

    def create_filter_bar(self):
        """Create the filter bar widget for archived data."""
        self.filter_bar = QFrame()
        self.filter_bar.setFrameShape(QFrame.Shape.StyledPanel)
        filter_layout = QHBoxLayout(self.filter_bar)
        filter_layout.setSpacing(15)

        # Employee Filter
        filter_layout.addWidget(QLabel("Employee:"))
        self.employee_filter_combo = QComboBox()
        self.employee_filter_combo.setMinimumWidth(150)
        self.employee_filter_combo.currentIndexChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.employee_filter_combo)

        # Date Range Filter (Jalali picker note: using Gregorian QDateEdit for now)
        filter_layout.addWidget(QLabel("Date Range:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        default_start = QDate.currentDate().addDays(-365) # Default to last year
        self.start_date_edit.setDate(default_start)
        self.start_date_edit.dateChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.start_date_edit)

        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.dateChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.end_date_edit)

        # Refresh Button
        self.refresh_button = QPushButton("Refresh")
        refresh_icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        self.refresh_button.setIcon(refresh_icon)
        self.refresh_button.clicked.connect(self.load_archive_data)
        filter_layout.addWidget(self.refresh_button)

        filter_layout.addStretch()

    def load_filter_data(self):
        """Load data needed for the filter controls."""
        try:
            session_gen = get_db_session()
            self.db_session = next(session_gen)

            employees = employee_service.get_all_employees(db=self.db_session)
            self.employee_filter_combo.clear()
            self.employee_filter_combo.addItem("All Employees", None)
            for emp in employees:
                display_name = f"{emp.first_name} {emp.last_name}".strip() or emp.email
                self.employee_filter_combo.addItem(display_name, emp.id)

        except Exception as e:
            self.logger.error(f"Error loading filter data for archive: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load filter data: {e}")
        finally:
            if self.db_session:
                self.db_session.close()
                self.db_session = None

    def load_archive_data(self):
        """Load archived attendance data into the model based on current filters."""
        try:
            selected_emp_id = self.employee_filter_combo.currentData()
            start_qdate = self.start_date_edit.date()
            end_qdate = self.end_date_edit.date()

            start_date_py = start_qdate.toPyDate() if not start_qdate.isNull() else None
            end_date_py = end_qdate.toPyDate() if not end_qdate.isNull() else None

            # Use the service to get archived records
            db_session = attendance_service._get_session()
            try:
                archived_records = attendance_service.get_archived_attendance_records(
                    employee_id=selected_emp_id,
                    start_date=start_date_py,
                    end_date=end_date_py,
                    db=db_session
                )
            finally:
                db_session.close()

            # Update the model's data directly
            self.archive_model.beginResetModel()
            self.archive_model.attendance_data = archived_records
            # Repopulate employee cache
            employee_ids = {r.employee_id for r in archived_records}
            if employee_ids:
                 session_gen = get_db_session()
                 temp_session = next(session_gen)
                 try:
                     employees = temp_session.query(Employee).filter(Employee.id.in_(employee_ids)).all()
                     self.archive_model.employee_cache = {emp.id: f"{emp.first_name} {emp.last_name}".strip() for emp in employees}
                 finally:
                     temp_session.close()
            self.archive_model.endResetModel()

            self.info_label.setText(f"Showing {len(archived_records)} archived records.")

        except Exception as e:
            self.logger.error(f"Error loading archived data: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load archived data: {e}")

    def on_filter_changed(self):
        """Slot called when any filter control changes."""
        self.load_archive_data()

    # --- Archive Actions ---
    def unarchive_selected(self):
        """Unarchive the selected records."""
        selected_rows = self.archive_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select one or more records to unarchive.")
            return

        record_ids = []
        for index in selected_rows:
            row = index.row()
            record = self.archive_model.get_attendance_at_row(row)
            if record:
                record_ids.append(record.id)

        if not record_ids:
            QMessageBox.warning(self, "Error", "Could not find selected records to unarchive.")
            return

        reply = QMessageBox.question(
            self, 'Confirm Unarchive',
            f"Are you sure you want to unarchive {len(record_ids)} selected record(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                db_session = attendance_service._get_session()
                try:
                    updated_count = attendance_service.unarchive_records(record_ids, db=db_session)
                    QMessageBox.information(self, "Success", f"Successfully unarchived {updated_count} record(s).")
                    self.logger.info(f"{updated_count} records unarchived by {self.current_user.username}.")
                    # Refresh the view
                    self.load_archive_data()
                finally:
                    db_session.close()
            except Exception as e:
                self.logger.error(f"Error unarchiving records: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to unarchive records: {e}")

    def export_archived(self):
        """Export the currently filtered archived records."""
        # Check if there's data to export
        if self.archive_model.rowCount() == 0:
            QMessageBox.information(self, "No Data", "There are no archived records to export with the current filters.")
            return

        # Use ExportDialog
        from ..dialogs.export_dialog import ExportDialog
        today_str = date.today().strftime("%Y%m%d")
        default_name = f"archived_attendance_export_{today_str}"

        export_dialog = ExportDialog(default_name, self)
        if export_dialog.exec() == QDialog.DialogCode.Accepted:
            options = export_dialog.get_export_options()
            self.perform_archived_export(options)

    def perform_archived_export(self, options: dict):
        """Perform the export of archived data."""
        try:
            format_type = options['format']
            export_path = options['path']
            delimiter = options.get('delimiter', ',')

            # Prevent overwriting without confirmation
            if export_path.exists():
                reply = QMessageBox.question(
                    self, 'Confirm Overwrite',
                    f"The file {export_path.name} already exists. Do you want to overwrite it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return # User cancelled

            # Get current filter settings (re-fetch to ensure consistency)
            selected_emp_id = self.employee_filter_combo.currentData()
            start_qdate = self.start_date_edit.date()
            end_qdate = self.end_date_edit.date()
            start_date_py = start_qdate.toPyDate() if not start_qdate.isNull() else None
            end_date_py = end_qdate.toPyDate() if not end_qdate.isNull() else None

            # Fetch archived data for export using the service
            db_session = attendance_service._get_session()
            try:
                # Note: This re-fetches data, which is fine for exports to ensure consistency.
                # Alternatively, we could use the data already in self.archive_model.attendance_data
                # but we'd need to convert it to the export format.
                export_data = attendance_service.get_attendance_for_export(
                    employee_id=selected_emp_id,
                    start_date=start_date_py,
                    end_date=end_date_py,
                    db=db_session # get_attendance_for_export needs to be updated to accept an 'archived' flag or fetch from archived records
                )
                # TODO: Modify get_attendance_for_export or create a specific method to fetch archived data for export
                # For now, we'll assume get_attendance_for_export can be made to work or we filter the model data.
                # Let's filter the model data for now.
                export_data = []
                for record in self.archive_model.attendance_data:
                    # Apply filters again in Python if needed, or trust the model is already filtered
                    # For simplicity, we'll export all currently loaded archived data.
                    # A more robust solution would re-query the service with the exact filters.
                    record_dict = {
                        "Date": record.date.isoformat() if record.date else "",
                        "Employee Name": self.archive_model.employee_cache.get(record.employee_id, "Unknown"),
                        "Time In": record.time_in.strftime("%H:%M") if record.time_in else "",
                        "Time Out": record.time_out.strftime("%H:%M") if record.time_out else "",
                        "Duration (min)": record.duration_minutes if record.duration_minutes is not None else "",
                        "Status": self.archive_model.STATUS_DISPLAY.get(record.status, record.status),
                        "Note": record.note or "",
                    }
                    export_data.append(record_dict)

            finally:
                db_session.close()

            if not export_data:
                QMessageBox.information(self, "No Data", "There is no archived data matching the current filters to export.")
                return

            # Perform export based on format
            # Import export service
            from ...services.export_service import export_service, ExportServiceError
            if format_type == "csv":
                export_service.export_to_csv(export_data, export_path, delimiter=delimiter)
            elif format_type == "xlsx":
                export_service.export_to_xlsx(export_data, export_path)
            elif format_type == "pdf":
                title = f"Archived Attendance Report ({start_date_py or 'Start'} to {end_date_py or 'End'})"
                export_service.export_to_pdf(export_data, export_path, title=title)

            QMessageBox.information(
                self, "Export Successful",
                f"Archived data successfully exported to:\n{export_path}"
            )
            self.logger.info(f"Archived attendance data exported to {export_path} (Format: {format_type})")

        except ExportServiceError as e:
            self.logger.error(f"Export failed (service error): {e}", exc_info=True)
            QMessageBox.critical(self, "Export Failed", f"Export failed: {e}")
        except Exception as e:
            self.logger.error(f"Export failed (unexpected error): {e}", exc_info=True)
            QMessageBox.critical(self, "Export Error", f"An unexpected error occurred during export: {e}")

# Example usage (if run directly)
# if __name__ == '__main__':
#     from PyQt6.QtWidgets import QApplication, QMainWindow
#     import sys
#     from ...database import init_db, User
#     init_db()
#     app = QApplication(sys.argv)
#     user = User(username="admin", role="admin")
#     window = QMainWindow()
#     archive_view = ArchiveView(user)
#     window.setCentralWidget(archive_view)
#     window.show()
#     sys.exit(app.exec())