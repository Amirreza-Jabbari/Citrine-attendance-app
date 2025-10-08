# src/citrine_attendance/ui/views/attendance_view.py
"""Attendance sheet view with filtering and a dedicated edit dialog."""
import logging
from datetime import date, timedelta
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QLineEdit, QTableView, QAbstractItemView,
    QMessageBox, QApplication, QStyle, QCheckBox, QFrame,
    QMenu
)
from PyQt6.QtCore import Qt, QDate, QModelIndex
from PyQt6.QtGui import QKeySequence, QShortcut
from ..widgets.jalali_date_edit import JalaliDateEdit
from sqlalchemy.orm import Session

from ..models.attendance_model import AttendanceTableModel
from ...services.employee_service import employee_service
from ...database import get_db_session, Attendance
from ...config import config
from ..dialogs.add_attendance_dialog import AddAttendanceDialog, EditAttendanceDialog
from ..dialogs.export_dialog import ExportDialog
from ...services.export_service import export_service
from ...services.attendance_service import attendance_service, LeaveBalanceExceededError
from ...services.audit_service import audit_service
from ...locale import _
from ...utils.time_utils import minutes_to_hhmm
from ...date_utils import get_jalali_month_names, jalali_to_gregorian
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
        self.populate_month_filter()
        self.load_filter_data()
        self.load_attendance_data()
        self.setup_context_menu()
        self.setup_keyboard_shortcuts()
        self.attendance_model.modelReset.connect(self.update_aggregation_label)


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
        self.attendance_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.attendance_table.doubleClicked.connect(self.open_edit_or_add_dialog)
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

        # --- Create widgets ---
        self.employee_filter_combo = QComboBox()
        self.employee_filter_combo.setMinimumWidth(150)

        self.month_filter_combo = QComboBox()
        self.month_filter_combo.setMinimumWidth(120)

        self.start_date_edit = JalaliDateEdit()
        self.end_date_edit = JalaliDateEdit()

        self.status_present_cb = QCheckBox(_("attendance_filter_present"), checked=True)
        self.status_absent_cb = QCheckBox(_("attendance_filter_absent"), checked=True)
        self.status_on_leave_cb = QCheckBox(_("attendance_status_on_leave"), checked=True)
        # BUG FIX: Add a checkbox for "Partial" status and check it by default.
        # This ensures records without a time_out remain visible after editing.
        self.status_partial_cb = QCheckBox(_("attendance_filter_partial"), checked=True)

        self.search_filter_edit = QLineEdit(placeholderText=_("attendance_filter_search_placeholder"))
        self.add_record_btn = QPushButton(_("attendance_add_record"))
        self.export_btn = QPushButton(_("attendance_export"))
        self.refresh_button = QPushButton(_("attendance_filter_refresh"))
        self.refresh_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))

        # --- Add widgets to layout ---
        filter_layout.addWidget(QLabel(_("attendance_filter_employee")))
        filter_layout.addWidget(self.employee_filter_combo)
        filter_layout.addWidget(QLabel(_("attendance_filter_month")))
        filter_layout.addWidget(self.month_filter_combo)
        filter_layout.addWidget(QLabel(_("attendance_filter_start")))
        filter_layout.addWidget(self.start_date_edit)
        filter_layout.addWidget(QLabel(_("attendance_filter_end")))
        filter_layout.addWidget(self.end_date_edit)
        filter_layout.addWidget(QLabel(_("attendance_filter_status")))
        filter_layout.addWidget(self.status_present_cb)
        filter_layout.addWidget(self.status_absent_cb)
        filter_layout.addWidget(self.status_on_leave_cb)
        # BUG FIX: Add the new "Partial" checkbox to the layout.
        filter_layout.addWidget(self.status_partial_cb)
        filter_layout.addWidget(self.search_filter_edit)
        filter_layout.addStretch()
        filter_layout.addWidget(self.add_record_btn)
        filter_layout.addWidget(self.export_btn)
        filter_layout.addWidget(self.refresh_button)

        # --- Connect signals ---
        self.employee_filter_combo.currentIndexChanged.connect(self.load_attendance_data)
        self.month_filter_combo.currentIndexChanged.connect(self.on_month_selected)
        self.start_date_edit.dateChanged.connect(self.load_attendance_data)
        self.end_date_edit.dateChanged.connect(self.load_attendance_data)
        self.status_present_cb.stateChanged.connect(self.load_attendance_data)
        self.status_absent_cb.stateChanged.connect(self.load_attendance_data)
        self.status_on_leave_cb.stateChanged.connect(self.load_attendance_data)
        # BUG FIX: Connect the new checkbox's signal to reload data.
        self.status_partial_cb.stateChanged.connect(self.load_attendance_data)
        self.search_filter_edit.textChanged.connect(self.load_attendance_data)
        self.refresh_button.clicked.connect(self.load_attendance_data)
        self.add_record_btn.clicked.connect(self.open_add_record_dialog)
        self.export_btn.clicked.connect(self.open_export_dialog)

    def populate_month_filter(self):
        """Populate the month filter dropdown with Jalali months."""
        self.month_filter_combo.blockSignals(True)
        self.month_filter_combo.clear()
        self.month_filter_combo.addItem(_("select_month"), -1)
        
        month_names = get_jalali_month_names()
        for i, month_name in enumerate(month_names):
            self.month_filter_combo.addItem(month_name, i + 1)
        
        today = jdatetime.date.today()
        self.month_filter_combo.setCurrentIndex(today.month)
        self.month_filter_combo.blockSignals(False)
        self.set_date_range_for_month(self.month_filter_combo.currentIndex())

    def on_month_selected(self, index):
        """Handle month selection from the dropdown."""
        self.set_date_range_for_month(index)

    def set_date_range_for_month(self, index):
        """Sets the start and end date edits based on the selected month index."""
        month = self.month_filter_combo.itemData(index)
        if month == -1: return
            
        today = jdatetime.date.today()
        year = today.year

        if month > today.month:
            year -= 1

        try:
            start_date_jalali = jdatetime.date(year, month, 1)
            days_in_month = jdatetime.j_days_in_month[month - 1]
            if month == 12 and not start_date_jalali.isleap():
                days_in_month = 29
            end_date_jalali = jdatetime.date(year, month, days_in_month)

            start_date_gregorian = jalali_to_gregorian(start_date_jalali)
            end_date_gregorian = jalali_to_gregorian(end_date_jalali)
            
            self.start_date_edit.setDate(QDate(start_date_gregorian))
            self.end_date_edit.setDate(QDate(end_date_gregorian))
        except ValueError as e:
            self.logger.error(f"Error calculating date range for month {month}: {e}")

    def load_filter_data(self):
        """Load data for filter controls (e.g., employee list)."""
        db = next(get_db_session())
        try:
            current_emp_id = self.employee_filter_combo.currentData()
            employees = employee_service.get_all_employees(db=db)

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
            db.close()

    def load_attendance_data(self):
        """Load attendance data based on current filter settings."""
        try:
            statuses = []
            if self.status_present_cb.isChecked(): statuses.append('present')
            if self.status_absent_cb.isChecked(): statuses.append('absent')
            if self.status_on_leave_cb.isChecked(): statuses.append('on_leave')
            # BUG FIX: Include 'partial' in the status filter if the checkbox is checked.
            if self.status_partial_cb.isChecked(): statuses.append('partial')

            self.attendance_model.set_filters(
                employee_id=self.employee_filter_combo.currentData(),
                start_date=self.start_date_edit.date().toPyDate(),
                end_date=self.end_date_edit.date().toPyDate(),
                statuses=statuses,
                search_text=self.search_filter_edit.text().strip()
            )
        except Exception as e:
            self.logger.error(f"Error loading attendance data: {e}", exc_info=True)
            QMessageBox.critical(self, _("dashboard_error"), _("error_loading_attendance_data", error=e))

    def update_aggregation_label(self):
        """Updates the aggregation label with totals from the model."""
        if self.employee_filter_combo.currentData() is None:
            self.aggregation_label.setText("")
            return

        totals = self.attendance_model.column_totals
        if not totals:
            self.aggregation_label.setText(_("no_data_for_filters"))
            return

        total_tardiness = minutes_to_hhmm(totals.get('tardiness', 0))
        total_early_departure = minutes_to_hhmm(totals.get('early_departure', 0))
        total_main_work = minutes_to_hhmm(totals.get('main_work', 0))
        total_overtime = minutes_to_hhmm(totals.get('overtime', 0))
        total_duration = minutes_to_hhmm(totals.get('total_duration', 0))

        text = (
            f"<b>{_('attendance_header_tardiness')}:</b> {total_tardiness} | "
            f"<b>{_('attendance_header_early_departure')}:</b> {total_early_departure} | "
            f"<b>{_('attendance_header_main_work')}:</b> {total_main_work} | "
            f"<b>{_('attendance_header_overtime')}:</b> {total_overtime} | "
            f"<b>{_('attendance_header_total_duration')}:</b> {total_duration}"
        )
        self.aggregation_label.setText(text)

    def setup_context_menu(self):
        """Setup the context menu for the table view."""
        self.attendance_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.attendance_table.customContextMenuRequested.connect(self.open_context_menu)

    def open_context_menu(self, position):
        menu = QMenu()
        index = self.attendance_table.indexAt(position)
        if not index.isValid(): return
        
        record = self.get_selected_record()
        if not record: return

        if record.id: # Existing record
            edit_action = menu.addAction(_("edit"))
            delete_action = menu.addAction(_("delete"))
            duplicate_action = menu.addAction(_("duplicate"))
            action = menu.exec(self.attendance_table.viewport().mapToGlobal(position))
            if action == edit_action: self.open_edit_or_add_dialog(index)
            elif action == delete_action: self.delete_selected_record()
            elif action == duplicate_action: self.duplicate_selected_record()
        else: # Placeholder record
            add_action = menu.addAction(_("attendance_add_record"))
            action = menu.exec(self.attendance_table.viewport().mapToGlobal(position))
            if action == add_action: self.open_edit_or_add_dialog(index)

    def get_selected_record(self) -> Optional[Attendance]:
        """Helper to get the Attendance object from the current selection."""
        indexes = self.attendance_table.selectionModel().selectedRows()
        if not indexes: return None
        return self.attendance_model.get_attendance_at_row(indexes[0].row())

    def delete_selected_record(self):
        record = self.get_selected_record()
        if not record or not record.id: return

        emp_name = self.attendance_model.employee_cache.get(record.employee_id, {}).get("name", "Unknown")
        reply = QMessageBox.question(
            self,
            _("confirm_delete_title"),
            _("confirm_delete_record_message", name=emp_name, date=record.date)
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                attendance_service.delete_attendance(record.id)
                audit_service.log_action("attendance", record.id, "delete", {}, self.current_user.username)
                self.load_attendance_data()
            except Exception as e:
                QMessageBox.critical(self, _("dashboard_error"), _("error_deleting_record", error=e))

    def duplicate_selected_record(self):
        record = self.get_selected_record()
        if not record or not record.id: return

        try:
            next_day = record.date + timedelta(days=1)
            
            # HEROIC IMPLEMENTATION: Include time_in_2 and time_out_2 in duplication
            new_record = attendance_service.add_manual_attendance(
                employee_id=record.employee_id,
                date=next_day,
                time_in=record.time_in,
                time_out=record.time_out,
                time_in_2=record.time_in_2,
                time_out_2=record.time_out_2,
                leave_start=record.leave_start,
                leave_end=record.leave_end,
                note=f"Duplicated from {record.date}",
                created_by=self.current_user.username
            )
            audit_service.log_action("attendance", new_record.id, "create", {"duplicated_from": record.id}, self.current_user.username)
            self.load_attendance_data()
            QMessageBox.information(self, _("success"), _("record_duplicated_success", date=next_day))

        except LeaveBalanceExceededError as e:
             QMessageBox.warning(self, _("error"), f"{e}")
        except Exception as e:
            QMessageBox.critical(self, _("dashboard_error"), _("error_duplicating_record", error=e))

    def open_add_record_dialog(self):
        employee_id = self.employee_filter_combo.currentData()
        if not employee_id:
            QMessageBox.warning(self, _("employee_validation_error"), _("dashboard_please_select_employee"))
            return

        dialog = AddAttendanceDialog(self, employee_id=employee_id, default_date=date.today())
        dialog.record_added.connect(self.handle_record_added)
        dialog.exec()

    def handle_record_added(self):
        self.load_attendance_data()
        QMessageBox.information(self, _("success"), _("record_added_success"))

    def open_edit_or_add_dialog(self, index: QModelIndex):
        """
        Opens the edit dialog for existing records or the add dialog for placeholder records.
        """
        record = self.attendance_model.get_attendance_at_row(index.row())
        if not record:
            return

        if record.id: # It's an existing record, open Edit dialog
            dialog = EditAttendanceDialog(record, self)
            dialog.record_updated.connect(self.handle_record_updated)
            dialog.exec()
        else: # It's a placeholder, open Add dialog
            dialog = AddAttendanceDialog(self, employee_id=record.employee_id, default_date=record.date)
            dialog.record_added.connect(self.handle_record_added)
            dialog.exec()

    def handle_record_updated(self, record_id: int, record_data: dict):
        """Handles the signal from the edit dialog."""
        dialog = self.sender()
        if not dialog: return
        try:
            attendance_service.update_attendance(attendance_id=record_id, **record_data)
            self.load_attendance_data()
            QMessageBox.information(self, _("success"), _("record_updated_success"))
            audit_service.log_action("attendance", record_id, "update", {k: str(v) for k, v in record_data.items()}, self.current_user.username)
        except LeaveBalanceExceededError as e:
            self.logger.warning(f"Update record failed: {e}")
            QMessageBox.warning(dialog, _("error"), f"Failed to update record: {e}")
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