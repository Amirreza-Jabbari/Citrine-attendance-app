# src/citrine_attendance/config.py
import os
import appdirs
import json
import logging
from pathlib import Path

# --- Application Metadata ---
APP_NAME = "ZarsahamAttendance"
APP_AUTHOR = "Zarsaham" # Or your name/company

# --- Default Settings ---
DEFAULT_SETTINGS = {
    "language": "en", # 'en' or 'fa'
    "date_format": "both", # 'jalali', 'gregorian', 'both'
    "backup_frequency_days": 1, # Daily
    "backup_retention_count": 10, # Keep last 10 backups
    "db_path_override": None, # Use default if None
    "enable_backup_encryption": False,
    "default_launch_start_time": "14:30", # Default launch start time
    "default_launch_end_time": "16:30",   # Default launch end time
    "workday_hours": 8,
    "late_threshold_time": "10:00",
}

class AppConfig:
    def __init__(self):
        self.app_dirs = appdirs.AppDirs(APP_NAME, APP_AUTHOR)
        self.user_data_dir = Path(self.app_dirs.user_data_dir)
        self.ensure_directories_exist()
        self.settings_file = self.user_data_dir / "settings.json"
        self.load_settings()

    def ensure_directories_exist(self):
        """Create necessary directories if they don't exist."""
        directories = [
            self.user_data_dir,
            self.user_data_dir / "backups",
            self.user_data_dir / "logs"
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(directory, 0o700)
            except Exception as e:
                logging.warning(f"Could not set permissions on {directory}: {e}")

    def get_db_path(self):
        """Get the path to the SQLite database file."""
        if self.settings.get("db_path_override"):
            return Path(self.settings["db_path_override"])
        return self.user_data_dir / "attendance.db"

    def load_settings(self):
        """Load settings from file, or use defaults."""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    self.settings = {**DEFAULT_SETTINGS, **loaded_settings}
            except (json.JSONDecodeError, IOError) as e:
                logging.error(f"Error loading settings: {e}. Using defaults.")
                self.settings = DEFAULT_SETTINGS.copy()
        else:
            self.settings = DEFAULT_SETTINGS.copy()
            self.save_settings()

    def save_settings(self):
        """Save current settings to file."""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
        except IOError as e:
            logging.error(f"Error saving settings: {e}")

    def update_setting(self, key, value):
        """Update a setting and save."""
        if key in self.settings or key in DEFAULT_SETTINGS:
            self.settings[key] = value
            self.save_settings()
        else:
            logging.warning(f"Attempted to update unknown setting key: {key}")


# Global config instance
config = AppConfig()