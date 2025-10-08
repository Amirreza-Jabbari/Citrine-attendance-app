# src/citrine_attendance/ui/views/settings_view.py
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QComboBox,
    QPushButton, QMessageBox, QSpinBox, QTextEdit, QTabWidget, QGroupBox, QLineEdit,
    QDialog, QDialogButtonBox, QListWidget, QHBoxLayout
)
from PyQt6.QtCore import Qt, QTime, pyqtSignal
from ...config import config
from ...services.user_service import user_service, UserServiceError
from ...database import User, get_db_session
from ...locale import _, translator
import re
from ..widgets.custom_time_edit import CustomTimeEdit

logger = logging.getLogger(__name__)


class SettingsView(QWidget):
    # HEROIC FIX: Signal to notify when language changes
    language_changed = pyqtSignal(str)
    
    def __init__(self, current_user, main_window_ref=None):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.current_user = current_user
        self.main_window = main_window_ref

        # keep a reference to title/save button for retranslation
        self.title_label = None
        self.save_button = None

        # UI placeholders (some widgets created later)
        self.language_combo = None
        self.date_format_combo = None

        self.init_ui()
        self.populate_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        # Title label (kept as attribute so we can retranslate)
        self.title_label = QLabel(_("settings_title"))
        self.title_label.setObjectName("viewTitle")
        main_layout.addWidget(self.title_label)
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, 1)

        # Create tabs (we build them via methods so we can rebuild on language change)
        self.create_general_tab()
        self.create_holidays_tab()
        self.create_backups_tab()
        self.create_users_tab()
        self.create_audit_log_tab()

        # Save button (kept as attribute to update text)
        self.save_button = QPushButton(_("settings_save_button"))
        self.save_button.clicked.connect(self.save_settings)
        main_layout.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignRight)

        # load lists used in admin tabs
        self.load_users_list()
        self.load_audit_log()

    def recreate_tabs_for_language(self, select_language: str | None = None):
        """
        Rebuild all tabs (used when language changes so UI texts update).
        Keep tabs cleared and re-create them in the same order.
        If select_language is provided, set the language combo to that value without emitting signals.
        """
        # Save current tab index to try to preserve selection
        try:
            idx = self.tabs.currentIndex()
        except Exception:
            idx = 0

        # Clear and recreate tabs
        self.tabs.clear()
        self.create_general_tab()
        self.create_holidays_tab()
        self.create_backups_tab()
        self.create_users_tab()
        self.create_audit_log_tab()

        # restore tab index if possible
        try:
            self.tabs.setCurrentIndex(min(idx, self.tabs.count() - 1))
        except Exception:
            pass

        # update title and save button text
        if self.title_label:
            self.title_label.setText(_("settings_title"))
        if self.save_button:
            self.save_button.setText(_("settings_save_button"))

        # Populate other settings
        self._populate_other_settings()

        # Set language combo to provided selection (without re-triggering signal)
        if select_language and self.language_combo is not None:
            try:
                self.language_combo.blockSignals(True)
                idx_lang = self.language_combo.findData(select_language)
                if idx_lang >= 0:
                    self.language_combo.setCurrentIndex(idx_lang)
            finally:
                try:
                    self.language_combo.blockSignals(False)
                except Exception:
                    pass

        self.load_users_list()
        self.load_audit_log()
        # Reload holidays list if tab exists
        try:
            if hasattr(self, "load_holidays"):
                self.load_holidays()
        except Exception:
            pass

    def create_general_tab(self):
        self.general_tab = QWidget()
        general_layout = QFormLayout(self.general_tab)

        self.language_combo = QComboBox()
        # localized labels for languages
        self.language_combo.addItem(_("language_english"), "en")
        self.language_combo.addItem(_("language_persian"), "fa")
        # connect to change handler so UI updates immediately
        # The handler accepts either index (signal) or string (callers)
        self.language_combo.currentIndexChanged.connect(self.on_language_changed)
        general_layout.addRow(_("settings_language"), self.language_combo)

        self.date_format_combo = QComboBox()
        self.date_format_combo.addItem(_("settings_date_format_both"), "both")
        self.date_format_combo.addItem(_("settings_date_format_jalali"), "jalali")
        self.date_format_combo.addItem(_("settings_date_format_gregorian"), "gregorian")
        general_layout.addRow(_("settings_date_format"), self.date_format_combo)

        self.workday_hours_spinbox = QSpinBox()
        self.workday_hours_spinbox.setRange(1, 24)
        general_layout.addRow(_("settings_workday_hours_label"), self.workday_hours_spinbox)

        # --- Launch / Threshold Time Settings ---
        self.launch_start_edit = CustomTimeEdit()
        general_layout.addRow(_("settings_launch_start"), self.launch_start_edit)

        self.launch_end_edit = CustomTimeEdit()
        general_layout.addRow(_("settings_launch_end"), self.launch_end_edit)

        self.late_threshold_edit = CustomTimeEdit()
        general_layout.addRow(_("settings_late_threshold_label"), self.late_threshold_edit)

        self.tabs.addTab(self.general_tab, _("settings_general_tab"))

    def create_backups_tab(self):
        self.backup_tab = QWidget()
        backup_form = QFormLayout(self.backup_tab)
        self.backup_freq_spinbox = QSpinBox()
        self.backup_freq_spinbox.setRange(0, 365)
        backup_form.addRow(_("settings_backup_frequency"), self.backup_freq_spinbox)
        self.backup_retention_spinbox = QSpinBox()
        self.backup_retention_spinbox.setRange(1, 1000)
        backup_form.addRow(_("settings_backup_retention"), self.backup_retention_spinbox)
        self.tabs.addTab(self.backup_tab, _("settings_backups_tab"))

    def create_holidays_tab(self):
        """
        Create Holidays tab. Note: we avoid instantiating JalaliDateEdit eagerly
        (it caused problems while re-creating tabs during language change).
        Instead, Add -> opens a small dialog containing JalaliDateEdit only when needed.
        """
        self.holidays_tab = QWidget()
        layout = QVBoxLayout(self.holidays_tab)

        self.holidays_list = QListWidget()
        layout.addWidget(self.holidays_list)

        row = QHBoxLayout()
        # Do NOT instantiate JalaliDateEdit here. We'll create it lazily inside add_holiday().
        self.holiday_add_btn = QPushButton(_("settings_holiday_add"))
        self.holiday_remove_btn = QPushButton(_("settings_holiday_remove"))
        row.addWidget(self.holiday_add_btn)
        row.addWidget(self.holiday_remove_btn)
        layout.addLayout(row)

        self.holiday_add_btn.clicked.connect(self.add_holiday)
        self.holiday_remove_btn.clicked.connect(self.remove_selected_holiday)

        self.tabs.addTab(self.holidays_tab, _("settings_holidays_tab"))
        # load current holidays
        self.load_holidays()

    def load_holidays(self):
        try:
            raw = config.settings.get('holidays', []) or []
            self.holidays_list.clear()
            for h in raw:
                try:
                    # If string is YYYY-MM-DD treat as gregorian one-off; else MM-DD jalali recurring
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", h):
                        self.holidays_list.addItem(h)
                    else:
                        # Display as Jalali month/day for clarity
                        parts = h.split('-')
                        if len(parts) == 2:
                            mm = int(parts[0])
                            dd = int(parts[1])
                            # Show as MM-DD (Jalali)
                            self.holidays_list.addItem(f"{mm:02d}-{dd:02d}")
                        else:
                            self.holidays_list.addItem(h)
                except Exception:
                    # Skip invalid holiday entries silently
                    pass
        except Exception:
            # HEROIC FIX: Don't use logger.exception to avoid recursion in Python 3.13
            pass

    def add_holiday(self):
        """
        Open a short dialog containing JalaliDateEdit and OK/Cancel.
        We construct JalaliDateEdit only when the user invokes this action
        (avoids jdatetime recursion when re-creating the UI).
        """
        try:
            # Import here to avoid module-level initialization side-effects
            from ..widgets.jalali_date_edit import JalaliDateEdit

            dlg = QDialog(self)
            dlg.setWindowTitle(_("settings_holiday_add"))
            dlg_layout = QVBoxLayout(dlg)

            picker = JalaliDateEdit()
            dlg_layout.addWidget(picker)

            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            dlg_layout.addWidget(buttons)

            def on_accept():
                try:
                    qd = picker.date()
                    pydate = qd.toPyDate()
                    import jdatetime
                    jdate = jdatetime.date.fromgregorian(date=pydate)
                    mmdd = f"{jdate.month:02d}-{jdate.day:02d}"
                    holidays = config.settings.get('holidays', []) or []
                    if mmdd in holidays:
                        QMessageBox.information(self, _("settings_holiday_add"), _("settings_holiday_already_exists"))
                        dlg.reject()
                        return
                    holidays.append(mmdd)
                    config.update_setting('holidays', holidays)
                    self.load_holidays()
                    dlg.accept()
                except Exception as e:
                    QMessageBox.critical(self, _("error"), str(e))
                    dlg.reject()

            buttons.accepted.connect(on_accept)
            buttons.rejected.connect(dlg.reject)

            dlg.exec()
        except Exception as e:
            logger.exception("Failed to open holiday picker: %s", str(e))
            QMessageBox.critical(self, _("error"), str(e))

    def remove_selected_holiday(self):
        try:
            sel = self.holidays_list.currentItem()
            if not sel:
                return
            txt = sel.text()
            holidays = config.settings.get('holidays', []) or []
            if txt in holidays:
                holidays.remove(txt)
            else:
                cleaned = txt
                if cleaned in holidays:
                    holidays.remove(cleaned)
            config.update_setting('holidays', holidays)
            self.load_holidays()
        except Exception as e:
            logger.exception("Failed to remove holiday: %s", str(e))
            QMessageBox.critical(self, _("error"), str(e))

    def create_users_tab(self):
        self.users_tab = QWidget()
        users_layout = QVBoxLayout(self.users_tab)
        add_user_group = QGroupBox(_("settings_add_user_group"))
        add_user_layout = QFormLayout(add_user_group)
        self.new_username_edit = QLineEdit()
        add_user_layout.addRow(_("settings_new_username"), self.new_username_edit)
        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        add_user_layout.addRow(_("settings_new_password"), self.new_password_edit)
        self.new_role_combo = QComboBox()
        self.new_role_combo.addItems(["Operator", "Admin"])
        self.new_role_combo.setItemData(0, "operator")
        self.new_role_combo.setItemData(1, "admin")
        add_user_layout.addRow(_("settings_new_role"), self.new_role_combo)
        self.add_user_button = QPushButton(_("settings_add_user_button"))
        self.add_user_button.clicked.connect(self.add_new_user)
        add_user_layout.addRow(self.add_user_button)
        existing_users_group = QGroupBox(_("settings_existing_users"))
        existing_users_layout = QVBoxLayout(existing_users_group)
        self.users_list_text = QTextEdit()
        self.users_list_text.setReadOnly(True)
        self.refresh_users_button = QPushButton(_("settings_refresh_user_list"))
        self.refresh_users_button.clicked.connect(self.load_users_list)
        existing_users_layout.addWidget(self.users_list_text, 1)
        existing_users_layout.addWidget(self.refresh_users_button)
        users_layout.addWidget(add_user_group)
        users_layout.addWidget(existing_users_group)
        self.tabs.addTab(self.users_tab, _("settings_users_tab"))

    def create_audit_log_tab(self):
        self.audit_tab = QWidget()
        audit_layout = QVBoxLayout(self.audit_tab)
        audit_layout.addWidget(QLabel(_("settings_audit_log_header")))
        self.audit_log_text = QTextEdit()
        self.audit_log_text.setReadOnly(True)
        audit_layout.addWidget(self.audit_log_text, 1)
        self.refresh_audit_button = QPushButton(_("settings_refresh_audit_log"))
        self.refresh_audit_button.clicked.connect(self.load_audit_log)
        audit_layout.addWidget(self.refresh_audit_button)
        self.tabs.addTab(self.audit_tab, _("settings_audit_log_tab"))

    def populate_settings(self):
        """
        Load saved settings into the UI.
        When setting combo current index programmatically we block signals to avoid
        triggering on_language_changed unintentionally.
        """
        settings = config.settings or {}
        # set translator language before setting UI indexes so _() calls return correct text
        lang = settings.get("language", "en")
        translator.set_language(lang)

        # set current indexes for combos (language and date format)
        try:
            if self.language_combo is not None:
                self.language_combo.blockSignals(True)
                self.language_combo.setCurrentIndex(self.language_combo.findData(settings.get("language", "en")))
                self.language_combo.blockSignals(False)
        except Exception:
            pass

        self._populate_other_settings()

    def populate_settings_after_language_change(self, current_language):
        """HEROIC FIX: Populate settings after language change without blocking language combo signals."""
        settings = config.settings or {}
        
        # Set language combo WITHOUT blocking signals - this is crucial!
        try:
            if self.language_combo is not None:
                # Don't block signals - we want the combo to remain interactive
                idx = self.language_combo.findData(current_language)
                if idx >= 0:
                    self.language_combo.setCurrentIndex(idx)
        except Exception:
            pass

        self._populate_other_settings()

    def _populate_other_settings(self):
        """HEROIC FIX: Helper to populate non-language settings."""
        settings = config.settings or {}

        try:
            if self.date_format_combo is not None:
                self.date_format_combo.setCurrentIndex(self.date_format_combo.findData(settings.get("date_format", "both")))
        except Exception:
            pass

        try:
            self.workday_hours_spinbox.setValue(settings.get("workday_hours", 8))
            self.launch_start_edit.setTime(QTime.fromString(settings.get("default_launch_start_time", "12:30"), "HH:mm"))
            self.launch_end_edit.setTime(QTime.fromString(settings.get("default_launch_end_time", "13:30"), "HH:mm"))
            self.late_threshold_edit.setTime(QTime.fromString(settings.get("late_threshold_time", "10:00"), "HH:mm"))
            self.backup_freq_spinbox.setValue(settings.get("backup_frequency_days", 1))
            self.backup_retention_spinbox.setValue(settings.get("backup_retention_count", 10))
        except Exception:
            pass

        # Update header and button labels now that translator language is set
        if self.title_label:
            self.title_label.setText(_("settings_title"))
        if self.save_button:
            self.save_button.setText(_("settings_save_button"))

    def save_settings(self):
        try:
            # Save language selection and update translator
            chosen_lang = self.language_combo.currentData()
            config.update_setting("language", chosen_lang)
            translator.set_language(chosen_lang)

            config.update_setting("date_format", self.date_format_combo.currentData())
            config.update_setting("workday_hours", self.workday_hours_spinbox.value())

            # Ensure the saved time strings use ASCII digits only (normalize)
            def _normalize_time_str_for_save(qtime):
                s = qtime.toString("HH:mm")
                trans_table = str.maketrans({
                    '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4', '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
                    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4', '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
                })
                return s.translate(trans_table)

            start_s = _normalize_time_str_for_save(self.launch_start_edit.time())
            end_s = _normalize_time_str_for_save(self.launch_end_edit.time())
            config.update_setting("default_launch_start_time", start_s)
            config.update_setting("default_launch_end_time", end_s)

            config.update_setting("late_threshold_time", self.late_threshold_edit.time().toString("HH:mm"))
            config.update_setting("backup_frequency_days", self.backup_freq_spinbox.value())
            config.update_setting("backup_retention_count", self.backup_retention_spinbox.value())

            QMessageBox.information(self, "Settings Saved", _("settings_saved_message"))

            # Some settings may require restart; prompt and close main window if user agrees
            if QMessageBox.question(self, _("settings_restart_required_title"), _("settings_restart_required_message")) == QMessageBox.StandardButton.Yes:
                if self.main_window:
                    self.main_window.close()
        except Exception as e:
            logger.exception("Failed saving settings: %s", str(e))
            QMessageBox.critical(self, _("settings_save_error"), str(e))

    def on_language_changed(self, index_or_value):
        """
        Called when the language combobox changes. It accepts either an index (from signal)
        or a direct value if invoked programmatically. We set translator language and rebuild tabs.
        """
        try:
            # if signal provided an index, map to data
            if isinstance(index_or_value, int):
                lang = self.language_combo.itemData(index_or_value)
            else:
                # assume it's the language code
                lang = index_or_value

            if not lang:
                lang = "en"

            # set translator language immediately
            translator.set_language(lang)

            # Recreate tabs so all labels/controls pick up new translations
            self.recreate_tabs_for_language(select_language=lang)

            # HEROIC FIX: Emit signal to update main window and all views
            self.language_changed.emit(lang)

            # Also persist choice to config (but do not trigger the restart flow now)
            config.update_setting("language", lang)
        except Exception as e:
            # HEROIC FIX: Don't use logger.exception to avoid recursion in Python 3.13
            # Just log the error message without stack trace
            try:
                logger.error(f"Failed to change language: {e}")
            except:
                pass  # If logging fails, silently continue

    # Other methods (add_new_user, load_users_list, load_audit_log) remain the same...
    def add_new_user(self):
        if self.current_user.role != "admin":
            QMessageBox.warning(self, _("settings_access_denied"), _("settings_only_admins_add_users"))
            return
        username = self.new_username_edit.text().strip()
        password = self.new_password_edit.text()
        role = self.new_role_combo.currentData()
        if not username or not password:
            QMessageBox.warning(self, _("settings_input_error"), _("settings_username_password_required"))
            return
        try:
            user_service.create_user(username, password, role)
            QMessageBox.information(self, _("success"), _("settings_user_created_success").format(username=username))
            self.new_username_edit.clear()
            self.new_password_edit.clear()
            self.load_users_list()
        except UserServiceError as e:
            QMessageBox.critical(self, _("error"), str(e))

    def load_users_list(self):
        if self.current_user.role != "admin":
            try:
                self.tabs.setTabEnabled(self.tabs.indexOf(self.users_tab), False)
            except Exception:
                pass
            return
        db = next(get_db_session())
        try:
            users = db.query(User).all()
            self.users_list_text.setPlainText("\n".join([f"{user.username} ({user.role})" for user in users]))
        finally:
            db.close()

    def load_audit_log(self):
        if self.current_user.role != "admin":
            try:
                self.tabs.setTabEnabled(self.tabs.indexOf(self.audit_tab), False)
            except Exception:
                pass
            return
        from ...database import AuditLog
        db = next(get_db_session())
        try:
            entries = db.query(AuditLog).order_by(AuditLog.performed_at.desc()).limit(100).all()
            self.audit_log_text.setPlainText("\n".join([f"{e.performed_at} | {e.performed_by} | {e.action} on {e.table_name}:{e.record_id}" for e in entries]))
        finally:
            db.close()
