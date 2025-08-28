# src/citrine_attendance/ui/views/attendance_view.py
"""Attendance sheet view with filtering and spreadsheet-like editing."""
import logging
from datetime import date, timedelta, time, datetime
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QLineEdit, QTableView, QHeaderView, QAbstractItemView,
    QMessageBox, QApplication, QStyle, QDateEdit, QCheckBox, QFrame, QDialog,
    QMenu, QInputDialog, QFileDialog
)
from PyQt6.QtCore import Qt, QDate, QItemSelectionModel, QItemSelection, QModelIndex
from PyQt6.QtGui import QKeySequence, QShortcut, QAction, QClipboard

# Import our model and related services/config
from ..models.attendance_model import AttendanceTableModel
from ...services.employee_service import employee_service
from ...database import get_db_session, Attendance
from ...config import config

# Import dialogs and services for new features
from ..dialogs.add_attendance_dialog import AddAttendanceDialog
from ..dialogs.export_dialog import ExportDialog
from ...services.export_service import export_service, ExportServiceError
from ...services.attendance_service import attendance_service
from ...services.audit_service import audit_service # <-- Import audit service
from ...locale import _
from ...utils.time_utils import minutes_to_hhmm # <-- Import the new utility

import jdatetime

class AttendanceView(QWidget):
    """The main attendance sheet view widget."""

    def __init__(self, current_user):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.attendance_model = AttendanceTableModel(config) # Pass config for date format
        self.db_session = None # For loading employees

        self.init_ui()
        self.load_filter_data() # Populate employee dropdown etc.
        self.load_attendance_data() # Load initial data
        self.setup_context_menu()
        self.setup_keyboard_shortcuts()

    def init_ui(self):
        """Initialize the attendance view UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- Filter Bar ---
        self.create_filter_bar()
        # --- Add Record & Export Buttons to Filter Bar ---
        button_layout = QHBoxLayout()
        self.add_record_btn = QPushButton(_("attendance_add_record"))
        self.add_record_btn.setStyleSheet(self.get_button_style("#11563a")) # Brand color
        self.add_record_btn.clicked.connect(self.open_add_record_dialog)

        self.export_btn = QPushButton(_("attendance_export"))
        self.export_btn.setStyleSheet(self.get_button_style("#4caf50")) # Green
        self.export_btn.clicked.connect(self.open_export_dialog)

        button_container = QWidget()
        button_container_layout = QHBoxLayout(button_container)
        button_container_layout.setContentsMargins(0, 0, 0, 0)
        button_container_layout.addWidget(self.add_record_btn)
        button_container_layout.addWidget(self.export_btn)
        button_container_layout.addStretch()

        filter_layout = self.filter_bar.layout()
        if filter_layout:
            filter_layout.insertWidget(filter_layout.count() - 1, button_container)
        layout.addWidget(self.filter_bar)

        # --- Table View ---
        self.attendance_table = QTableView()
        self.attendance_table.setAlternatingRowColors(True)
        self.attendance_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.attendance_table.setSortingEnabled(False)
        self.attendance_table.setModel(self.attendance_model)
        self.attendance_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)

        header = self.attendance_table.horizontalHeader()
        header.setStretchLastSection(True)
        layout.addWidget(self.attendance_table)

        # --- Aggregation Row ---
        # The text will be set in update_aggregates
        self.aggregation_label = QLabel("Loading aggregates...")
        self.aggregation_label.setStyleSheet("font-weight: bold; padding: 5px;")
        self.aggregation_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.aggregation_label)

    def create_filter_bar(self):
        """Create the filter bar widget."""
        self.filter_bar = QFrame()
        self.filter_bar.setFrameShape(QFrame.Shape.StyledPanel)
        filter_layout = QHBoxLayout(self.filter_bar)
        filter_layout.setSpacing(15)

        # Employee Filter
        filter_layout.addWidget(QLabel(_("attendance_filter_employee")))
        self.employee_filter_combo = QComboBox()
        self.employee_filter_combo.setMinimumWidth(150)
        self.employee_filter_combo.currentIndexChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.employee_filter_combo)

        # Date Range Filter
        date_range_layout = QHBoxLayout()
        date_range_layout.addWidget(QLabel(_("attendance_filter_date_range")))

        start_layout = QVBoxLayout()
        start_layout.setSpacing(0)
        start_layout.addWidget(QLabel(_("attendance_filter_start")))
        self.start_date_edit = QDateEdit(calendarPopup=True)
        self.start_date_edit.setDate(QDate.currentDate().addDays(-30))
        self.start_date_edit.dateChanged.connect(self.on_filter_changed)
        self.start_jalali_label = QLabel()
        self.start_jalali_label.setStyleSheet("font-size: 11px; color: gray;")
        start_layout.addWidget(self.start_date_edit)
        start_layout.addWidget(self.start_jalali_label)
        date_range_layout.addLayout(start_layout)

        end_layout = QVBoxLayout()
        end_layout.setSpacing(0)
        end_layout.addWidget(QLabel(_("attendance_filter_end")))
        self.end_date_edit = QDateEdit(calendarPopup=True)
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.dateChanged.connect(self.on_filter_changed)
        self.end_jalali_label = QLabel()
        self.end_jalali_label.setStyleSheet("font-size: 11px; color: gray;")
        end_layout.addWidget(self.end_date_edit)
        end_layout.addWidget(self.end_jalali_label)
        date_range_layout.addLayout(end_layout)
        filter_layout.addLayout(date_range_layout)

        # Status Filter
        filter_layout.addWidget(QLabel(_("attendance_filter_status")))
        self.status_present_cb = QCheckBox(_("attendance_filter_present"))
        self.status_present_cb.setChecked(True)
        self.status_present_cb.stateChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.status_present_cb)
        self.status_absent_cb = QCheckBox(_("attendance_filter_absent"))
        self.status_absent_cb.setChecked(True)
        self.status_absent_cb.stateChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.status_absent_cb)

        # Search Filter
        filter_layout.addWidget(QLabel(_("attendance_filter_search")))
        self.search_filter_edit = QLineEdit()
        self.search_filter_edit.setPlaceholderText(_("attendance_filter_search_placeholder"))
        self.search_filter_edit.textChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.search_filter_edit)

        # Refresh Button
        self.refresh_button = QPushButton(_("attendance_filter_refresh"))
        self.refresh_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.refresh_button.clicked.connect(self.load_attendance_data)
        filter_layout.addWidget(self.refresh_button)
        filter_layout.addStretch()

        self.start_date_edit.dateChanged.connect(self.on_date_range_changed)
        self.end_date_edit.dateChanged.connect(self.on_date_range_changed)
        self.on_date_range_changed()

    def load_filter_data(self):
        """Load data for filter controls."""
        try:
            session_gen = get_db_session()
            self.db_session = next(session_gen)
            current_emp_id = self.employee_filter_combo.currentData()
            employees = employee_service.get_all_employees(db=self.db_session)
            self.employee_filter_combo.clear()
            self.employee_filter_combo.addItem("All Employees", None)
            for emp in employees:
                display_name = f"{emp.first_name} {emp.last_name}".strip() or emp.email
                self.employee_filter_combo.addItem(display_name, emp.id)
            index = self.employee_filter_combo.findData(current_emp_id)
            if index != -1:
                self.employee_filter_combo.setCurrentIndex(index)
            self.logger.debug("Employee filter data reloaded.")
        except Exception as e:
            self.logger.error(f"Error loading filter data: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load filter data: {e}")
        finally:
            if self.db_session:
                self.db_session.close()
                self.db_session = None

    def load_attendance_data(self):
        """Load attendance data based on filters."""
        try:
            statuses = []
            if self.status_present_cb.isChecked():
                statuses.append('present')
            if self.status_absent_cb.isChecked():
                statuses.append('absent')

            self.attendance_model.set_filters(
                employee_id=self.employee_filter_combo.currentData(),
                start_date=self.start_date_edit.date().toPyDate(),
                end_date=self.end_date_edit.date().toPyDate(),
                statuses=statuses,
                search_text=self.search_filter_edit.text().strip()
            )
            self.logger.debug("Attendance data loaded/refreshed.")
            self.update_aggregates()
        except Exception as e:
            self.logger.error(f"Error loading attendance data: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load attendance data: {e}")

    def on_filter_changed(self, *args, **kwargs):
        self.load_attendance_data()

    def update_aggregates(self):
        """Calculate and display aggregate values in HH:MM format."""
        try:
            aggregates = self.attendance_model.get_aggregates()
            # --- THIS IS THE CORRECTED PART, USING HH:MM FORMATTING ---
            agg_text = (
                f"Total Duration: {minutes_to_hhmm(aggregates.get('total_duration'))} | "
                f"Main Work: {minutes_to_hhmm(aggregates.get('total_main_work'))} | "
                f"Overtime: {minutes_to_hhmm(aggregates.get('total_overtime'))} | "
                f"Tardiness: {minutes_to_hhmm(aggregates.get('total_tardiness'))} | "
                f"Present: {aggregates.get('present_days', 0)} days | "
                f"Absent: {aggregates.get('absent_days', 0)} days"
            )
            self.aggregation_label.setText(agg_text)
        except Exception as e:
            self.logger.error(f"Error calculating aggregates: {e}", exc_info=True)
            self.aggregation_label.setText("Aggregates: Error calculating")

    def setup_context_menu(self):
        """Setup the context menu for the table view."""
        self.attendance_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.attendance_table.customContextMenuRequested.connect(self.open_context_menu)

    def open_context_menu(self, position):
        menu = QMenu()
        index = self.attendance_table.indexAt(position)
        if not index.isValid():
            return

        mark_absent_action = menu.addAction(_("attendance_context_mark_absent"))
        add_note_action = menu.addAction(_("attendance_context_add_edit_note"))
        delete_row_action = menu.addAction(_("attendance_context_delete_record"))
        duplicate_row_action = menu.addAction(_("attendance_context_duplicate_record"))

        action = menu.exec(self.attendance_table.viewport().mapToGlobal(position))

        if action == mark_absent_action:
            self.mark_selected_absent()
        elif action == add_note_action:
            self.add_note_to_selected()
        elif action == delete_row_action:
            self.delete_selected_record()
        elif action == duplicate_row_action:
            self.duplicate_selected_record()

    def get_selected_record(self):
        """Helper to get the Attendance object from the current selection."""
        # Prefer selected rows, but fall back to the current cell's row
        indexes = self.attendance_table.selectionModel().selectedRows()
        if not indexes:
            index = self.attendance_table.currentIndex()
            if not index.isValid():
                return None
            return self.attendance_model.get_attendance_at_row(index.row())
        return self.attendance_model.get_attendance_at_row(indexes[0].row())

    def mark_selected_absent(self):
        record = self.get_selected_record()
        if not record: return
        
        try:
            attendance_service.update_attendance(attendance_id=record.id, time_in=None, time_out=None)
            audit_service.log_action("attendance", record.id, "update", {"status": "absent"}, self.current_user.username)
            self.load_attendance_data()
        except Exception as e:
            self.logger.error(f"Error marking absent: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to mark as absent: {e}")

    def add_note_to_selected(self):
        record = self.get_selected_record()
        if not record: return
        
        note, ok = QInputDialog.getMultiLineText(self, "Edit Note", "Note:", record.note or "")
        if ok:
            try:
                attendance_service.update_attendance(attendance_id=record.id, note=note)
                audit_service.log_action("attendance", record.id, "update", {"note": note}, self.current_user.username)
                self.load_attendance_data()
            except Exception as e:
                self.logger.error(f"Error updating note: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to update note: {e}")
    
    def delete_selected_record(self):
        record = self.get_selected_record()
        if not record: return

        emp_name = self.attendance_model.employee_cache.get(record.employee_id, 'Unknown')
        reply = QMessageBox.question(self, 'Confirm Delete', f"Delete record for {emp_name} on {record.date}?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                attendance_service.delete_attendance(record.id)
                audit_service.log_action("attendance", record.id, "delete", {}, self.current_user.username)
                self.load_attendance_data()
            except Exception as e:
                self.logger.error(f"Error deleting record: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to delete record: {e}")
    
    def duplicate_selected_record(self):
        record = self.get_selected_record()
        if not record: return

        try:
            new_record = attendance_service.add_manual_attendance(
                employee_id=record.employee_id, date=record.date + timedelta(days=1),
                time_in=record.time_in, time_out=record.time_out,
                launch_start=record.launch_start_time, launch_end=record.launch_end_time,
                note=f"Duplicated from {record.date}", created_by=self.current_user.username
            )
            audit_service.log_action("attendance", new_record.id, "create", {"duplicated_from": record.id}, self.current_user.username)
            self.load_attendance_data()
        except Exception as e:
            self.logger.error(f"Error duplicating record: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to duplicate record: {e}")

    def setup_keyboard_shortcuts(self):
        QShortcut(QKeySequence.StandardKey.Copy, self.attendance_table, self.copy_selection)

    def copy_selection(self):
        selection = self.attendance_table.selectionModel().selectedIndexes()
        if not selection: return
        
        rows = sorted(list(set(index.row() for index in selection)))
        cols = sorted(list(set(index.column() for index in selection)))
        
        table_data = [['' for _ in cols] for _ in rows]
        for index in selection:
            row_idx = rows.index(index.row())
            col_idx = cols.index(index.column())
            table_data[row_idx][col_idx] = index.data()

        text = "\n".join(["\t".join(map(str, row)) for row in table_data])
        QApplication.clipboard().setText(text)
        
    def open_add_record_dialog(self):
        self.add_dialog = AddAttendanceDialog(self)
        self.add_dialog.record_added.connect(self.handle_record_added)
        self.add_dialog.exec()

    def handle_record_added(self, record_data):
        try:
            self.attendance_model.add_attendance_record(record_data)
            self.add_dialog.accept()
            QMessageBox.information(self, "Success", "Record added successfully.")
            audit_service.log_action("attendance", 0, "create", {k: str(v) for k, v in record_data.items()}, self.current_user.username)
        except Exception as e:
            self.logger.error(f"Add record failed: {e}", exc_info=True)
            QMessageBox.critical(self.add_dialog, "Error", f"Failed to add record: {e}")

    def open_export_dialog(self):
        default_name = f"attendance_export_{date.today().strftime('%Y%m%d')}"
        export_dialog = ExportDialog(default_name, self)
        if export_dialog.exec() == QDialog.DialogCode.Accepted:
            self.perform_export(export_dialog.get_export_options())

    def perform_export(self, options: dict):
        try:
            dict_data_to_export = attendance_service.get_attendance_for_export(
                employee_id=self.employee_filter_combo.currentData(),
                start_date=self.start_date_edit.date().toPyDate(),
                end_date=self.end_date_edit.date().toPyDate()
            )
            if not dict_data_to_export:
                QMessageBox.information(self, "No Data", "No data to export for the selected filters.")
                return

            export_path = options['path']
            if export_path.exists():
                if QMessageBox.question(self, 'Confirm Overwrite', f"{export_path.name} exists. Overwrite?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.No:
                    return

            format_type = options['format']
            if format_type == "csv":
                export_service.export_to_csv(dict_data_to_export, export_path)
            elif format_type == "xlsx":
                export_service.export_to_xlsx(dict_data_to_export, export_path)
            elif format_type == "pdf":
                export_service.export_to_pdf(dict_data_to_export, export_path, title="Attendance Report")

            QMessageBox.information(self, "Export Successful", f"Data exported to:\n{export_path}")
            audit_service.log_action("export", 0, "create", {"path": str(export_path), "format": format_type}, self.current_user.username)
        except Exception as e:
            self.logger.error(f"Export failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Export Error", f"An error occurred during export: {e}")
    
    def on_date_range_changed(self):
        """Update Jalali date labels."""
        digit_map = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
        
        def format_jalali(qdate):
            if qdate.isNull(): return ""
            try:
                py_date = qdate.toPyDate()
                jalali_date = jdatetime.date.fromgregorian(date=py_date)
                day = str(jalali_date.day).translate(digit_map)
                month = jalali_date.j_months[jalali_date.month - 1]
                year = str(jalali_date.year).translate(digit_map)
                return f"{day} {month} {year}"
            except Exception:
                return ""

        self.start_jalali_label.setText(format_jalali(self.start_date_edit.date()))
        self.end_jalali_label.setText(format_jalali(self.end_date_edit.date()))

    def get_button_style(self, bg_color):
        hover_color = self.darken_color(bg_color)
        return f"""QPushButton {{ background-color: {bg_color}; color: white; border: none; padding: 8px 16px; border-radius: 5px; font-size: 14px; }}
                   QPushButton:hover {{ background-color: {hover_color}; }}"""

    def darken_color(self, color_hex):
        color_hex = color_hex.lstrip('#')
        rgb = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))
        darker_rgb = tuple(max(0, int(c * 0.9)) for c in rgb)
        return f"#{darker_rgb[0]:02x}{darker_rgb[1]:02x}{darker_rgb[2]:02x}"