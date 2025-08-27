# src/citrine_attendance/main.py
"""
Main entry point for the Citrine Attendance application.
Handles initialization of core services, database, default user,
and launches the PyQt6 GUI.
"""
import sys
import logging
# Import our internal modules
# Adjust import path if necessary, assuming this file is run as a module
# e.g., `python -m src.citrine_attendance.main`
# Import database first to ensure init_db defines engine/session
from . import database
from .config import config
# Now import engine, SessionLocal, User *after* database module is processed
from .database import engine, SessionLocal, User
from .services.employee_service import employee_service
from .services.user_service import user_service
from .services.attendance_service import attendance_service
# Import security utility
from .utils.security import hash_password
from .locale import translator
from PyQt6.QtCore import Qt


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
    # --- ROBUST CHECK: Ensure the database engine is initialized ---
    # Access the engine directly from the database module namespace
    if not hasattr(database, 'engine') or database.engine is None:
        # Log to root logger as __main__ logger might not be set up in this specific context if called early
        logging.getLogger().error("Database engine is not initialized. Cannot create default admin.")
        print("Error: Database engine is not initialized. Cannot create default admin user.")
        return

    # Use SessionLocal from the database module
    db_session = database.SessionLocal()
    try:
        # Check if any users exist in the database
        user_count = db_session.query(User).count()

        if user_count == 0:
            default_username = "admin"
            default_password = "admin123" # MUST be changed by the user immediately
            # Log to root logger for consistency during startup
            logging.getLogger().warning(
                f"No existing users found. Creating default admin user: "
                f"Username: '{default_username}', Password: '{default_password}'. "
                f"*** CHANGE THIS PASSWORD IMMEDIATELY AFTER FIRST LOGIN ***"
            )
            # --- IMPORTANT: Inform the user on the console as well ---
            print("\n" + "="*60)
            print("SECURITY ALERT: DEFAULT ADMIN USER CREATED!")
            print(f"Username: {default_username}")
            print(f"Password: {default_password}")
            print("*** CHANGE THIS PASSWORD IMMEDIATELY AFTER FIRST LOGIN ***")
            print("="*60 + "\n")

            # Hash the default password securely
            hashed_pw = hash_password(default_password)

            # Create the User object
            admin_user = User(
                username=default_username,
                password_hash=hashed_pw,
                role="admin"
            )
            # Add and commit to the database
            db_session.add(admin_user)
            db_session.commit()
            logging.getLogger().info(f"Default admin user '{default_username}' created successfully.")
        else:
            logging.getLogger().info("Existing users found in the database. Skipping default admin creation.")

    except Exception as e:
        logging.getLogger().error(f"Error during default admin user creation/check: {e}", exc_info=True)
        print(f"Warning: An error occurred while checking/creating the default admin user. See logs for details.")
        # Depending on policy, you might want to exit here if this is critical
        # sys.exit(1)
    finally:
        # Ensure the database session is closed
        db_session.close()


# --- Main Application Entry Point ---
def main():
    """
    Main function to initialize the Citrine Attendance application.
    This includes setting up logging, the database, default user,
    and launches the PyQt6 GUI.
    """
    print("Initializing Citrine Attendance App...")

    # 1. Setup logging first to capture any initialization messages
    setup_logging()
    # Use a specific logger for main
    logger = logging.getLogger(__name__)
    logger.info("Starting Citrine Attendance application.")

    # 2. Initialize the database connection and create tables if they don't exist
    try:
        # Call init_db from the database module to ensure engine is set
        database.init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize the database: {e}", exc_info=True)
        print(f"Critical Error: Could not initialize the database. See logs for details.")
        sys.exit(1) # Exit the application if the database cannot be initialized

    # 3. Create the default admin user if the users table is empty
    # Ensure this runs AFTER database.init_db() has been called
    try:
        create_default_admin()
    except Exception as e:
        logger.error(f"Error ensuring default admin user exists: {e}", exc_info=True)
        print(f"Warning: Could not check or create the default admin user. See logs for details.")
        # Depending on requirements, you might choose to exit here if this step is mandatory
        # sys.exit(1)

    # 4. --- Phase 3: Launch the PyQt6 GUI ---
    logger.info("Initializing PyQt6 GUI...")
    try:
        # Import PyQt6 modules *after* core setup.
        from PyQt6.QtWidgets import QApplication

        # Import the main window class
        from .ui.main_window import MainWindow

        # Ensure only one QApplication instance exists.
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
            logger.debug("Created new QApplication instance.")

        # Set language and layout direction
        translator.set_language(config.settings.get("language", "en"))
        if config.settings.get("language") == "fa":
            app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        # --- Create the Main Application Window ---
        # The MainWindow constructor handles login and showing itself
        window = MainWindow() # This starts the login flow and sets up the UI asynchronously
        # Do NOT call window.show() here anymore.

        logger.info("Main application window initialization started. Starting GUI event loop.")

        # --- Start the Qt Event Loop ---
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


if __name__ == "__main__":
    main()