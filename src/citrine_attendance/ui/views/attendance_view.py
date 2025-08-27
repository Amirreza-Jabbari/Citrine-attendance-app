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
        self.add_record_btn = QPushButton("Add Record")
        self.add_record_btn.setStyleSheet(self.get_button_style("#11563a")) # Brand color
        self.add_record_btn.clicked.connect(self.open_add_record_dialog)

        self.export_btn = QPushButton("Export")
        self.export_btn.setStyleSheet(self.get_button_style("#4caf50")) # Green
        self.export_btn.clicked.connect(self.open_export_dialog)

        # Create a container widget for the buttons
        button_container = QWidget()
        button_container_layout = QHBoxLayout(button_container)
        button_container_layout.setContentsMargins(0, 0, 0, 0)
        button_container_layout.addWidget(self.add_record_btn)
        button_container_layout.addWidget(self.export_btn)
        button_container_layout.addStretch()

        # Add the button container to the main filter bar layout
        filter_layout = self.filter_bar.layout()
        if filter_layout:
            # Insert before the last item (the stretch)
            filter_layout.insertWidget(filter_layout.count() - 1, button_container)
        # --- End Buttons ---
        layout.addWidget(self.filter_bar)

        # --- Table View ---
        self.attendance_table = QTableView()
        self.attendance_table.setAlternatingRowColors(True)
        self.attendance_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems) # Allow cell selection
        self.attendance_table.setSortingEnabled(False) # Sorting handled by model filters
        self.attendance_table.setModel(self.attendance_model)
        self.attendance_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)

        # Configure header
        header = self.attendance_table.horizontalHeader()
        header.setStretchLastSection(True) # Stretch 'Note' column
        # Set specific section resize modes if needed
        # header.setSectionResizeMode(AttendanceTableModel.DATE_COL, QHeaderView.ResizeMode.ResizeToContents)
        # header.setSectionResizeMode(AttendanceTableModel.STATUS_COL, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.attendance_table)

        # --- Aggregation Row (Updated to remove Late and HalfDay) ---
        self.aggregation_label = QLabel("Aggregates: Total Mins: 0, Present: 0, Absent: 0")
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
        filter_layout.addWidget(QLabel("Employee:"))
        self.employee_filter_combo = QComboBox()
        self.employee_filter_combo.setMinimumWidth(150)
        self.employee_filter_combo.currentIndexChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.employee_filter_combo)

        # --- Modified Date Range Filter Section ---
        date_range_layout = QHBoxLayout()
        date_range_layout.addWidget(QLabel("Date Range:"))

        # Start Date
        start_layout = QVBoxLayout()
        start_layout.setSpacing(0)
        start_layout.addWidget(QLabel("Start:")) # Label for clarity
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate.currentDate().addDays(-30)) # Default start
        # Connect to on_filter_changed to trigger data reload
        self.start_date_edit.dateChanged.connect(self.on_filter_changed)
        self.start_date_edit.setObjectName("startDateEdit") # For styling if needed
        # --- Add QLabel for Jalali display ---
        self.start_jalali_label = QLabel()
        self.start_jalali_label.setStyleSheet("font-size: 11px; color: gray;") # Style it subtly
        start_layout.addWidget(self.start_date_edit)
        start_layout.addWidget(self.start_jalali_label)
        # --- End Add QLabel ---
        date_range_layout.addLayout(start_layout)

        # End Date
        end_layout = QVBoxLayout()
        end_layout.setSpacing(0)
        end_layout.addWidget(QLabel("End:")) # Label for clarity
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate()) # Default end (today)
        # Connect to on_filter_changed to trigger data reload
        self.end_date_edit.dateChanged.connect(self.on_filter_changed)
        self.end_date_edit.setObjectName("endDateEdit") # For styling if needed
        # --- Add QLabel for Jalali display ---
        self.end_jalali_label = QLabel()
        self.end_jalali_label.setStyleSheet("font-size: 11px; color: gray;")
        end_layout.addWidget(self.end_date_edit)
        end_layout.addWidget(self.end_jalali_label)
        # --- End Add QLabel ---
        date_range_layout.addLayout(end_layout)

        filter_layout.addLayout(date_range_layout)
        # --- End Modified Date Range Filter Section ---

        # --- Status Filter (Updated to remove Late and Half Day) ---
        filter_layout.addWidget(QLabel("Status:"))
        self.status_present_cb = QCheckBox("Present")
        self.status_present_cb.setChecked(True)
        self.status_present_cb.stateChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.status_present_cb)

        # self.status_late_cb = QCheckBox("Late") # Removed
        # self.status_late_cb.stateChanged.connect(self.on_filter_changed) # Removed

        self.status_absent_cb = QCheckBox("Absent")
        self.status_absent_cb.setChecked(True)
        self.status_absent_cb.stateChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.status_absent_cb)

        # self.status_halfday_cb = QCheckBox("Half Day") # Removed
        # self.status_halfday_cb.stateChanged.connect(self.on_filter_changed) # Removed

        # Search Filter
        filter_layout.addWidget(QLabel("Search:"))
        self.search_filter_edit = QLineEdit()
        self.search_filter_edit.setPlaceholderText("Search notes or status...")
        self.search_filter_edit.textChanged.connect(self.on_filter_changed)
        self.search_filter_edit.returnPressed.connect(self.on_filter_changed)
        filter_layout.addWidget(self.search_filter_edit)

        # Refresh Button
        self.refresh_button = QPushButton("Refresh")
        refresh_icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        self.refresh_button.setIcon(refresh_icon)
        self.refresh_button.clicked.connect(self.load_attendance_data)
        filter_layout.addWidget(self.refresh_button)

        filter_layout.addStretch() # Push everything to the left

        # --- Initialize Jalali labels ---
        # Call the handler once to set initial display
        self.on_date_range_changed()

    def load_filter_data(self):
        """Load data needed for the filter controls (e.g., employee list)."""
        try:
            session_gen = get_db_session()
            self.db_session = next(session_gen)

            # Load employees for the dropdown
            employees = employee_service.get_all_employees(db=self.db_session)
            self.employee_filter_combo.clear()
            self.employee_filter_combo.addItem("All Employees", None) # Data role is None for 'All'
            for emp in employees:
                display_name = f"{emp.first_name} {emp.last_name}".strip() or emp.email
                self.employee_filter_combo.addItem(display_name, emp.id)

        except Exception as e:
            self.logger.error(f"Error loading filter data: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load filter data: {e}")
        finally:
            if self.db_session:
                self.db_session.close()
                self.db_session = None

    def load_attendance_data(self):
        """Load attendance data into the model based on current filters."""
        try:
            # Get filter values
            selected_emp_id = self.employee_filter_combo.currentData()
            start_qdate = self.start_date_edit.date()
            end_qdate = self.end_date_edit.date()

            # Convert QDate to Python date
            start_date_py = start_qdate.toPyDate() if not start_qdate.isNull() else None
            end_date_py = end_qdate.toPyDate() if not end_qdate.isNull() else None

            # --- Get status filter states (Updated to remove Late and Half Day) ---
            statuses = []
            if self.status_present_cb.isChecked():
                # Use the model's INVERSE class attribute to get the raw status value
                # Note: STATUS_DISPLAY_INVERSE in the model now only has Present/Absent
                statuses.append(AttendanceTableModel.STATUS_DISPLAY_INVERSE.get("Present", "present"))
            # if self.status_late_cb.isChecked(): # Removed
            #     statuses.append(AttendanceTableModel.STATUS_DISPLAY_INVERSE.get("Late", "late")) # Removed
            if self.status_absent_cb.isChecked():
                statuses.append(AttendanceTableModel.STATUS_DISPLAY_INVERSE.get("Absent", "absent"))
            # if self.status_halfday_cb.isChecked(): # Removed
            #     statuses.append(AttendanceTableModel.STATUS_DISPLAY_INVERSE.get("Half Day", "halfday")) # Removed

            search_text = self.search_filter_edit.text().strip()

            # Apply filters to the model
            self.attendance_model.set_filters(
                employee_id=selected_emp_id,
                start_date=start_date_py,
                end_date=end_date_py,
                statuses=statuses,
                search_text=search_text
            )
            self.logger.debug("Attendance data loaded/refreshed based on filters.")

            # Update aggregates
            self.update_aggregates()

        except Exception as e:
            self.logger.error(f"Error loading attendance data: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load attendance data: {e}")

    # --- on_filter_changed remains the same, but relies on updated on_date_range_changed ---
    def on_filter_changed(self):
        """Slot called when any filter control changes."""
        # Debouncing might be needed for text input, but for simplicity, reload on any change
        self.load_attendance_data()

    # --- update_aggregates (Updated to remove Late and HalfDay counts) ---
    def update_aggregates(self):
        """Calculate and display aggregate values."""
        try:
            aggregates = self.attendance_model.get_aggregates()
            # Updated aggregate text to only show Present and Absent
            agg_text = (
                f"Aggregates: "
                f"Total Mins: {aggregates['total_minutes']}, "
                f"Present: {aggregates['present_days']}, "
                f"Absent: {aggregates['absent_days']}"
                # Late and Half Day removed
            )
            self.aggregation_label.setText(agg_text)
        except Exception as e:
            self.logger.error(f"Error calculating aggregates: {e}", exc_info=True)
            self.aggregation_label.setText("Aggregates: Error calculating")

    # --- Context Menu ---
    def setup_context_menu(self):
        """Setup the context menu for the table view."""
        self.attendance_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.attendance_table.customContextMenuRequested.connect(self.open_context_menu)

    def open_context_menu(self, position):
        """Open the context menu."""
        menu = QMenu()
        index = self.attendance_table.indexAt(position)
        if not index.isValid():
            return

        # Actions
        mark_absent_action = QAction("Mark Absent", self)
        mark_absent_action.triggered.connect(lambda: self.mark_selected_absent())
        menu.addAction(mark_absent_action)

        add_note_action = QAction("Add/Edit Note", self)
        add_note_action.triggered.connect(lambda: self.add_note_to_selected())
        menu.addAction(add_note_action)

        delete_row_action = QAction("Delete Record", self)
        delete_row_action.triggered.connect(lambda: self.delete_selected_record())
        menu.addAction(delete_row_action)

        duplicate_row_action = QAction("Duplicate Record", self)
        duplicate_row_action.triggered.connect(lambda: self.duplicate_selected_record())
        menu.addAction(duplicate_row_action)

        menu.exec(self.attendance_table.viewport().mapToGlobal(position))

    def mark_selected_absent(self):
        """Mark the selected record as absent."""
        indexes = self.attendance_table.selectionModel().selectedIndexes()
        if not indexes:
            return
        index = indexes[0] # Get the first selected cell
        row = index.row()
        record = self.attendance_model.get_attendance_at_row(row)
        if not record:
            return

        try:
            db_session = attendance_service._get_session()
            try:
                # Update the record to be absent
                updated_record = attendance_service.update_attendance(
                    attendance_id=record.id,
                    time_in=None,
                    time_out=None,
                    note=record.note, # Keep existing note
                    db=db_session
                )
                # Update the model's record
                self.attendance_model.attendance_data[row] = updated_record
                # Refresh the row display
                first_col_idx = self.attendance_model.index(row, 0)
                last_col_idx = self.attendance_model.index(row, self.attendance_model.COLUMN_COUNT - 1)
                self.attendance_model.dataChanged.emit(first_col_idx, last_col_idx, [Qt.ItemDataRole.DisplayRole])
                self.logger.info(f"Record ID {record.id} marked as absent by {self.current_user.username}.")
                # Log the action
                audit_service.log_action("attendance", record.id, "update", {"status": "absent"}, self.current_user.username)
                # Update aggregates
                self.update_aggregates()
            finally:
                db_session.close()
        except Exception as e:
            self.logger.error(f"Error marking record as absent: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to mark record as absent: {e}")

    def add_note_to_selected(self):
        """Add or edit a note for the selected record."""
        indexes = self.attendance_table.selectionModel().selectedIndexes()
        if not indexes:
            return
        index = indexes[0] # Get the first selected cell
        row = index.row()
        record = self.attendance_model.get_attendance_at_row(row)
        if not record:
            return

        current_note = record.note or ""
        note, ok = QInputDialog.getMultiLineText(self, "Edit Note", "Note:", current_note)
        if ok:
            try:
                db_session = attendance_service._get_session()
                try:
                    updated_record = attendance_service.update_attendance(
                        attendance_id=record.id,
                        time_in=record.time_in,
                        time_out=record.time_out,
                        note=note if note else None,
                        db=db_session
                    )
                    self.attendance_model.attendance_data[row] = updated_record
                    # Refresh the note cell display
                    note_col_idx = self.attendance_model.index(row, AttendanceTableModel.NOTE_COL)
                    self.attendance_model.dataChanged.emit(note_col_idx, note_col_idx, [Qt.ItemDataRole.DisplayRole])
                    self.logger.info(f"Note updated for record ID {record.id} by {self.current_user.username}.")
                    # Log the action
                    audit_service.log_action("attendance", record.id, "update", {"note": note}, self.current_user.username)
                finally:
                    db_session.close()
            except Exception as e:
                self.logger.error(f"Error updating note: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to update note: {e}")

    def delete_selected_record(self):
        """Delete the selected attendance record."""
        indexes = self.attendance_table.selectionModel().selectedIndexes()
        if not indexes:
            return
        index = indexes[0] # Get the first selected cell
        row = index.row()
        record = self.attendance_model.get_attendance_at_row(row)
        if not record:
            return

        reply = QMessageBox.question(
            self, 'Confirm Delete',
            f"Are you sure you want to delete this attendance record for {self.attendance_model.employee_cache.get(record.employee_id, 'Unknown')} on {record.date}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                db_session = attendance_service._get_session()
                try:
                    attendance_service.delete_attendance(record.id, db=db_session)
                    # Remove from model and refresh view
                    self.attendance_model.beginRemoveRows(QModelIndex(), row, row)
                    del self.attendance_model.attendance_data[row]
                    self.attendance_model.endRemoveRows()
                    self.logger.info(f"Record ID {record.id} deleted by {self.current_user.username}.")
                    # Log the action
                    audit_service.log_action("attendance", record.id, "delete", {}, self.current_user.username)
                    # Update aggregates
                    self.update_aggregates()
                finally:
                    db_session.close()
            except Exception as e:
                self.logger.error(f"Error deleting record: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to delete record: {e}")

    def duplicate_selected_record(self):
        """Duplicate the selected attendance record."""
        indexes = self.attendance_table.selectionModel().selectedIndexes()
        if not indexes:
            return
        index = indexes[0] # Get the first selected cell
        row = index.row()
        record = self.attendance_model.get_attendance_at_row(row)
        if not record:
            return

        try:
            db_session = attendance_service._get_session()
            try:
                # Create a new record with the same data (except ID, created/updated times)
                new_record = attendance_service.add_manual_attendance(
                    employee_id=record.employee_id,
                    date=record.date,
                    time_in=record.time_in,
                    time_out=record.time_out,
                    note=record.note,
                    created_by=self.current_user.username,
                    db=db_session
                )
                # Add to model and refresh view
                self.attendance_model.beginInsertRows(QModelIndex(), row + 1, row + 1)
                self.attendance_model.attendance_data.insert(row + 1, new_record)
                self.attendance_model.endInsertRows()
                self.logger.info(f"Record ID {record.id} duplicated by {self.current_user.username}. New ID: {new_record.id}")
                # Log the action
                audit_service.log_action("attendance", new_record.id, "create", {"duplicated_from": record.id}, self.current_user.username)
                # Update aggregates
                self.update_aggregates()
            finally:
                db_session.close()
        except Exception as e:
            self.logger.error(f"Error duplicating record: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to duplicate record: {e}")

    # --- Keyboard Shortcuts ---
    def setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for the table view."""
        # F2 to edit selected cell
        f2_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F2), self.attendance_table)
        f2_shortcut.activated.connect(self.edit_selected_cell)

        # Delete key to delete selected record
        delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.attendance_table)
        delete_shortcut.activated.connect(self.delete_selected_record)

        # Ctrl+C for copy
        copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self.attendance_table)
        copy_shortcut.activated.connect(self.copy_selection)

        # Ctrl+V for paste (basic implementation)
        paste_shortcut = QShortcut(QKeySequence.StandardKey.Paste, self.attendance_table)
        paste_shortcut.activated.connect(self.paste_selection)

        # Ctrl+A for select all
        select_all_shortcut = QShortcut(QKeySequence.StandardKey.SelectAll, self.attendance_table)
        select_all_shortcut.activated.connect(self.attendance_table.selectAll)

    def edit_selected_cell(self):
        """Edit the currently selected cell."""
        index = self.attendance_table.currentIndex()
        if index.isValid():
            self.attendance_table.edit(index)

    def copy_selection(self):
        """Copy selected cells to clipboard."""
        selection_model = self.attendance_table.selectionModel()
        if not selection_model.hasSelection():
            return

        selected_indexes = selection_model.selectedIndexes()
        if not selected_indexes:
            return

        # Sort indexes by row and column to ensure correct order
        selected_indexes.sort(key=lambda idx: (idx.row(), idx.column()))

        # Get the data
        rows = {}
        for index in selected_indexes:
            if index.row() not in rows:
                rows[index.row()] = {}
            # Use the model's data method to get the display text
            rows[index.row()][index.column()] = self.attendance_model.data(index, Qt.ItemDataRole.DisplayRole)

        # Convert to string format (tab-separated columns, newline-separated rows)
        min_row = min(rows.keys())
        max_row = max(rows.keys())
        min_col = min(min(cols.keys()) for cols in rows.values())
        max_col = max(max(cols.keys()) for cols in rows.values())

        copied_text = ""
        for r in range(min_row, max_row + 1):
            row_data = []
            for c in range(min_col, max_col + 1):
                row_data.append(str(rows.get(r, {}).get(c, "")))
            copied_text += "\t".join(row_data) + "\n"

        clipboard = QApplication.clipboard()
        clipboard.setText(copied_text)
        self.logger.debug("Selection copied to clipboard.")

    def paste_selection(self):
        """Paste data from clipboard into selected cells."""
        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        if not mime_data.hasText():
            return

        text = mime_data.text()
        if not text:
            return

        # Parse the text (assuming tab-separated columns, newline-separated rows)
        lines = text.strip().split('\n')
        if not lines:
            return

        # Get the top-left cell of the current selection as the paste origin
        selection_model = self.attendance_table.selectionModel()
        if not selection_model.hasSelection():
            QMessageBox.information(self, "No Selection", "Please select a cell to paste data into.")
            return

        selected_indexes = selection_model.selectedIndexes()
        if not selected_indexes:
            return

        # Find the top-left selected cell
        min_row = min(idx.row() for idx in selected_indexes)
        min_col = min(idx.column() for idx in selected_indexes)

        # Iterate through the pasted data and update the model
        for r, line in enumerate(lines):
            row = min_row + r
            if row >= self.attendance_model.rowCount():
                break # Don't paste beyond the model
            columns = line.split('\t')
            for c, value in enumerate(columns):
                col = min_col + c
                if col >= self.attendance_model.columnCount():
                    continue # Don't paste beyond the model columns
                index = self.attendance_model.index(row, col)
                if self.attendance_model.flags(index) & Qt.ItemFlag.ItemIsEditable:
                    # Try to set the data. The model's setData will handle validation and conversion.
                    success = self.attendance_model.setData(index, value.strip(), Qt.ItemDataRole.EditRole)
                    if not success:
                        self.logger.warning(f"Failed to paste data '{value}' into cell ({row}, {col})")
                else:
                    self.logger.debug(f"Cell ({row}, {col}) is not editable, skipping paste.")

        self.logger.debug("Data pasted from clipboard.")
        # Update aggregates after paste
        self.update_aggregates()

    # --- Add Record Functionality ---
    def open_add_record_dialog(self):
        """Open the dialog to add a new manual attendance record."""
        self.add_dialog = AddAttendanceDialog(self) # Parent to this view
        self.add_dialog.record_added.connect(self.handle_record_added)
        dialog_result = self.add_dialog.exec()

    def handle_record_added(self, record_data_dict):
        """Handle the signal from the AddAttendanceDialog when 'Add Record' is clicked."""
        try:
            # Use the model to add the record via the service
            new_record = self.attendance_model.add_attendance_record(**record_data_dict)

            # If successful, close the dialog and show confirmation
            if self.add_dialog:
                self.add_dialog.accept()

            QMessageBox.information(
                self, "Success",
                f"Manual attendance record added successfully for "
                f"{self.add_dialog.employee_combo.currentText() if self.add_dialog else 'employee'}."
            )
            self.logger.info(f"Manual attendance record added via UI: ID {new_record.id}")
            # Log the action
            audit_service.log_action("attendance", new_record.id, "create", record_data_dict, self.current_user.username)

            # The model's add_attendance_record calls load_data which refreshes the view.

        except Exception as e:
            # This will catch service errors like AttendanceAlreadyExistsError etc.
            self.logger.error(f"Add Attendance Record failed: {e}", exc_info=True)
            QMessageBox.critical(
                self.add_dialog, "Error",
                f"Failed to add attendance record: {e}"
            )
            # Keep the dialog open for correction if possible, otherwise close
            # For now, let the user decide (dialog stays open on error)

    # --- Export Functionality ---
    def open_export_dialog(self):
        """Open the dialog to select export options."""
        # Generate a default filename based on current date
        today_str = date.today().strftime("%Y%m%d")
        default_name = f"attendance_export_{today_str}"

        self.export_dialog = ExportDialog(default_name, self)
        if self.export_dialog.exec() == QDialog.DialogCode.Accepted:
            options = self.export_dialog.get_export_options()
            self.perform_export(options)

    # --- perform_export (Updated to remove Late and Half Day from status filter) ---
    def perform_export(self, options: dict):
        """Perform the actual export based on selected options."""
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

            # Get current filter settings
            selected_emp_id = self.employee_filter_combo.currentData()
            start_qdate = self.start_date_edit.date()
            end_qdate = self.end_date_edit.date()
            start_date_py = start_qdate.toPyDate() if not start_qdate.isNull() else None
            end_date_py = end_qdate.toPyDate() if not end_qdate.isNull() else None

            # --- Get status filter states for export (Updated) ---
            statuses = []
            if self.status_present_cb.isChecked():
                statuses.append(AttendanceTableModel.STATUS_DISPLAY_INVERSE.get("Present", "present"))
            # if self.status_late_cb.isChecked(): # Removed
            #     statuses.append(AttendanceTableModel.STATUS_DISPLAY_INVERSE.get("Late", "late")) # Removed
            if self.status_absent_cb.isChecked():
                statuses.append(AttendanceTableModel.STATUS_DISPLAY_INVERSE.get("Absent", "absent"))
            # if self.status_halfday_cb.isChecked(): # Removed
            #     statuses.append(AttendanceTableModel.STATUS_DISPLAY_INVERSE.get("Half Day", "halfday")) # Removed

            search_text = self.search_filter_edit.text().strip()

            # Fetch data for export using the service
            # This needs to be called with a session, get one from the model or service
            # Let's get it from the service helper
            db_session = attendance_service._get_session() # Use service helper
            try:
                export_data = attendance_service.get_attendance_for_export(
                    employee_id=selected_emp_id,
                    start_date=start_date_py,
                    end_date=end_date_py,
                    statuses=statuses,
                    db=db_session
                )
            finally:
                db_session.close()

            if not export_data:
                QMessageBox.information(self, "No Data", "There is no data matching the current filters to export.")
                return

            # Perform export based on format
            if format_type == "csv":
                export_service.export_to_csv(export_data, export_path, delimiter=delimiter)
            elif format_type == "xlsx":
                export_service.export_to_xlsx(export_data, export_path)
            elif format_type == "pdf":
                # Get a simple title for the PDF
                title = f"Attendance Report ({start_date_py or 'Start'} to {end_date_py or 'End'})"
                export_service.export_to_pdf(export_data, export_path, title=title)

            QMessageBox.information(
                self, "Export Successful",
                f"Data successfully exported to:\n{export_path}"
            )
            self.logger.info(f"Attendance data exported to {export_path} (Format: {format_type})")
            # Log the action
            audit_service.log_action("export", 0, "create", {"path": str(export_path), "format": format_type}, self.current_user.username)

        except ExportServiceError as e:
            self.logger.error(f"Export failed (service error): {e}", exc_info=True)
            QMessageBox.critical(self, "Export Failed", f"Export failed: {e}")
        except Exception as e:
            self.logger.error(f"Export failed (unexpected error): {e}", exc_info=True)
            QMessageBox.critical(self, "Export Error", f"An unexpected error occurred during export: {e}")

    # --- UI Helper Methods ---
    def get_button_style(self, bg_color):
        """Helper for consistent button styles."""
        hover_color = self.darken_color(bg_color)
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
            background-color: {hover_color};
        }}
        QPushButton:disabled {{
            background-color: #bdbdbd;
            color: #9e9e9e;
        }}
        """

    def darken_color(self, color_hex):
        """Simple hex color darkener."""
        color_hex = color_hex.lstrip('#')
        rgb = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))
        darker_rgb = tuple(max(0, int(c * 0.9)) for c in rgb)
        return f"#{darker_rgb[0]:02x}{darker_rgb[1]:02x}{darker_rgb[2]:02x}"
    
    # --- on_date_range_changed (Fixed to properly update labels and connect signals) ---
    def on_date_range_changed(self):
        """Update Jalali date labels when QDateEdit dates change."""
        # Mapping for Persian digits
        digit_map = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')

        # Update Start Date Jalali Label
        start_qdate = self.start_date_edit.date()
        if not start_qdate.isNull():
            try:
                # Convert QDate to Python date
                start_py_date = start_qdate.toPyDate()
                # Convert to Jalali
                start_jalali = jdatetime.date.fromgregorian(date=start_py_date)
                # Format: ۷ خرداد ۱۴۰۳
                day_str = str(start_jalali.day).translate(digit_map)
                month_name = start_jalali.j_months[start_jalali.month - 1] # j_months is 0-indexed
                year_str = str(start_jalali.year).translate(digit_map)
                jalali_str = f"{day_str} {month_name} {year_str}"
                self.start_jalali_label.setText(jalali_str)
                # Optional: Set tooltip to Gregorian ISO
                self.start_jalali_label.setToolTip(start_py_date.isoformat())
            except Exception as e:
                self.logger.warning(f"Error converting start date to Jalali: {e}")
                self.start_jalali_label.setText("")

        # Update End Date Jalali Label
        end_qdate = self.end_date_edit.date()
        if not end_qdate.isNull():
            try:
                end_py_date = end_qdate.toPyDate()
                end_jalali = jdatetime.date.fromgregorian(date=end_py_date)
                day_str = str(end_jalali.day).translate(digit_map)
                month_name = end_jalali.j_months[end_jalali.month - 1]
                year_str = str(end_jalali.year).translate(digit_map)
                jalali_str = f"{day_str} {month_name} {year_str}"
                self.end_jalali_label.setText(jalali_str)
                self.end_jalali_label.setToolTip(end_py_date.isoformat())
            except Exception as e:
                self.logger.warning(f"Error converting end date to Jalali: {e}")
                self.end_jalali_label.setText("")


    # --- Placeholder methods for future functionality ---
    # def on_selection_changed(self): pass # For status bar info or context menu
    # def delete_selected_records(self): pass # For deletion
    # def contextMenuEvent(self, event): pass # For right-click context menu

# Example usage (if run directly)
# if __name__ == '__main__':
#     from PyQt6.QtWidgets import QApplication, QMainWindow
#     import sys
#     from ...database import init_db, User
#     init_db()
#     app = QApplication(sys.argv)
#     user = User(username="testuser", role="admin")
#     window = QMainWindow()
#     att_view = AttendanceView(user)
#     window.setCentralWidget(att_view)
#     window.show()
#     sys.exit(app.exec())