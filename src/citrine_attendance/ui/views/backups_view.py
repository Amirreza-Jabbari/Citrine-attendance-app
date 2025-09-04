# src/citrine_attendance/ui/views/backups_view.py
"""View for managing backups."""
import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableView,
    QMessageBox, QHeaderView, QLabel, QTextEdit, QAbstractItemView, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QAbstractTableModel, QModelIndex, QVariant
from PyQt6.QtGui import QBrush, QColor

from ...services.backup_service import backup_service, BackupServiceError
from ...database import BackupRecord
from ...date_utils import format_date_for_display # For displaying backup creation time


class BackupsTableModel(QAbstractTableModel):
    """Model for displaying backup records."""
    TIMESTAMP_COL = 0
    FILENAME_COL = 1
    SIZE_COL = 2
    ENCRYPTED_COL = 3
    COLUMN_HEADERS = ["Created At", "Filename", "Size (Bytes)", "Encrypted"]
    COLUMN_COUNT = len(COLUMN_HEADERS)

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.backup_data: list[BackupRecord] = []

    def load_data(self):
        """Load backup records from the service."""
        try:
            backups = backup_service.list_backups()
            self.beginResetModel()
            self.backup_data = list(backups)
            self.endResetModel()
            self.logger.debug(f"Loaded {len(self.backup_data)} backup records into model.")
        except Exception as e:
            self.logger.error(f"Error loading backups into model: {e}", exc_info=True)
            raise

    def rowCount(self, parent=QModelIndex()):
        return len(self.backup_data)

    def columnCount(self, parent=QModelIndex()):
        return self.COLUMN_COUNT

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.backup_data):
            return QVariant()

        record = self.backup_data[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.TIMESTAMP_COL:
                if record.created_at:
                    # Format based on user preference? For now, use a standard format
                    # You can integrate config here if needed
                    return record.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    # Or use date_utils: return format_date_for_display(record.created_at.date(), record.created_at)
                return ""
            elif col == self.FILENAME_COL:
                return record.file_name
            elif col == self.SIZE_COL:
                return str(record.size_bytes) if record.size_bytes is not None else ""
            elif col == self.ENCRYPTED_COL:
                return "Yes" if record.encrypted else "No"

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col == self.SIZE_COL:
                return Qt.AlignmentFlag.AlignRight + Qt.AlignmentFlag.AlignVCenter

        elif role == Qt.ItemDataRole.BackgroundRole:
             # Example: Highlight encrypted backups
             if col == self.ENCRYPTED_COL and record.encrypted:
                 return QBrush(QColor(200, 230, 200)) # Light green

        return QVariant()

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < self.COLUMN_COUNT:
                return self.COLUMN_HEADERS[section]
        return QVariant()

    def get_backup_at_row(self, row: int):
        """Get the BackupRecord object for a given row."""
        if 0 <= row < len(self.backup_data):
            return self.backup_data[row]
        return None


class BackupsView(QWidget):
    """The backups management view widget."""

    def __init__(self, current_user):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.backups_model = BackupsTableModel()

        self.init_ui()
        self.load_backups()

    def init_ui(self):
        """Initialize the backups view UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- Top Bar ---
        top_layout = QHBoxLayout()
        self.create_backup_btn = QPushButton("Create Backup Now")
        self.create_backup_btn.setStyleSheet(self.get_button_style("#e5e7eb"))
        self.create_backup_btn.clicked.connect(self.create_manual_backup)
        top_layout.addWidget(self.create_backup_btn)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setStyleSheet(self.get_button_style("#4caf50"))
        self.refresh_btn.clicked.connect(self.load_backups)
        top_layout.addWidget(self.refresh_btn)

        top_layout.addStretch()
        layout.addLayout(top_layout)

        # --- Backups Table ---
        self.backups_table = QTableView()
        self.backups_table.setAlternatingRowColors(True)
        self.backups_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.backups_table.setModel(self.backups_model)
        self.backups_table.setSortingEnabled(False) # Simple list, no sorting for now

        header = self.backups_table.horizontalHeader()
        header.setStretchLastSection(True)
        # Set specific column widths if desired
        # header.setSectionResizeMode(BackupsTableModel.TIMESTAMP_COL, QHeaderView.ResizeMode.ResizeToContents)
        # header.setSectionResizeMode(BackupsTableModel.ENCRYPTED_COL, QHeaderView.ResizeMode.ResizeToContents)

        # Enable context menu or double-click for actions
        self.backups_table.doubleClicked.connect(self.on_backup_double_clicked)

        layout.addWidget(self.backups_table)

        # --- Details Panel (Placeholder) ---
        self.details_label = QLabel("Select a backup to see details.")
        self.details_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(self.details_label)

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

    def load_backups(self):
        """Load backups into the table."""
        try:
            self.backups_model.load_data()
            self.details_label.setText(f"Total backups: {self.backups_model.rowCount()}")
        except Exception as e:
            self.logger.error(f"Error loading backups: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to load backups: {e}")

    def create_manual_backup(self):
        """Create a manual backup."""
        try:
            backup_path = backup_service.create_backup(manual=True)
            QMessageBox.information(
                self, "Backup Created",
                f"Backup successfully created:\n{backup_path}"
            )
            self.logger.info(f"Manual backup created: {backup_path}")
            self.load_backups() # Refresh the list
        except Exception as e:
            self.logger.error(f"Error creating manual backup: {e}", exc_info=True)
            QMessageBox.critical(self, "Backup Error", f"Failed to create backup: {e}")

    def refresh_view(self):
        """Public method to refresh the backups list displayed in the view."""
        self.load_backups()

    def on_backup_double_clicked(self, index):
        """Handle double-click on a backup row."""
        if not index.isValid():
            return
        row = index.row()
        backup_record = self.backups_model.get_backup_at_row(row)
        if backup_record:
            # Show details or open a context menu
            # For now, show a simple info dialog with restore option
            reply = QMessageBox.question(
                self, 'Restore Backup?',
                f"Are you sure you want to restore the database from this backup?\n"
                f"Filename: {backup_record.file_name}\n"
                f"Created: {backup_record.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"WARNING: This will REPLACE the current database. "
                f"Ensure all work is saved. The application will restart after restore.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.restore_backup(backup_record.id)

    def restore_backup(self, backup_id: int):
        """Restore from a specific backup."""
        try:
            # Confirmation again, as it's critical
            reply = QMessageBox.warning(
                self, 'Final Confirmation',
                "This action is irreversible and will shut down the application to restore the database. "
                "Are you absolutely sure?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                backup_service.restore_backup(backup_id)
                QMessageBox.information(
                    self, "Restore Successful",
                    "Database restored successfully. The application will now close. "
                    "Please restart it."
                )
                self.logger.info(f"Database restored from backup ID {backup_id}. Application will exit.")
                QApplication.instance().quit() # Or close the main window

        except Exception as e:
            self.logger.error(f"Error restoring backup ID {backup_id}: {e}", exc_info=True)
            QMessageBox.critical(self, "Restore Error", f"Failed to restore backup: {e}")

    # --- Placeholder methods ---
    # def delete_selected_backup(self): pass # Add delete button/context menu

# Example usage (if run directly)
# if __name__ == '__main__':
#     from PyQt6.QtWidgets import QApplication, QMainWindow
#     import sys
#     from ...database import init_db, User
#     init_db()
#     app = QApplication(sys.argv)
#     user = User(username="admin", role="admin") # Assume admin for backups
#     window = QMainWindow()
#     backups_view = BackupsView(user)
#     window.setCentralWidget(backups_view)
#     window.show()
#     sys.exit(app.exec())