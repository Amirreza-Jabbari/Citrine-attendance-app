# src/citrine_attendance/ui/widgets/custom_time_edit.py
"""A custom QTimeEdit-like widget with a clear button, using a masked QLineEdit."""

from PyQt6.QtWidgets import QLineEdit, QPushButton, QHBoxLayout, QWidget
from PyQt6.QtCore import QTime, Qt

class CustomTimeEdit(QWidget):
    """
    A custom time input widget that uses a masked QLineEdit to ensure
    Left-to-Right display in all layout directions.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # HEROIC FIX: Force the entire custom widget to LTR to ensure correct layout of its children
        # PyQt6.6+ uses Qt.LayoutDirection.LeftToRight, older versions use Qt.LeftToRight
        try:
            # Try the newer PyQt6 enum style first
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        except (TypeError, AttributeError):
            # Fallback to older PyQt6 style
            try:
                self.setLayoutDirection(Qt.LeftToRight)
            except:
                pass  # If all else fails, use default layout direction
        self.init_ui()

    def init_ui(self):
        """Initializes the UI components of the custom widget."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Use QLineEdit with an input mask. This is the key to fixing the RTL issue.
        self.time_edit = QLineEdit()
        self.time_edit.setInputMask("00:00")
        self.time_edit.setPlaceholderText("HH:MM")
        # HEROIC FIX: Ensure text is aligned left within the QLineEdit - handle enum properly
        try:
            self.time_edit.setAlignment(Qt.AlignmentFlag.AlignLeft)
        except (TypeError, AttributeError):
            try:
                self.time_edit.setAlignment(Qt.AlignLeft)
            except:
                pass  # Use default alignment if all else fails

        # Clear button
        self.clear_button = QPushButton("X")
        self.clear_button.setFixedSize(20, 20)
        self.clear_button.setFlat(True)
        # HEROIC FIX: Set cursor - handle enum properly
        try:
            self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        except (TypeError, AttributeError):
            try:
                self.clear_button.setCursor(Qt.PointingHandCursor)
            except:
                pass  # Use default cursor if all else fails
        self.clear_button.setStyleSheet("font-weight: bold; border: none;")
        self.clear_button.clicked.connect(self.clear)

        layout.addWidget(self.time_edit)
        layout.addWidget(self.clear_button)

    def time(self) -> QTime:
        """
        Returns the current time from the QLineEdit as a QTime object.
        Returns QTime(0,0) if the input is incomplete or invalid.
        """
        try:
            h, m = map(int, self.time_edit.text().split(':'))
            if 0 <= h < 24 and 0 <= m < 60:
                return QTime(h, m)
        except (ValueError, IndexError):
            pass # Return default if text is not a valid time
        return QTime(0, 0)

    def setTime(self, time: QTime):
        """
        Sets the time in the QLineEdit from a QTime object.
        If the time is null (0,0), it clears the line edit.
        """
        if time and time != QTime(0, 0):
            self.time_edit.setText(time.toString("HH:mm"))
        else:
            self.clear()

    def clear(self):
        """Clears the time text."""
        self.time_edit.clear()