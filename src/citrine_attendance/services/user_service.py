# src/citrine_attendance/services/user_service.py
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ..database import User, get_db_session
from ..utils.security import hash_password, verify_password

class UserServiceError(Exception):
    """Base exception for user service errors."""
    pass

class UserNotFoundError(UserServiceError):
    """Raised when a user is not found."""
    pass

class UserAlreadyExistsError(UserServiceError):
    """Raised when trying to create a user that already exists."""
    pass

class InvalidCredentialsError(UserServiceError):
    """Raised when username/password is incorrect."""
    pass

class UserService:
    """Service class to handle user-related business logic."""

    def __init__(self):
        pass

    def _get_session(self) -> Session:
        """Helper to get a database session."""
        session_gen = get_db_session()
        return next(session_gen)

    def create_user(self, username: str, password: str, role: str = "operator", db: Session = None) -> User:
        """Create a new user."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            if not username or not password:
                raise ValueError("Username and password are required.")

            if role not in ["admin", "operator"]:
                 # Log warning but default to operator for safety
                 logging.warning(f"Invalid role '{role}' provided for user '{username}'. Defaulting to 'operator'.")
                 role = "operator"

            # Check for existing user
            existing = self.get_user_by_username(username, db)
            if existing:
                raise UserAlreadyExistsError(f"User '{username}' already exists.")

            hashed_pw = hash_password(password)
            new_user = User(username=username, password_hash=hashed_pw, role=role)
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            logging.info(f"Created new user: {new_user.username} (Role: {new_user.role})")
            return new_user
        except IntegrityError as e:
            db.rollback()
            logging.error(f"Integrity error creating user: {e}")
            raise UserAlreadyExistsError(f"User creation failed due to a conflict.") from e
        except Exception as e:
            db.rollback()
            logging.error(f"Error creating user '{username}': {e}")
            raise UserServiceError(f"Failed to create user: {e}") from e
        finally:
            if managed_session:
                db.close()

    def get_user_by_username(self, username: str, db: Session = None) -> Optional[User]:
        """Retrieve a user by their username."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            user = db.query(User).filter(User.username == username).first()
            return user
        finally:
            if managed_session:
                db.close()

    def get_user_by_id(self, user_id: int, db: Session = None) -> Optional[User]:
        """Retrieve a user by their database ID."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            user = db.query(User).filter(User.id == user_id).first()
            return user
        finally:
            if managed_session:
                db.close()

    def authenticate_user(self, username: str, password: str, db: Session = None) -> Optional[User]:
        """Authenticate a user by username and password."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            user = self.get_user_by_username(username, db)
            if user and verify_password(password, user.password_hash):
                # Update last login time (optional)
                import datetime
                user.last_login = datetime.datetime.utcnow()
                db.commit()
                db.refresh(user)
                logging.info(f"User '{username}' authenticated successfully.")
                return user
            else:
                logging.info(f"Authentication failed for user '{username}'.")
                return None # Explicitly return None on failure
        except Exception as e:
            logging.error(f"Error during authentication for '{username}': {e}")
            return None # Safer to fail authentication on error
        finally:
            if managed_session:
                db.close()

    def is_admin(self, user: User) -> bool:
        """Check if a user has admin role."""
        return user is not None and user.role == "admin"

    def is_operator(self, user: User) -> bool:
        """Check if a user has operator role."""
        # Operators are users with role 'operator'
        return user is not None and user.role == "operator"

    def change_password(self, user_id: int, new_password: str, db: Session = None):
        """Change a user's password."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            user = self.get_user_by_id(user_id, db)
            if not user:
                raise UserNotFoundError(f"User with ID {user_id} not found.")

            user.password_hash = hash_password(new_password)
            db.commit()
            logging.info(f"Password changed for user ID {user_id}.")
        except UserNotFoundError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logging.error(f"Error changing password for user ID {user_id}: {e}")
            raise UserServiceError(f"Failed to change password: {e}") from e
        finally:
            if managed_session:
                db.close()

    def delete_user(self, user_id: int, db: Session = None):
        """Delete a user by ID (Admin only)."""
        # Basic check, caller should ensure admin rights
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            user = self.get_user_by_id(user_id, db)
            if not user:
                raise UserNotFoundError(f"User with ID {user_id} not found for deletion.")

            db.delete(user)
            db.commit()
            logging.info(f"Deleted user ID {user_id}: {user.username}")
        except UserNotFoundError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logging.error(f"Error deleting user ID {user_id}: {e}")
            raise UserServiceError(f"Failed to delete user: {e}") from e
        finally:
            if managed_session:
                db.close()


# Global instance
user_service = UserService()