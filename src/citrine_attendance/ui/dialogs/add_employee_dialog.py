# src/citrine_attendance/ui/dialogs/add_employee_dialog.py
"""Dialog for adding a new employee with localization support (English / Persian)."""
import logging
import re
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton,
    QMessageBox, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal

from ...config import config
from ...locale import _  # translator helper

logger = logging.getLogger(__name__)


class AddEmployeeDialog(QDialog):
    """A dialog window for adding a new employee (localized)."""
    employee_added = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)

        # Determine language and direction
        self.language = str(config.settings.get("language", "en")).lower()
        self.is_fa = (self.language == "fa")

        # Window title (localized)
        title = _("employee_add_dialog_title") if _("employee_add_dialog_title") else _("employee_add_employee")
        self.setWindowTitle(title)

        # If Persian, use Right-to-Left layout direction
        if self.is_fa:
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        self.setModal(True)
        self.resize(480, 380)
        self.init_ui()

    def init_ui(self):
        """Initialize the dialog UI with localized labels and placeholders."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title label (bigger)
        title_label = QLabel(_("employee_add_employee"))
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        if self.is_fa:
            title_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        else:
            title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(title_label)

        form_layout = QFormLayout()
        # Align labels to the right for RTL languages
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # First name
        self.first_name_input = QLineEdit()
        self.first_name_input.setPlaceholderText(_("employee_first_name") or "e.g., Ali")
        form_layout.addRow(f"{_('employee_first_name')}*", self.first_name_input)

        # Last name
        self.last_name_input = QLineEdit()
        self.last_name_input.setPlaceholderText(_("employee_last_name") or "e.g., Rezaei")
        form_layout.addRow(f"{_('employee_last_name')}", self.last_name_input)

        # Email
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText(_("employee_email") or "e.g., ali.rezaei@example.com")
        form_layout.addRow(f"{_('employee_email')}*", self.email_input)

        # Phone
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText(_("employee_phone") or "e.g., +98 21 1234 5678")
        form_layout.addRow(f"{_('employee_phone')}", self.phone_input)

        # Employee ID
        self.employee_id_input = QLineEdit()
        self.employee_id_input.setPlaceholderText(_("employee_id") or "Optional custom ID")
        form_layout.addRow(f"{_('employee_id')}", self.employee_id_input)

        # Monthly leave allowance (spinbox in HOURS)
        self.leave_allowance_input = QSpinBox()
        # reasonable default range (0..240 hours = 0..10 days approx)
        self.leave_allowance_input.setRange(0, 240)
        # Set suffix localized
        suffix = " hours"
        if self.is_fa:
            suffix = " ساعت"
        self.leave_allowance_input.setSuffix(suffix)
        # If key exists for label, use it; else fallback
        leave_label = _("employee_monthly_leave_allowance") if _("employee_monthly_leave_allowance") else _("employee_monthly_leave_allowance") if _("employee_monthly_leave_allowance") else _("Monthly Leave Allowance")
        # If locale doesn't have that key, use a safe default string (localized by simple heuristics)
        # We attempt to build a label that includes '(hours)' in the active language.
        if leave_label in ("employee_monthly_leave_allowance", None):
            # fallback readable label:
            leave_label = _("Monthly Leave Allowance") if not self.is_fa else "سهم مرخصی ماهانه"
        form_layout.addRow(f"{leave_label}:", self.leave_allowance_input)

        # Notes
        self.notes_input = QTextEdit()
        self.notes_input.setMaximumHeight(90)
        form_layout.addRow(f"{_('employee_notes') or 'Notes'}:", self.notes_input)

        layout.addLayout(form_layout)

        # Buttons
        button_layout = QHBoxLayout()
        # Add button text localized
        add_text = _("employee_add_employee") or _("employee_add") or "Add Employee"
        cancel_text = _("cancel") or "Cancel"
        self.add_button = QPushButton(add_text)
        self.add_button.clicked.connect(self.handle_add)
        self.add_button.setDefault(True)

        self.cancel_button = QPushButton(cancel_text)
        self.cancel_button.clicked.connect(self.reject)

        # Place buttons according to direction
        if self.is_fa:
            # In RTL, typically primary button is on the right; keep stretch on left
            button_layout.addStretch()
            button_layout.addWidget(self.cancel_button)
            button_layout.addWidget(self.add_button)
        else:
            button_layout.addStretch()
            button_layout.addWidget(self.add_button)
            button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.first_name_input.setFocus()

    def _show_warning(self, title_key: str, message_key: str):
        """Helper to show localized warning message boxes."""
        title = _(title_key) or _("employee_validation_error") or "Validation Error"
        message = _(message_key) or message_key
        QMessageBox.warning(self, title, message)

    def handle_add(self):
        """Handle the 'Add Employee' button click with validation and localized messages."""
        first_name = self.first_name_input.text().strip()
        last_name = self.last_name_input.text().strip() or None
        email = self.email_input.text().strip().lower()
        phone = self.phone_input.text().strip() or None
        employee_id = self.employee_id_input.text().strip() or None
        notes = self.notes_input.toPlainText().strip() or None

        # Value is provided in hours from the spinbox
        leave_allowance_hours = int(self.leave_allowance_input.value())

        # Validation
        if not first_name:
            self._show_warning("employee_validation_error", "employee_first_name_required")
            self.first_name_input.setFocus()
            return

        if not email:
            self._show_warning("employee_validation_error", "employee_email_required")
            self.email_input.setFocus()
            return

        # Basic email validation
        email_regex = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,}$'
        if not re.match(email_regex, email):
            self._show_warning("employee_validation_error", "employee_invalid_email")
            self.email_input.setFocus()
            return

        # Prepare payload for the rest of the app.
        # Note: The rest of the app may expect monthly_leave_allowance in minutes or hours.
        # The app previously used 'monthly_leave_allowance_hours' in the dialog; keep this key to preserve compatibility.
        employee_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "employee_id": employee_id,
            "notes": notes,
            # Keep hours key (downstream can convert to minutes if needed)
            "monthly_leave_allowance_hours": leave_allowance_hours,
        }

        # Emit the signal for the parent to handle insertion
        try:
            self.employee_added.emit(employee_data)
        except Exception:
            logger.exception("Failed to emit employee_added signal.")
            QMessageBox.critical(self, _("error"), _("error_loading_filter_data") or "Internal error")
