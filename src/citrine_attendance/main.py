# src/citrine_attendance/main.py
"""
Main entry point for the Citrine Attendance application.
Handles initialization of core services, database, default user,
and launches the PyQt6 GUI.
"""
import sys
import logging
from PyQt6.QtCore import Qt

# --- CORRECTED: Use absolute imports from the package root ---
from citrine_attendance import database
from citrine_attendance.config import config
from citrine_attendance.database import engine, SessionLocal, User
from citrine_attendance.services.employee_service import employee_service
from citrine_attendance.services.user_service import user_service
from citrine_attendance.services.attendance_service import attendance_service
from citrine_attendance.utils.security import hash_password
from citrine_attendance.locale import translator

# --- Logging Setup ---
def setup_logging():
    """Configure application logging to file and console."""
    try:
        # Ensure the logs directory exists within the user data directory
        log_dir = config.user_data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file_path = log_dir / "app.log"

        # Configure the root logger
        logging.basicConfig(
            level=logging.INFO, # Set to DEBUG for more verbose output during development
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file_path, encoding='utf-8'),
                logging.StreamHandler(sys.stdout) # Also print to console
            ]
        )
        logging.info("Logging system initialized. Log file: %s", log_file_path)
    except Exception as e:
        # If logging setup fails, print to console and exit
        print(f"Critical Error: Failed to setup logging: {e}")
        sys.exit(1)


# --- Default User Creation ---
def create_default_admin():
    """
    Creates a default 'admin' user with password 'admin123' if no users exist.
    This should only run on the very first startup.
    """
    if not hasattr(database, 'engine') or database.engine is None:
        logging.getLogger().error("Database engine is not initialized. Cannot create default admin.")
        print("Error: Database engine is not initialized. Cannot create default admin user.")
        return

    db_session = database.SessionLocal()
    try:
        user_count = db_session.query(User).count()

        if user_count == 0:
            default_username = "admin"
            default_password = "admin123"
            logging.getLogger().warning(
                f"No existing users found. Creating default admin user: "
                f"Username: '{default_username}', Password: '{default_password}'. "
                f"*** CHANGE THIS PASSWORD IMMEDIATELY AFTER FIRST LOGIN ***"
            )
            print("\n" + "="*60)
            print("SECURITY ALERT: DEFAULT ADMIN USER CREATED!")
            print(f"Username: {default_username}")
            print(f"Password: {default_password}")
            print("*** CHANGE THIS PASSWORD IMMEDIATELY AFTER FIRST LOGIN ***")
            print("="*60 + "\n")

            hashed_pw = hash_password(default_password)
            admin_user = User(
                username=default_username,
                password_hash=hashed_pw,
                role="admin"
            )
            db_session.add(admin_user)
            db_session.commit()
            logging.getLogger().info(f"Default admin user '{default_username}' created successfully.")
        else:
            logging.getLogger().info("Existing users found in the database. Skipping default admin creation.")

    except Exception as e:
        logging.getLogger().error(f"Error during default admin user creation/check: {e}", exc_info=True)
        print(f"Warning: An error occurred while checking/creating the default admin user. See logs for details.")
    finally:
        db_session.close()


# --- Main Application Entry Point ---
def main():
    """
    Main function to initialize the Citrine Attendance application.
    """
    print("Initializing Zarsaham Attendance App...")

    # 1. Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Zarsaham Attendance application.")

    # 2. Initialize the database
    try:
        database.init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize the database: {e}", exc_info=True)
        print(f"Critical Error: Could not initialize the database. See logs for details.")
        sys.exit(1)

    # 3. Create the default admin user if needed
    try:
        create_default_admin()
    except Exception as e:
        logger.error(f"Error ensuring default admin user exists: {e}", exc_info=True)
        print(f"Warning: Could not check or create the default admin user. See logs for details.")

    # 4. Launch the PyQt6 GUI
    logger.info("Initializing PyQt6 GUI...")
    try:
        from PyQt6.QtWidgets import QApplication
        # --- CORRECTED: Use absolute import for MainWindow ---
        from citrine_attendance.ui.main_window import MainWindow

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
            logger.debug("Created new QApplication instance.")

        translator.set_language(config.settings.get("language", "en"))
        if config.settings.get("language") == "fa":
            app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        
        # The MainWindow constructor handles the entire application flow
        window = MainWindow() 

        logger.info("Main application window initialization started. Starting GUI event loop.")
        exit_code = app.exec()
        logger.info(f"GUI event loop finished with exit code: {exit_code}")
        sys.exit(exit_code)

    except ImportError as e:
        logger.critical(f"Failed to import PyQt6 modules: {e}", exc_info=True)
        print(f"Critical Error: Required GUI libraries (PyQt6) are missing or not installed correctly.")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected error occurred during GUI initialization or execution: {e}", exc_info=True)
        print(f"Critical Error: Failed to start or run the application GUI. See logs for details.")
        sys.exit(1)

# This check is now mainly for direct testing of this file,
# but the application should be started via run.py
if __name__ == "__main__":
    main()
