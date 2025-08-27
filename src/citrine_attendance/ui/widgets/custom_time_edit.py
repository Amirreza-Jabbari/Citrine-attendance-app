# src/citrine_attendance/ui/widgets/custom_time_edit.py
"""A custom QTimeEdit that accepts 4-digit time input."""
from PyQt6.QtWidgets import QTimeEdit, QLineEdit
from PyQt6.QtCore import QTime, Qt
from PyQt6.QtGui import QKeyEvent


class CustomTimeEdit(QTimeEdit):
    """
    A QTimeEdit that allows entering time as a 4-digit string (e.g., '0930')
    and automatically formats it to 'HH:mm'.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDisplayFormat("HH:mm")
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, obj, event):
        """Filter key press events on the line edit."""
        if obj is self.lineEdit() and isinstance(event, QKeyEvent):
            if event.type() == QKeyEvent.Type.KeyPress:
                # On Return/Enter, attempt to format the text
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self.format_text()
                    return True # Event handled
        # Pass the event to the base class
        return super().eventFilter(obj, event)

    def focusOutEvent(self, event):
        """Format the text when the widget loses focus."""
        self.format_text()
        super().focusOutEvent(event)

    def format_text(self):
        """
        Parses the current text in the line edit and formats it as HH:mm.
        """
        line_edit = self.lineEdit()
        text = line_edit.text()

        # Remove any non-digit characters
        digits = ''.join(filter(str.isdigit, text))

        if len(digits) == 4:
            try:
                hour = int(digits[0:2])
                minute = int(digits[2:4])
                
                # Basic validation
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    self.setTime(QTime(hour, minute))
            except (ValueError, IndexError):
                # If parsing fails, do nothing or reset to a default
                pass # Keep the invalid text for user correction
        # If the input is not 4 digits, let the default QTimeEdit handling apply