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
    
    # --- New Launch Time Fields ---
    launch_start_time = Column(Time, nullable=True)
    launch_end_time = Column(Time, nullable=True)

    # --- Derived/Calculated Fields ---
    duration_minutes = Column(Integer, nullable=True) # Total duration in minutes
    launch_duration_minutes = Column(Integer, nullable=True) # Launch duration in minutes
    tardiness_minutes = Column(Integer, nullable=True) # Lateness in minutes
    main_work_minutes = Column(Integer, nullable=True) # Regular work time
    overtime_minutes = Column(Integer, nullable=True) # Overtime work

    status = Column(String, nullable=False) # 'present', 'absent'
    note = Column(Text, nullable=True)

    created_by = Column(String, nullable=True) # Username or identifier
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    is_archived = Column(Boolean, default=False, nullable=False) 

    # Relationship
    employee = relationship("Employee", back_populates="attendance_records")

# Indexes for performance
Index('idx_attendance_employee_id', Attendance.employee_id)
Index('idx_attendance_date', Attendance.date)
Index('idx_attendance_date_employee', Attendance.date, Attendance.employee_id)

class BackupRecord(Base):
    __tablename__ = 'backups'
    # ... (no changes here)
    id = Column(Integer, primary_key=True)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    size_bytes = Column(Integer, nullable=False)
    encrypted = Column(Boolean, default=False)


class User(Base):
     __tablename__ = 'users'
     # ... (no changes here)
     id = Column(Integer, primary_key=True)
     username = Column(String, unique=True, nullable=False)
     password_hash = Column(String, nullable=False) # Will store bcrypt hash
     role = Column(String, nullable=False) # 'admin', 'operator'
     created_at = Column(DateTime, default=datetime.datetime.utcnow)
     last_login = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = 'audit_log'
    # ... (no changes here)
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
        engine = create_engine(database_url, echo=False, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(bind=engine)
        logging.info("Database tables created/verified.")

        # --- MIGRATION: Add new columns if they don't exist ---
        if engine and inspect(engine).has_table('attendance'):
            inspector = inspect(engine)
            attendance_columns = [column['name'] for column in inspector.get_columns('attendance')]
            
            new_columns = {
                "launch_start_time": "ALTER TABLE attendance ADD COLUMN launch_start_time TIME",
                "launch_end_time": "ALTER TABLE attendance ADD COLUMN launch_end_time TIME",
                "launch_duration_minutes": "ALTER TABLE attendance ADD COLUMN launch_duration_minutes INTEGER",
                "tardiness_minutes": "ALTER TABLE attendance ADD COLUMN tardiness_minutes INTEGER",
                "main_work_minutes": "ALTER TABLE attendance ADD COLUMN main_work_minutes INTEGER",
                "overtime_minutes": "ALTER TABLE attendance ADD COLUMN overtime_minutes INTEGER"
            }
            
            from sqlalchemy import text
            with engine.connect() as connection:
                for col_name, alter_sql in new_columns.items():
                    if col_name not in attendance_columns:
                        logging.warning(f"Migrating database: '{col_name}' column not found in 'attendance' table. Adding it.")
                        try:
                            trans = connection.begin()
                            connection.execute(text(alter_sql))
                            trans.commit()
                            logging.info(f"Successfully added '{col_name}' column to 'attendance' table.")
                        except Exception as e:
                            trans.rollback()
                            logging.critical(f"Failed to add '{col_name}' column during migration: {e}")
                            raise RuntimeError(f"Failed to migrate database for column {col_name}") from e

    except Exception as e:
        logging.critical(f"Failed to initialize database: {e}")
        raise

def get_db_session():
    """Provide a database session."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def utcnow():
    """Get current UTC time."""
    return datetime.datetime.utcnow()