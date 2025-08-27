# src/citrine_attendance/utils/security.py
import bcrypt
import logging

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    try:
        # Convert password to bytes
        password_bytes = password.encode('utf-8')
        # Generate salt and hash
        hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
        # Return as string (bcrypt returns bytes)
        return hashed.decode('utf-8')
    except Exception as e:
        logging.error(f"Error hashing password: {e}")
        raise

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed one."""
    try:
        # Convert inputs to bytes
        plain_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        # Check
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except Exception as e:
        logging.error(f"Error verifying password: {e}")
        return False # Safer to fail verification on error