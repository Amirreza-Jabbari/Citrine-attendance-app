# src/citrine_attendance/database.py
import logging
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Date, Time, Boolean, ForeignKey, Index, event, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
from .config import config # Import our config to get the DB path

Base = declarative_base()

# --- Models ---
class Employee(Base):
    __tablename__ = 'employees'

    id = Column(Integer, primary_key=True)
    employee_id = Column(String, unique=True, nullable=True) # Optional custom ID
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationship
    attendance_records = relationship("Attendance", back_populates="employee", cascade="all, delete-orphan")

class Attendance(Base):
    __tablename__ = 'attendance'

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey('employees.id', ondelete='CASCADE'), nullable=False)
    date = Column(Date, nullable=False) # Stored as ISO Gregorian YYYY-MM-DD
    time_in = Column(Time, nullable=True)
    time_out = Column(Time, nullable=True)
    duration_minutes = Column(Integer, nullable=True) # Derived/calculated field
    status = Column(String, nullable=False) # 'present', 'absent', 'late', 'halfday'
    note = Column(Text, nullable=True)

    created_by = Column(String, nullable=True) # Username or identifier
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # --- Archive Flag ---
    # Note: The model defines it as NOT NULL, but the migration below adds it as NULLABLE first 
    # to handle existing databases, then relies on the default. 
    # SQLAlchemy ORM should handle this, but the DB column might be nullable if migrated.
    is_archived = Column(Boolean, default=False, nullable=False) 

    # Relationship
    employee = relationship("Employee", back_populates="attendance_records")

# Indexes for performance
Index('idx_attendance_employee_id', Attendance.employee_id)
Index('idx_attendance_date', Attendance.date)
Index('idx_attendance_date_employee', Attendance.date, Attendance.employee_id)

class BackupRecord(Base):
    __tablename__ = 'backups'

    id = Column(Integer, primary_key=True)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    size_bytes = Column(Integer, nullable=False)
    encrypted = Column(Boolean, default=False)

class User(Base):
     __tablename__ = 'users'

     id = Column(Integer, primary_key=True)
     username = Column(String, unique=True, nullable=False)
     password_hash = Column(String, nullable=False) # Will store bcrypt hash
     role = Column(String, nullable=False) # 'admin', 'operator'
     created_at = Column(DateTime, default=datetime.datetime.utcnow)
     last_login = Column(DateTime, nullable=True)

class AuditLog(Base):
    __tablename__ = 'audit_log'

    id = Column(Integer, primary_key=True)
    table_name = Column(String, nullable=False) # e.g., 'employees', 'attendance'
    record_id = Column(Integer, nullable=False) # ID of the record in the table
    action = Column(String, nullable=False) # 'create', 'update', 'delete'
    changes_json = Column(Text, nullable=True) # JSON string describing changes
    performed_by = Column(String, nullable=False) # Username
    performed_at = Column(DateTime, default=datetime.datetime.utcnow)


# --- Database Engine & Session ---
def get_database_url():
    """Construct the database URL."""
    db_path = config.get_db_path()
    return f"sqlite:///{db_path}"

engine = None
SessionLocal = None

def init_db():
    """Initialize the database engine, create tables, and perform migrations."""
    global engine, SessionLocal
    database_url = get_database_url()
    logging.info(f"Initializing database at: {database_url}")
    try:
        # Use check_same_thread=False for SQLite in multi-threaded apps (like Qt)
        engine = create_engine(database_url, echo=False, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Ensure foreign key constraints are enforced in SQLite
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        # Create tables if they don't exist
        Base.metadata.create_all(bind=engine)
        logging.info("Database tables created/verified.")

        # --- MIGRATION: Add 'is_archived' column if it doesn't exist ---
        # This handles databases created before the column was added to the model.
        if engine and inspect(engine).has_table('attendance'):
            inspector = inspect(engine)
            attendance_columns = [column['name'] for column in inspector.get_columns('attendance')]

            if 'is_archived' not in attendance_columns:
                logging.warning("Migrating database: 'is_archived' column not found in 'attendance' table. Attempting to add it.")
                # Use raw SQL to add the column.
                # Import text for executing raw SQL
                from sqlalchemy import text
                try:
                    # Get a connection from the engine
                    with engine.connect() as connection:
                        # Begin a transaction
                        trans = connection.begin()
                        try:
                            # Use text() to wrap the raw SQL string
                            connection.execute(text("ALTER TABLE attendance ADD COLUMN is_archived BOOLEAN DEFAULT 0"))
                            # Commit the transaction
                            trans.commit()
                            logging.info("Successfully added 'is_archived' column (nullable with default 0) to 'attendance' table.")
                        except Exception as inner_e:
                            # Rollback the transaction on error
                            trans.rollback()
                            raise inner_e # Re-raise to be caught by the outer except
                except Exception as e:
                    error_msg = f"Failed to add 'is_archived' column during migration: {e}"
                    logging.critical(error_msg)
                    raise RuntimeError(error_msg) from e # Halt startup if migration fails
            else:
                logging.debug("'is_archived' column already exists in 'attendance' table. No migration needed.")

    except Exception as e:
        logging.critical(f"Failed to initialize database: {e}")
        raise # Re-raise to halt application startup if DB init fails

def get_db_session():
    """Provide a database session."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Utility for Timestamps ---
def utcnow():
    """Get current UTC time."""
    return datetime.datetime.utcnow()

# Initialize on import (or call explicitly in main)
# init_db() # Better to call explicitly in main.py to control when it happens