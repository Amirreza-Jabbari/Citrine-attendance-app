# src/citrine_attendance/ui/views/attendance_view.py
"""Attendance sheet view with filtering and a dedicated edit dialog."""
import logging
from datetime import date, timedelta
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QLineEdit, QTableView, QAbstractItemView,
    QMessageBox, QApplication, QStyle, QDateEdit, QCheckBox, QFrame,
    QMenu, QInputDialog
)
from PyQt6.QtCore import Qt, QDate, QModelIndex
from PyQt6.QtGui import QKeySequence, QShortcut
from sqlalchemy.orm import Session

from ..models.attendance_model import AttendanceTableModel
from ...services.employee_service import employee_service
from ...database import get_db_session, Attendance
from ...config import config
from ..dialogs.add_attendance_dialog import AddAttendanceDialog, EditAttendanceDialog
from ..dialogs.export_dialog import ExportDialog
from ...services.export_service import export_service
from ...services.attendance_service import attendance_service
from ...services.audit_service import audit_service
from ...locale import _
from ...utils.time_utils import minutes_to_hhmm
import jdatetime


class AttendanceView(QWidget):
    """The main attendance sheet view widget."""

    def __init__(self, current_user):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.attendance_model = AttendanceTableModel(config)
        self.db_session: Optional[Session] = None

        self.init_ui()
        self.load_filter_data()
        self.load_attendance_data()
        self.setup_context_menu()
        self.setup_keyboard_shortcuts()

    def init_ui(self):
        """Initialize the attendance view UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        self.create_filter_bar()
        layout.addWidget(self.filter_bar)

        self.attendance_table = QTableView()
        self.attendance_table.setAlternatingRowColors(True)
        self.attendance_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.attendance_table.setSortingEnabled(False)
        self.attendance_table.setModel(self.attendance_model)
        # Disable inline editing; use double-click dialog instead
        self.attendance_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.attendance_table.doubleClicked.connect(self.open_edit_record_dialog)
        self.attendance_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.attendance_table)

        self.aggregation_label = QLabel(_("loading_aggregates"))
        self.aggregation_label.setStyleSheet("font-weight: bold; padding: 5px;")
        self.aggregation_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.aggregation_label)

    def create_filter_bar(self):
        """Create the filter bar widget."""
        self.filter_bar = QFrame()
        self.filter_bar.setFrameShape(QFrame.Shape.StyledPanel)
        filter_layout = QHBoxLayout(self.filter_bar)
        filter_layout.setSpacing(15)

        filter_layout.addWidget(QLabel(_("attendance_filter_employee")))
        self.employee_filter_combo = QComboBox()
        self.employee_filter_combo.setMinimumWidth(150)
        filter_layout.addWidget(self.employee_filter_combo)

        filter_layout.addWidget(QLabel(_("attendance_filter_start")))
        self.start_date_edit = QDateEdit(calendarPopup=True)
        self.start_date_edit.setDate(QDate.currentDate().addDays(-30))
        filter_layout.addWidget(self.start_date_edit)

        filter_layout.addWidget(QLabel(_("attendance_filter_end")))
        self.end_date_edit = QDateEdit(calendarPopup=True)
        self.end_date_edit.setDate(QDate.currentDate())
        filter_layout.addWidget(self.end_date_edit)

        filter_layout.addWidget(QLabel(_("attendance_filter_status")))
        self.status_present_cb = QCheckBox(_("attendance_filter_present"), checked=True)
        self.status_absent_cb = QCheckBox(_("attendance_filter_absent"), checked=True)
        self.status_on_leave_cb = QCheckBox(_("attendance_status_on_leave"), checked=True)
        filter_layout.addWidget(self.status_present_cb)
        filter_layout.addWidget(self.status_absent_cb)
        filter_layout.addWidget(self.status_on_leave_cb)

        self.search_filter_edit = QLineEdit(placeholderText=_("attendance_filter_search_placeholder"))
        filter_layout.addWidget(self.search_filter_edit)
        filter_layout.addStretch()

        self.add_record_btn = QPushButton(_("attendance_add_record"))
        self.add_record_btn.clicked.connect(self.open_add_record_dialog)
        filter_layout.addWidget(self.add_record_btn)

        self.export_btn = QPushButton(_("attendance_export"))
        self.export_btn.clicked.connect(self.open_export_dialog)
        filter_layout.addWidget(self.export_btn)

        self.refresh_button = QPushButton(_("attendance_filter_refresh"))
        self.refresh_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        filter_layout.addWidget(self.refresh_button)

        # Connect signals directly to the data loading function
        for widget in (self.employee_filter_combo, self.start_date_edit, self.end_date_edit,
                       self.status_present_cb, self.status_absent_cb, self.status_on_leave_cb,
                       self.search_filter_edit, self.refresh_button):
            if isinstance(widget, (QComboBox)):
                widget.currentIndexChanged.connect(self.load_attendance_data)
            elif isinstance(widget, (QDateEdit)):
                widget.dateChanged.connect(self.load_attendance_data)
            elif isinstance(widget, (QCheckBox)):
                widget.stateChanged.connect(self.load_attendance_data)
            elif isinstance(widget, QLineEdit):
                widget.textChanged.connect(self.load_attendance_data)
            elif isinstance(widget, QPushButton):
                widget.clicked.connect(self.load_attendance_data)

    def load_filter_data(self):
        """Load data for filter controls (e.g., employee list)."""
        try:
            session_gen = get_db_session()
            self.db_session = next(session_gen)
            current_emp_id = self.employee_filter_combo.currentData()
            employees = employee_service.get_all_employees(db=self.db_session)

            self.employee_filter_combo.blockSignals(True)
            self.employee_filter_combo.clear()
            self.employee_filter_combo.addItem(_("all_employees"), None)
            for emp in employees:
                display_name = f"{emp.first_name} {emp.last_name}".strip() or emp.email
                self.employee_filter_combo.addItem(display_name, emp.id)

            index = self.employee_filter_combo.findData(current_emp_id)
            if index != -1:
                self.employee_filter_combo.setCurrentIndex(index)
            self.employee_filter_combo.blockSignals(False)

        except Exception as e:
            self.logger.error(f"Error loading filter data: {e}", exc_info=True)
            QMessageBox.critical(self, _("dashboard_error"), _("error_loading_filter_data", error=e))
        finally:
            if self.db_session:
                self.db_session.close()

    def load_attendance_data(self):
        """Load attendance data based on current filter settings."""
        try:
            statuses = []
            if self.status_present_cb.isChecked(): statuses.append('present')
            if self.status_absent_cb.isChecked(): statuses.append('absent')
            if self.status_on_leave_cb.isChecked(): statuses.append('on_leave')

            self.attendance_model.set_filters(
                employee_id=self.employee_filter_combo.currentData(),
                start_date=self.start_date_edit.date().toPyDate(),
                end_date=self.end_date_edit.date().toPyDate(),
                statuses=statuses,
                search_text=self.search_filter_edit.text().strip()
            )
            # self.update_aggregates() # Add this back if you implement get_aggregates in the model
        except Exception as e:
            self.logger.error(f"Error loading attendance data: {e}", exc_info=True)
            QMessageBox.critical(self, _("dashboard_error"), _("error_loading_attendance_data", error=e))

    def setup_context_menu(self):
        """Setup the context menu for the table view."""
        self.attendance_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.attendance_table.customContextMenuRequested.connect(self.open_context_menu)

    def open_context_menu(self, position):
        menu = QMenu()
        index = self.attendance_table.indexAt(position)
        if not index.isValid(): return

        edit_action = menu.addAction(_("edit"))
        delete_action = menu.addAction(_("delete"))
        duplicate_action = menu.addAction(_("duplicate"))

        action = menu.exec(self.attendance_table.viewport().mapToGlobal(position))

        if action == edit_action:
            self.open_edit_record_dialog(index)
        elif action == delete_action:
            self.delete_selected_record()
        elif action == duplicate_action:
            self.duplicate_selected_record()

    def get_selected_record(self) -> Optional[Attendance]:
        """Helper to get the Attendance object from the current selection."""
        indexes = self.attendance_table.selectionModel().selectedRows()
        if not indexes:
            return None
        return self.attendance_model.get_attendance_at_row(indexes[0].row())

    def delete_selected_record(self):
        record = self.get_selected_record()
        if not record: return

        emp_name = self.attendance_model.employee_cache.get(record.employee_id, 'Unknown')
        reply = QMessageBox.question(self, _("confirm_delete_title"), _("confirm_delete_record_message", name=emp_name, date=record.date))
        if reply == QMessageBox.StandardButton.Yes:
            try:
                attendance_service.delete_attendance(record.id)
                audit_service.log_action("attendance", record.id, "delete", {}, self.current_user.username)
                self.load_attendance_data()
            except Exception as e:
                QMessageBox.critical(self, _("dashboard_error"), _("error_deleting_record", error=e))

    def duplicate_selected_record(self):
        record = self.get_selected_record()
        if not record: return

        try:
            new_record = attendance_service.add_manual_attendance(
                employee_id=record.employee_id, date=record.date + timedelta(days=1),
                time_in=record.time_in, time_out=record.time_out,
                leave_start=record.leave_start, leave_end=record.leave_end,
                note=f"Duplicated from {record.date}", created_by=self.current_user.username
            )
            audit_service.log_action("attendance", new_record.id, "create", {"duplicated_from": record.id}, self.current_user.username)
            self.load_attendance_data()
        except Exception as e:
            QMessageBox.critical(self, _("dashboard_error"), _("error_duplicating_record", error=e))

    def open_add_record_dialog(self):
        dialog = AddAttendanceDialog(self)
        dialog.record_added.connect(self.handle_record_added)
        dialog.exec()

    def handle_record_added(self):
        dialog = self.sender()
        if not dialog: return
        try:
            new_data = dialog.get_new_record_data()
            if new_data:
                self.attendance_model.add_attendance_record(new_data)
                QMessageBox.information(self, _("success"), _("record_added_success"))
                audit_service.log_action("attendance", 0, "create", {k: str(v) for k, v in new_data.items()}, self.current_user.username)
        except Exception as e:
            self.logger.error(f"Add record failed: {e}", exc_info=True)
            QMessageBox.critical(dialog, _("dashboard_error"), _("error_adding_record", error=e))

    def open_edit_record_dialog(self, index: QModelIndex):
        """Opens the edit dialog for the double-clicked or context-menu-selected record."""
        record = self.attendance_model.get_attendance_at_row(index.row())
        if record:
            dialog = EditAttendanceDialog(record, self)
            dialog.record_updated.connect(self.handle_record_updated)
            dialog.exec()

    def handle_record_updated(self, record_id: int, record_data: dict):
        """Handles the signal from the edit dialog."""
        dialog = self.sender()
        if not dialog: return
        try:
            self.attendance_model.update_attendance_record(record_id, record_data)
            QMessageBox.information(self, _("success"), _("record_updated_success"))
            audit_service.log_action("attendance", record_id, "update", {k: str(v) for k, v in record_data.items()}, self.current_user.username)
        except Exception as e:
            self.logger.error(f"Update record failed: {e}", exc_info=True)
            QMessageBox.critical(dialog, _("dashboard_error"), _("error_updating_record", error=e))

    def open_export_dialog(self):
        default_name = f"attendance_export_{date.today().strftime('%Y%m%d')}"
        export_dialog = ExportDialog(default_name, self)
        if export_dialog.exec():
            self.perform_export(export_dialog.get_export_options())

    def perform_export(self, options: dict):
        try:
            dict_data = attendance_service.get_attendance_for_export(
                employee_id=self.employee_filter_combo.currentData(),
                start_date=self.start_date_edit.date().toPyDate(),
                end_date=self.end_date_edit.date().toPyDate()
            )
            if not dict_data:
                QMessageBox.information(self, _("no_data_to_export"), _("no_data_for_filters"))
                return

            path = options['path']
            if path.exists():
                if QMessageBox.question(self, _("confirm_overwrite_title"), _("confirm_overwrite_message", file=path.name)) != QMessageBox.StandardButton.Yes:
                    return

            export_service.export_data(options['format'], dict_data, path, title=_("attendance_report_title"))
            QMessageBox.information(self, _("export_successful_title"), _("export_successful_message", path=path))
            audit_service.log_action("export", 0, "create", {"path": str(path), "format": options['format']}, self.current_user.username)

        except Exception as e:
            self.logger.error(f"Export failed: {e}", exc_info=True)
            QMessageBox.critical(self, _("export_error_title"), _("export_error_message", error=e))

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

