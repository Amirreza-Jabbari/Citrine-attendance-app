# src/citrine_attendance/ui/widgets/jalali_date_edit.py
from PyQt6.QtWidgets import (
    QWidget, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout, QLabel,
    QGridLayout, QFrame, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QDate, QRect, QPoint
from PyQt6.QtGui import QIcon
import jdatetime
import datetime
import re
from ...config import config
from ...date_utils import is_holiday


PERSIAN_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"
]

# Saturday ... Friday short names (display right-to-left)
PERSIAN_WEEKDAYS = ["ش", "ی", "د", "س", "چ", "پ", "ج"]

# Persian digits map and reverse map
_PERSIAN_DIGITS = {str(i): ch for i, ch in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_LATIN_FROM_PERSIAN = {v: k for k, v in _PERSIAN_DIGITS.items()}

def to_persian_digits(s: str) -> str:
    return "".join(_PERSIAN_DIGITS.get(ch, ch) for ch in s)

def persian_to_latin(s: str) -> str:
    return "".join(_LATIN_FROM_PERSIAN.get(ch, ch) for ch in s)

def jdate_from_qdate(qd: QDate) -> jdatetime.date:
    # QDate -> python date -> jdatetime.date
    try:
        pydate = qd.toPyDate()
    except Exception:
        # fallback for older/newer bindings
        pydate = datetime.date(qd.year(), qd.month(), qd.day())
    return jdatetime.date.fromgregorian(date=pydate)

def _is_jalali_leap(year: int) -> bool:
    """
    Jalali leap-year check using 33-year cycle residues:
    Leap years in cycle residues: 1,5,9,13,17,22,26,30
    (fallback; jdatetime also has isleap but keep a safe local method)
    """
    try:
        y = int(year)
    except Exception:
        return False
    return (y % 33) in (1, 5, 9, 13, 17, 22, 26, 30)

class PopupJalaliCalendar(QFrame):
    """Styled popup calendar showing a Jalali month with RTL layout,
       Saturday..Friday mapped right-to-left visually.
       Callback gets a python datetime.date (gregorian).
    """
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        # ensure popup respects RTL visually
        try:
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        except Exception:
            pass
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("jalaliPopup")

        self.setStyleSheet("""
        QFrame#jalaliPopup {
            background: #ffffff;
            border: 1px solid #cfd8dc;
            border-radius: 8px;
            padding: 8px;
        }
        QLabel#monthLabel {
            font-weight: 700;
            color: #1f3a57;
            font-size: 12pt;
        }
        QLabel[class="weekday"] {
            color: #1f7ae0;
            min-width: 36px;
            font-weight: bold;
        }
        QPushButton[role="nav"] {
            background: #1f7ae0;
            color: white;
            border: none;
            border-radius: 6px;
            min-width: 28px;
            min-height: 28px;
            padding: 0;
            font-weight: bold;
        }
        QPushButton[role="nav"]:hover { background: #185fb8; }
        QPushButton[role="day"] {
            background: transparent;
            border: none;
            min-width: 36px;
            min-height: 32px;
            border-radius: 6px;
            color: #1c2430;
        }
        QPushButton[role="day"]:hover { background: #e9f4ff; }
        QPushButton[role="day"][selected="true"] {
            background: #2f98ff;
            color: #ffffff;
            font-weight: 700;
        }
        QPushButton[role="day"][holiday="true"] {
            background: transparent;
            color: #b71c1c; /* red text for holidays */
            font-weight: 700;
        }
        QPushButton[role="day"][holiday="true"]:hover { background: #ffecec; }
        """)

        self.vbox = QVBoxLayout(self)
        self.vbox.setSpacing(8)

        # header: nav buttons + month label
        header = QHBoxLayout()
        header.setSpacing(6)
        # For RTL layout the order is visually handled by layout direction
        self.btn_next = QPushButton("▶")
        self.btn_next.setProperty("role", "nav")
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setProperty("role", "nav")
        self.lbl_month = QLabel("")
        self.lbl_month.setObjectName("monthLabel")
        self.lbl_month.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.btn_next)
        header.addWidget(self.lbl_month, 1)
        header.addWidget(self.btn_prev)
        self.vbox.addLayout(header)

        # weekday header (Saturday .. Friday)
        weekday_layout = QHBoxLayout()
        weekday_layout.setSpacing(4)
        # ensure weekday header respects RTL visually (container has RTL)
        for wd in PERSIAN_WEEKDAYS:
            lbl = QLabel(wd)
            lbl.setProperty("class", "weekday")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedWidth(36)
            weekday_layout.addWidget(lbl)
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)
        self.vbox.addLayout(weekday_layout)

        # grid of day buttons (6 rows x 7 columns)
        self.grid = QGridLayout()
        self.grid.setSpacing(6)
        self.day_buttons = []
        for r in range(6):
            row = []
            for c in range(7):
                b = QPushButton("")
                b.setProperty("role", "day")
                b.setProperty("selected", "false")
                b.setProperty("holiday", "false")
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(self._on_day_clicked)
                b.setObjectName(f"dayBtn_{r}_{c}")
                self.grid.addWidget(b, r, c)
                row.append(b)
            self.day_buttons.append(row)
        self.vbox.addLayout(self.grid)

        # state
        self._on_date_selected = None
        self._current_jyear = None
        self._current_jmonth = None

        self.btn_prev.clicked.connect(self._go_prev_month)
        self.btn_next.clicked.connect(self._go_next_month)

    def open_for(self, jdate: jdatetime.date, on_date_selected):
        """Open popup for a given jdatetime.date and supply a callback:
           on_date_selected(gregorian_date: datetime.date)
           Also highlights the provided day in the month (if applicable).
        """
        self._on_date_selected = on_date_selected
        self._current_jyear = jdate.year
        self._current_jmonth = jdate.month
        self._refresh()
        # if jdate provided has a day in this month, highlight it
        try:
            sel_day = int(jdate.day)
            self._mark_selected_day(sel_day)
        except Exception:
            pass
        self.adjustSize()
        self.show()
        self.raise_()
        self.activateWindow()

    def _go_prev_month(self):
        if self._current_jmonth == 1:
            self._current_jmonth = 12
            self._current_jyear -= 1
        else:
            self._current_jmonth -= 1
        self._refresh()

    def _go_next_month(self):
        if self._current_jmonth == 12:
            self._current_jmonth = 1
            self._current_jyear += 1
        else:
            self._current_jmonth += 1
        self._refresh()

    def _refresh(self):
        """Render the month: set day labels, enabled state, and holiday property for each day."""
        # first day of this jalali month -> convert to gregorian to compute weekday
        first_j = jdatetime.date(self._current_jyear, self._current_jmonth, 1)
        gfirst = first_j.togregorian()
        py_weekday = gfirst.weekday()  # Mon=0..Sun=6
        # convert to index where Saturday=0, Sunday=1, Monday=2, ..., Friday=6
        start_index = (py_weekday + 2) % 7

        # days in jalali month:
        if self._current_jmonth <= 6:
            days_in_month = 31
        elif self._current_jmonth <= 11:
            days_in_month = 30
        else:
            # use jdatetime's isleap if available, else fallback
            try:
                days_in_month = 30 if jdatetime.isleap(self._current_jyear) else 29
            except Exception:
                days_in_month = 30 if _is_jalali_leap(self._current_jyear) else 29

        # set month label (Persian month name + persian digits for year)
        self.lbl_month.setText(f"{PERSIAN_MONTHS[self._current_jmonth - 1]} {to_persian_digits(str(self._current_jyear))}")

        # Clear all buttons first
        for r in range(6):
            for c in range(7):
                btn = self.day_buttons[r][c]
                btn.setText("")
                btn.setProperty("jalali_day", None)
                btn.setProperty("selected", "false")
                btn.setProperty("holiday", "false")
                btn.setEnabled(False)
                btn.setToolTip("")
                btn.hide()
                # re-polish so stylesheet updates are applied
                try:
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)
                except Exception:
                    pass

        # Fill buttons: compute holiday property for each day
        for day in range(1, days_in_month + 1):
            idx = start_index + (day - 1)
            row = idx // 7
            week_day_index = idx % 7  # 0..6 where 0=Saturday
            col = week_day_index   # align column with weekday header
            if 0 <= row < 6 and 0 <= col < 7:
                btn = self.day_buttons[row][col]
                btn.setText(to_persian_digits(str(day)))
                btn.setProperty("jalali_day", day)
                btn.setEnabled(True)
                btn.show()

                # compute corresponding gregorian date for holiday check
                try:
                    jd_day = jdatetime.date(self._current_jyear, self._current_jmonth, day)
                    gdate = jd_day.togregorian()
                    # Use the app config and is_holiday util
                    holiday_flag = False
                    try:
                        holiday_flag = is_holiday(gdate, config.settings if hasattr(config, 'settings') else None)
                    except Exception:
                        # fallback: don't mark holiday if helper throws
                        holiday_flag = False

                    btn.setProperty("holiday", "true" if holiday_flag else "false")
                    if holiday_flag:
                        # helpful tooltip showing exact Gregorian iso so you can confirm
                        btn.setToolTip(gdate.isoformat())
                    else:
                        btn.setToolTip("")

                except Exception:
                    # If anything fails, ensure holiday property is reset
                    btn.setProperty("holiday", "false")
                    btn.setToolTip("")

                # apply style updates
                try:
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)
                except Exception:
                    pass

    def _on_day_clicked(self):
        b = self.sender()
        day = b.property("jalali_day")
        if not day:
            return
        # current month/year -> build jalali date and convert
        jd = jdatetime.date(self._current_jyear, self._current_jmonth, int(day))
        gdate = jd.togregorian()
        if callable(self._on_date_selected):
            try:
                self._on_date_selected(gdate)
            except Exception:
                # swallow exceptions from callback to avoid breaking widget
                pass
        # visually mark selected
        self._mark_selected_day(day)

    def _mark_selected_day(self, day_num):
        for r in range(6):
            for c in range(7):
                btn = self.day_buttons[r][c]
                d = btn.property("jalali_day")
                if d:
                    selected = (int(d) == int(day_num))
                    btn.setProperty("selected", "true" if selected else "false")
                    try:
                        btn.style().unpolish(btn)
                        btn.style().polish(btn)
                    except Exception:
                        pass

class JalaliDateEdit(QWidget):
    """Composite widget: editable line + popup Jalali calendar.

    API:
      - date() -> QDate (Gregorian)
      - setDate(QDate)  # accepts QDate and updates UI (shows Jalali visually)
      - dateChanged(QDate) signal
    """
    dateChanged = pyqtSignal(QDate)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Visual layout direction: RTL
        try:
            self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        except Exception:
            pass

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.line = QLineEdit()
        self.line.setPlaceholderText("yyyy/mm/dd")
        self.line.setReadOnly(False)
        self.line.setClearButtonEnabled(True)
        self.btn = QPushButton()
        try:
            self.btn.setIcon(QIcon.fromTheme("calendar"))
        except Exception:
            self.btn.setText("📅")
        self.btn.setFixedWidth(32)
        h.addWidget(self.line)
        h.addWidget(self.btn)

        self._popup = PopupJalaliCalendar(self)
        try:
            self._popup.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        except Exception:
            pass

        self._selected_qdate = QDate.currentDate()
        # set initial text & keep consistent
        self.setDate(self._selected_qdate)

        # connections
        self.btn.clicked.connect(self._open_popup)
        self.line.returnPressed.connect(self._on_line_enter)

    def _on_line_enter(self):
        text = self.line.text().strip()
        if not text:
            return
        text = persian_to_latin(text)
        # accept formats like yyyy/mm/dd or yy/mm/dd or yyyymmdd
        m = re.match(r"^(\d{2,4})[^\d]*(\d{1,2})[^\d]*(\d{1,2})$", text)
        if not m:
            m = re.match(r"^(\d{4})(\d{2})(\d{2})$", text)
        if not m:
            # invalid entry -> revert to current selected date
            self.setDate(self._selected_qdate)
            return
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # heuristics: if year is in Jalali range (12xx..16xx) interpret as Jalali
        if 1200 <= y <= 1600:
            try:
                jd = jdatetime.date(y, mo, d)
                g = jd.togregorian()
                qd = QDate(g.year, g.month, g.day)
                self.setDate(qd)
                # emit change
                self.dateChanged.emit(self._selected_qdate)
            except Exception:
                self.setDate(self._selected_qdate)
        else:
            # treat as Gregorian
            qd = QDate(y, mo, d)
            if qd.isValid():
                self.setDate(qd)
                self.dateChanged.emit(self._selected_qdate)
            else:
                self.setDate(self._selected_qdate)

    def _open_popup(self):
        current_j = jdate_from_qdate(self._selected_qdate)
        def on_selected(gdate: datetime.date):
            qd = QDate(gdate.year, gdate.month, gdate.day)
            self.setDate(qd)
            # mark selected day in popup visually in case popup remains briefly
            try:
                jd = jdatetime.date.fromgregorian(date=gdate)
                self._popup._mark_selected_day(jd.day)
            except Exception:
                pass
            # consistent signal
            self.dateChanged.emit(self._selected_qdate)

        # open popup and position intelligently
        self._popup.open_for(current_j, on_selected)
        # position: prefer below; but keep inside screen bounds
        global_pos = self.mapToGlobal(self.rect().bottomLeft())
        popup_geo = QRect(global_pos, self._popup.sizeHint())
        screen_geo = QApplication.primaryScreen().availableGeometry()
        # if popup would overflow to the right/bottom, adjust
        if popup_geo.right() > screen_geo.right():
            global_pos.setX(max(screen_geo.right() - popup_geo.width(), screen_geo.left()))
        if popup_geo.bottom() > screen_geo.bottom():
            # open above widget if not enough space below
            global_pos = self.mapToGlobal(self.rect().topLeft() - QPoint(0, self._popup.sizeHint().height()))
        self._popup.move(global_pos)

    def setDate(self, qdate: QDate):
        """Set the internal date and update visual (Jalali) representation."""
        if not isinstance(qdate, QDate) or not qdate.isValid():
            return
        self._selected_qdate = qdate
        # convert to jalali for display
        jd = jdate_from_qdate(qdate)
        display = f"{to_persian_digits(str(jd.year))}/{to_persian_digits(str(jd.month).zfill(2))}/{to_persian_digits(str(jd.day).zfill(2))}"
        self.line.setText(display)
        # ensure popup will show same selection when opened (emit signal for listeners)
        self.dateChanged.emit(self._selected_qdate)

    def date(self) -> QDate:
        return self._selected_qdate

    def setDateFromPyDate(self, pydate: datetime.date):
        self.setDate(QDate(pydate.year, pydate.month, pydate.day))

if __name__ == '__main__':
    # simple manual test
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = JalaliDateEdit()
    w.show()
    sys.exit(app.exec())
