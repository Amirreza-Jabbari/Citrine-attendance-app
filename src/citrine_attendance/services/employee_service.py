# src/citrine_attendance/services/employee_service.py
import logging
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ..database import Employee, get_db_session
from ..database import init_db, engine, SessionLocal, User
import csv
from pathlib import Path


class EmployeeServiceError(Exception):
    """Base exception for employee service errors."""
    pass

class EmployeeNotFoundError(EmployeeServiceError):
    """Raised when an employee is not found."""
    pass

class EmployeeAlreadyExistsError(EmployeeServiceError):
    """Raised when trying to create an employee that already exists (e.g., duplicate email)."""
    pass

class EmployeeService:
    """Service class to handle employee-related business logic."""

    def __init__(self):
        # This service will get sessions from the generator when needed
        pass

    def _get_session(self) -> Session:
        """Helper to get a database session."""
        # get_db_session is a generator, so we need to get the first (and only) item
        session_gen = get_db_session()
        return next(session_gen)

    def get_all_employees(self, db: Session = None) -> List[Employee]:
        """Retrieve all employees."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            employees = db.query(Employee).order_by(Employee.first_name, Employee.last_name).all()
            return employees
        finally:
            if managed_session:
                db.close()

    def get_employee_by_id(self, employee_id: int, db: Session = None) -> Optional[Employee]:
        """Retrieve an employee by their database ID."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            employee = db.query(Employee).filter(Employee.id == employee_id).first()
            return employee
        finally:
            if managed_session:
                db.close()

    def get_employee_by_email(self, email: str, db: Session = None) -> Optional[Employee]:
        """Retrieve an employee by their email."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            employee = db.query(Employee).filter(Employee.email == email).first()
            return employee
        finally:
            if managed_session:
                db.close()

    def create_employee(self, first_name: str, email: str, last_name: str = None,
                        phone: str = None, notes: str = None,
                        employee_id: str = None, db: Session = None) -> Employee:
        """Create a new employee."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            # Basic validation (can be expanded)
            if not first_name or not email:
                raise ValueError("First name and email are required.")

            # Check for existing employee with same email
            existing = self.get_employee_by_email(email, db)
            if existing:
                raise EmployeeAlreadyExistsError(f"Employee with email '{email}' already exists.")

            new_employee = Employee(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                notes=notes,
                employee_id=employee_id
            )
            db.add(new_employee)
            db.commit()
            db.refresh(new_employee) # Get the ID after commit
            logging.info(f"Created new employee: {new_employee.first_name} {new_employee.last_name} ({new_employee.email})")
            return new_employee
        except IntegrityError as e:
            db.rollback()
            # This might catch other unique constraint violations too
            logging.error(f"Integrity error creating employee: {e}")
            raise EmployeeAlreadyExistsError(f"Employee creation failed due to a conflict (e.g., duplicate email).") from e
        except Exception as e:
            db.rollback()
            logging.error(f"Error creating employee: {e}")
            raise EmployeeServiceError(f"Failed to create employee: {e}") from e
        finally:
            if managed_session:
                db.close()

    def update_employee(self, employee_id: int, first_name: str = None, email: str = None,
                        last_name: str = None, phone: str = None, notes: str = None,
                        employee_id_field: str = None, db: Session = None) -> Employee:
        """Update an existing employee."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
             # Basic validation
            if not first_name and not email and not last_name and not phone and not notes and not employee_id_field:
                 raise ValueError("At least one field must be provided for update.")

            employee = self.get_employee_by_id(employee_id, db)
            if not employee:
                raise EmployeeNotFoundError(f"Employee with ID {employee_id} not found.")

            # Check for email conflict if email is being updated
            if email and email != employee.email:
                existing = self.get_employee_by_email(email, db)
                if existing and existing.id != employee.id:
                     raise EmployeeAlreadyExistsError(f"Another employee with email '{email}' already exists.")

            # Update fields if provided
            if first_name is not None:
                employee.first_name = first_name
            if email is not None:
                employee.email = email
            if last_name is not None:
                employee.last_name = last_name
            if phone is not None:
                employee.phone = phone
            if notes is not None:
                employee.notes = notes
            if employee_id_field is not None: # Use employee_id_field to avoid conflict with function param
                employee.employee_id = employee_id_field

            db.commit()
            db.refresh(employee) # Refresh to get updated timestamps
            logging.info(f"Updated employee ID {employee.id}: {employee.first_name} {employee.last_name}")
            return employee
        except EmployeeNotFoundError:
            db.rollback()
            raise
        except EmployeeAlreadyExistsError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logging.error(f"Error updating employee ID {employee_id}: {e}")
            raise EmployeeServiceError(f"Failed to update employee: {e}") from e
        finally:
            if managed_session:
                db.close()

    def delete_employee(self, employee_id: int, db: Session = None):
        """Delete an employee by ID."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            employee = self.get_employee_by_id(employee_id, db)
            if not employee:
                raise EmployeeNotFoundError(f"Employee with ID {employee_id} not found for deletion.")

            db.delete(employee)
            db.commit()
            logging.info(f"Deleted employee ID {employee_id}: {employee.first_name} {employee.last_name}")
        except EmployeeNotFoundError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logging.error(f"Error deleting employee ID {employee_id}: {e}")
            raise EmployeeServiceError(f"Failed to delete employee: {e}") from e
        finally:
            if managed_session:
                db.close()

    def import_employees_from_csv(self, csv_file_path: Path, db: Session = None) -> Tuple[int, int, List[str]]:
        """
        Import employees from a CSV file.
        Expected columns: name, email, phone
        Returns: A tuple containing (success_count, error_count, list of error messages)
        """
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        success_count = 0
        error_count = 0
        errors: List[str] = [] # Explicitly type the list

        try:
            with open(csv_file_path, 'r', encoding='utf-8-sig') as csvfile: # utf-8-sig handles BOM
                reader = csv.DictReader(csvfile)
                expected_columns = {'name', 'email', 'phone'}
                if not expected_columns.issubset(reader.fieldnames):
                    raise EmployeeServiceError(f"CSV is missing required columns. Found: {reader.fieldnames}, Required: {expected_columns}")

                for row_num, row in enumerate(reader, start=2): # Start at 2 because header is row 1
                    try:
                        name = row.get('name', '').strip()
                        email = row.get('email', '').strip().lower() # Normalize email
                        phone = row.get('phone', '').strip()

                        if not name or not email:
                            errors.append(f"Row {row_num}: Missing name or email.")
                            error_count += 1
                            continue

                        # Split name into first and last (simple approach)
                        name_parts = name.split(' ', 1)
                        first_name = name_parts[0]
                        last_name = name_parts[1] if len(name_parts) > 1 else None

                        # Try to create the employee
                        self.create_employee(first_name=first_name, last_name=last_name,
                                             email=email, phone=phone, db=db)
                        success_count += 1
                    except EmployeeAlreadyExistsError as e:
                        errors.append(f"Row {row_num}: {str(e)}")
                        error_count += 1
                    except Exception as e:
                        errors.append(f"Row {row_num}: Unexpected error - {str(e)}")
                        error_count += 1

            db.commit() # Commit all successful imports
            logging.info(f"Finished importing employees from {csv_file_path}. Success: {success_count}, Errors: {error_count}")
            return success_count, error_count, errors

        except FileNotFoundError:
            error_msg = f"CSV file not found: {csv_file_path}"
            logging.error(error_msg)
            raise EmployeeServiceError(error_msg)
        except Exception as e:
            db.rollback()
            error_msg = f"Error reading CSV file {csv_file_path}: {e}"
            logging.error(error_msg)
            raise EmployeeServiceError(error_msg) from e
        finally:
            if managed_session:
                db.close()

    # --- Default User Creation ---
    def create_default_admin():
        """
        Creates a default 'admin' user with password 'admin123' if no users exist.
        This should only run on the very first startup.
        """
        # --- FIX: Use the imported engine object directly ---
        # Check if the engine object from database.py is initialized
        if engine is None:
            logging.error("Database engine is not initialized. Cannot create default admin.")
            print("Error: Database engine is not initialized. Cannot create default admin user.")
            return # Exit the function early

        db_session = SessionLocal()
        try:
            # Check if any users exist in the database
            user_count = db_session.query(User).count()

            if user_count == 0:
                default_username = "admin"
                default_password = "admin123" # MUST be changed by the user immediately
                logging.warning(
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
                from utils.security import hash_password # Import locally to avoid potential circular imports at module level if not handled carefully
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
                logging.info(f"Default admin user '{default_username}' created successfully.")
            else:
                logging.info("Existing users found in the database. Skipping default admin creation.")

        except Exception as e:
            logging.error(f"Error during default admin user creation/check: {e}", exc_info=True)
            print(f"Warning: An error occurred while checking/creating the default admin user. See logs for details.")
            # Depending on policy, you might want to exit here if this step is mandatory
            # sys.exit(1)
        finally:
            # Ensure the database session is closed
            db_session.close()




# Global instance for easy access
employee_service = EmployeeService()