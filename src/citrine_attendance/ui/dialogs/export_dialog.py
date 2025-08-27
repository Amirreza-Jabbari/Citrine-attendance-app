# src/citrine_attendance/ui/dialogs/export_dialog.py
"""Dialog for selecting export options."""
import sys
import logging
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QPushButton, QMessageBox, QApplication, QFileDialog, QRadioButton, QButtonGroup, QCheckBox, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal


class ExportDialog(QDialog):
    """A dialog window for selecting export options."""

    def __init__(self, default_filename: str, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.setWindowTitle("Export Data")
        self.setModal(True)
        self.resize(400, 200)
        self.default_filename = default_filename
        self.selected_format = "xlsx" # Default
        self.selected_path = "" # Will be set by user

        self.init_ui()

    def init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        title_label = QLabel("Export Options")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)

        # Format Selection
        format_label = QLabel("Select Format:")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Excel (.xlsx)", "CSV (.csv)", "PDF (.pdf)"])
        self.format_combo.currentIndexChanged.connect(self.on_format_changed)

        format_layout = QHBoxLayout()
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)
        layout.addLayout(format_layout)

        # CSV Specific Options (initially hidden)
        self.csv_options_widget = QWidget()
        csv_options_layout = QHBoxLayout(self.csv_options_widget)
        self.comma_radio = QRadioButton("Comma (,)")
        self.semicolon_radio = QRadioButton("Semicolon (;)")
        self.semicolon_radio.setChecked(True) # Default for Persian locales
        self.csv_delimiter_group = QButtonGroup()
        self.csv_delimiter_group.addButton(self.comma_radio)
        self.csv_delimiter_group.addButton(self.semicolon_radio)
        csv_options_layout.addWidget(QLabel("Delimiter:"))
        csv_options_layout.addWidget(self.comma_radio)
        csv_options_layout.addWidget(self.semicolon_radio)
        self.csv_options_widget.setVisible(False) # Hidden by default
        layout.addWidget(self.csv_options_widget)

        # Filename/Path Selection
        path_layout = QHBoxLayout()
        self.path_label = QLabel("Save As:")
        self.path_edit = QLabel(f"<i>{self.default_filename}</i>") # Placeholder
        self.path_edit.setWordWrap(True)
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.select_file_path)
        path_layout.addWidget(self.path_label)
        path_layout.addWidget(self.path_edit, 1) # Stretch
        path_layout.addWidget(self.browse_button)
        layout.addLayout(path_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.export_button = QPushButton("Export")
        self.export_button.clicked.connect(self.accept)
        self.export_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.export_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        # Set initial path based on default filename and default format
        self.update_default_path()

    def on_format_changed(self, index):
        """Handle format selection change."""
        format_text = self.format_combo.currentText()
        if "Excel" in format_text:
            self.selected_format = "xlsx"
            self.csv_options_widget.setVisible(False)
        elif "CSV" in format_text:
            self.selected_format = "csv"
            self.csv_options_widget.setVisible(True)
        elif "PDF" in format_text:
            self.selected_format = "pdf"
            self.csv_options_widget.setVisible(False)
        self.update_default_path()

    def update_default_path(self):
        """Update the displayed path based on selected format."""
        ext = f".{self.selected_format}"
        # Replace extension or add it
        if self.default_filename.endswith(('.xlsx', '.csv', '.pdf')):
            base_name = Path(self.default_filename).stem
        else:
            base_name = self.default_filename
        new_filename = f"{base_name}{ext}"
        self.selected_path = str(Path.home() / "Downloads" / new_filename) # Suggest Downloads
        self.path_edit.setText(f"<i>{self.selected_path}</i>")

    def select_file_path(self):
        """Open file dialog to select save location."""
        file_filter = ""
        if self.selected_format == "xlsx":
            file_filter = "Excel Files (*.xlsx)"
        elif self.selected_format == "csv":
            file_filter = "CSV Files (*.csv)"
        elif self.selected_format == "pdf":
            file_filter = "PDF Files (*.pdf)"

        # Use the current suggested path as the initial directory/filename
        initial_path = self.selected_path
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Export As", initial_path, f"{file_filter};;All Files (*)"
        )

        if filename:
            # Update selected path and potentially format if user changed extension
            self.selected_path = filename
            path_obj = Path(filename)
            suffix = path_obj.suffix.lower()
            if suffix == ".xlsx":
                self.selected_format = "xlsx"
                self.format_combo.setCurrentText("Excel (.xlsx)")
            elif suffix == ".csv":
                self.selected_format = "csv"
                self.format_combo.setCurrentText("CSV (.csv)")
            elif suffix == ".pdf":
                self.selected_format = "pdf"
                self.format_combo.setCurrentText("PDF (.pdf)")

            self.path_edit.setText(f"<i>{self.selected_path}</i>")

    def get_export_options(self):
        """Return the selected export options."""
        delimiter = ";"
        if self.selected_format == "csv":
            if self.comma_radio.isChecked():
                delimiter = ","
            # else, keep semicolon
        return {
            "format": self.selected_format,
            "path": Path(self.selected_path),
            "delimiter": delimiter
        }

# Example usage (if run directly for testing)
# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     dialog = ExportDialog("attendance_report")
#     if dialog.exec() == QDialog.DialogCode.Accepted:
#         options = dialog.get_export_options()
#         print(options)
#     sys.exit(app.exec())