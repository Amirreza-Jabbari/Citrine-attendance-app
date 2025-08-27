# tests/test_employee_crud.py
import sys
import os
# Add src to the path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import unittest
from citrine_attendance.database import init_db, get_db_session
from citrine_attendance.services.employee_service import (
    employee_service, EmployeeNotFoundError, EmployeeAlreadyExistsError
)
import tempfile
import shutil
from pathlib import Path

class TestEmployeeCRUD(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create a temporary directory for test data
        cls.test_dir = Path(tempfile.mkdtemp())
        print(f"Test data directory: {cls.test_dir}")

        # Override config paths for testing
        # We need to patch the config, which is a bit tricky.
        # A better way is to allow config to take paths, but for simplicity here:
        # We'll directly manipulate the config instance's paths for this test.
        # This is a bit of a hack for this isolated test.
        from citrine_attendance.config import config
        cls.original_user_data_dir = config.user_data_dir
        cls.original_settings_file = config.settings_file
        cls.original_get_db_path = config.get_db_path

        config.user_data_dir = cls.test_dir
        config.settings_file = cls.test_dir / "settings.json"
        # Override get_db_path method temporarily
        cls.original_get_db_path_method = config.get_db_path
        config.get_db_path = lambda: cls.test_dir / "test_attendance.db"

        # Re-initialize config directories
        config.ensure_directories_exist()
        # Re-save settings to test dir
        config.save_settings()

        # Initialize the test database
        init_db()

    @classmethod
    def tearDownClass(cls):
        # Restore original config (important if other tests rely on it)
        from citrine_attendance.config import config
        config.user_data_dir = cls.original_user_data_dir
        config.settings_file = cls.original_settings_file
        config.get_db_path = cls.original_get_db_path_method

        # Remove the temporary directory after tests
        try:
            shutil.rmtree(cls.test_dir)
            print(f"Removed test data directory: {cls.test_dir}")
        except Exception as e:
            print(f"Warning: Could not remove test directory {cls.test_dir}: {e}")


    def test_1_create_employee(self):
        """Test creating a new employee."""
        emp = employee_service.create_employee(
            first_name="Alice",
            last_name="Smith",
            email="alice.smith@example.com",
            phone="123-456-7890",
            notes="Software Engineer"
        )
        self.assertIsNotNone(emp.id)
        self.assertEqual(emp.first_name, "Alice")
        self.assertEqual(emp.email, "alice.smith@example.com")
        print(f"Created employee: {emp.first_name} {emp.last_name}")

    def test_2_get_employee_by_id(self):
        """Test retrieving an employee by ID."""
        # Get the ID from the previous test (assuming it ran)
        # A better way is to create it here and get the ID
        emp = employee_service.create_employee(
            first_name="Bob",
            last_name="Jones",
            email="bob.jones@example.com"
        )
        emp_id = emp.id

        retrieved_emp = employee_service.get_employee_by_id(emp_id)
        self.assertIsNotNone(retrieved_emp)
        self.assertEqual(retrieved_emp.id, emp_id)
        self.assertEqual(retrieved_emp.first_name, "Bob")
        print(f"Retrieved employee by ID: {retrieved_emp.first_name}")

    def test_3_get_employee_by_email(self):
        """Test retrieving an employee by email."""
        email = "charlie.brown@example.com"
        employee_service.create_employee(
            first_name="Charlie",
            last_name="Brown",
            email=email
        )

        retrieved_emp = employee_service.get_employee_by_email(email)
        self.assertIsNotNone(retrieved_emp)
        self.assertEqual(retrieved_emp.email, email)
        print(f"Retrieved employee by email: {retrieved_emp.first_name}")

    def test_4_get_all_employees(self):
        """Test retrieving all employees."""
        all_emps = employee_service.get_all_employees()
        self.assertGreaterEqual(len(all_emps), 3) # At least Alice, Bob, Charlie
        print(f"Retrieved {len(all_emps)} employees.")

    def test_5_update_employee(self):
        """Test updating an employee."""
        emp = employee_service.create_employee(
            first_name="Diana",
            last_name="Prince",
            email="diana.prince@example.com"
        )
        emp_id = emp.id

        updated_emp = employee_service.update_employee(
            employee_id=emp_id,
            phone="987-654-3210",
            notes="Updated notes"
        )

        self.assertEqual(updated_emp.phone, "987-654-3210")
        self.assertEqual(updated_emp.notes, "Updated notes")
        print(f"Updated employee ID {emp_id}")

    def test_6_delete_employee(self):
        """Test deleting an employee."""
        emp = employee_service.create_employee(
            first_name="Eve",
            last_name="Tester",
            email="eve.tester@example.com"
        )
        emp_id = emp.id

        # Ensure it exists
        self.assertIsNotNone(employee_service.get_employee_by_id(emp_id))

        # Delete it
        employee_service.delete_employee(emp_id)

        # Ensure it's gone
        deleted_emp = employee_service.get_employee_by_id(emp_id)
        self.assertIsNone(deleted_emp)
        print(f"Deleted employee ID {emp_id}")

    def test_7_create_duplicate_email_error(self):
        """Test that creating an employee with a duplicate email raises an error."""
        email = "unique@example.com"
        employee_service.create_employee(first_name="Unique", email=email)

        with self.assertRaises(EmployeeAlreadyExistsError):
            employee_service.create_employee(first_name="Another", email=email)
        print("Correctly prevented duplicate email creation.")

    def test_8_update_to_duplicate_email_error(self):
        """Test that updating an employee to a duplicate email raises an error."""
        email1 = "update1@example.com"
        email2 = "update2@example.com"
        emp1 = employee_service.create_employee(first_name="Update1", email=email1)
        emp2 = employee_service.create_employee(first_name="Update2", email=email2)

        with self.assertRaises(EmployeeAlreadyExistsError):
            employee_service.update_employee(emp2.id, email=email1) # Try to change emp2's email to emp1's
        print("Correctly prevented updating to duplicate email.")

    def test_9_delete_nonexistent_employee_error(self):
        """Test that deleting a non-existent employee raises an error."""
        non_existent_id = 99999
        with self.assertRaises(EmployeeNotFoundError):
            employee_service.delete_employee(non_existent_id)
        print("Correctly handled deletion of non-existent employee.")

    # Note: CSV import test would require creating a temporary CSV file.
    # It's a good test to add later.

if __name__ == '__main__':
    unittest.main()