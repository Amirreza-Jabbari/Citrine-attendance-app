# src/citrine_attendance/services/employee_service.py
import logging
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ..database import Employee, get_db_session, User
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
        pass

    def _get_session(self) -> Session:
        """Helper to get a database session."""
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
            return db.query(Employee).order_by(Employee.first_name, Employee.last_name).all()
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
            return db.query(Employee).filter(Employee.id == employee_id).first()
        finally:
            if managed_session:
                db.close()

    def create_employee(self, first_name: str, email: str, last_name: str = None,
                        phone: str = None, notes: str = None,
                        employee_id: str = None, monthly_leave_allowance_hours: int = 0,
                        db: Session = None) -> Employee:
        """Create a new employee, accepting leave allowance in hours."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False
        try:
            if not first_name or not email:
                raise ValueError("First name and email are required.")
            
            existing = self.get_employee_by_email(email, db)
            if existing:
                raise EmployeeAlreadyExistsError(f"Employee with email '{email}' already exists.")

            # Convert hours from UI to minutes for DB
            monthly_leave_allowance_minutes = monthly_leave_allowance_hours * 60

            new_employee = Employee(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                notes=notes,
                employee_id=employee_id,
                monthly_leave_allowance_minutes=monthly_leave_allowance_minutes
            )
            db.add(new_employee)
            db.commit()
            db.refresh(new_employee)
            logging.info(f"Created new employee: {new_employee.first_name} {new_employee.last_name}")
            return new_employee
        except IntegrityError as e:
            db.rollback()
            logging.error(f"Integrity error creating employee: {e}")
            raise EmployeeAlreadyExistsError("Employee creation failed due to a conflict (e.g., duplicate email).") from e
        except Exception as e:
            db.rollback()
            logging.error(f"Error creating employee: {e}")
            raise EmployeeServiceError(f"Failed to create employee: {e}") from e
        finally:
            if managed_session:
                db.close()

    def update_employee(self, employee_id: int, first_name: str = None, email: str = None,
                        last_name: str = None, phone: str = None, notes: str = None,
                        employee_id_field: str = None, monthly_leave_allowance_hours: int = None,
                        db: Session = None) -> Employee:
        """Update an existing employee, accepting leave allowance in hours."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False
        try:
            employee = self.get_employee_by_id(employee_id, db)
            if not employee:
                raise EmployeeNotFoundError(f"Employee with ID {employee_id} not found.")

            if email and email != employee.email:
                existing = self.get_employee_by_email(email, db)
                if existing and existing.id != employee.id:
                    raise EmployeeAlreadyExistsError(f"Another employee with email '{email}' already exists.")

            if first_name is not None: employee.first_name = first_name
            if email is not None: employee.email = email
            if last_name is not None: employee.last_name = last_name
            if phone is not None: employee.phone = phone
            if notes is not None: employee.notes = notes
            if employee_id_field is not None: employee.employee_id = employee_id_field
            
            # Convert hours from UI to minutes for DB
            if monthly_leave_allowance_hours is not None:
                employee.monthly_leave_allowance_minutes = monthly_leave_allowance_hours * 60

            db.commit()
            db.refresh(employee)
            logging.info(f"Updated employee ID {employee.id}: {employee.first_name} {employee.last_name}")
            return employee
        except (EmployeeNotFoundError, EmployeeAlreadyExistsError):
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

# Global instance for easy access
employee_service = EmployeeService()