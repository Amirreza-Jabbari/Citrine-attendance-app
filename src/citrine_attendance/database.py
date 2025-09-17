# src/citrine_attendance/database.py
import logging
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, Date, Time,
    Boolean, ForeignKey, Index, event, inspect, text
)
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
import datetime
from .config import config

Base = declarative_base()

class Employee(Base):
    __tablename__ = 'employees'
    id = Column(Integer, primary_key=True)
    employee_id = Column(String, unique=True, nullable=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    # HEROIC FIX: Added monthly leave allowance in minutes
    monthly_leave_allowance_minutes = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    attendance_records = relationship("Attendance", back_populates="employee", cascade="all, delete-orphan")

class Attendance(Base):
    __tablename__ = 'attendance'
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey('employees.id', ondelete='CASCADE'), nullable=False)
    date = Column(Date, nullable=False)
    time_in = Column(Time, nullable=True)
    time_out = Column(Time, nullable=True)

    # --- Leave Time Fields ---
    leave_start = Column(Time, nullable=True)
    leave_end = Column(Time, nullable=True)

    # --- Derived/Calculated Fields ---
    duration_minutes = Column(Integer, nullable=True)
    launch_duration_minutes = Column(Integer, nullable=True)
    leave_duration_minutes = Column(Integer, nullable=True) # New column for leave duration
    tardiness_minutes = Column(Integer, nullable=True)
    # HEROIC FIX: Added early_departure_minutes for "Ta'jil"
    early_departure_minutes = Column(Integer, nullable=True)
    main_work_minutes = Column(Integer, nullable=True)
    overtime_minutes = Column(Integer, nullable=True)
    status = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    is_archived = Column(Boolean, default=False, nullable=False)
    employee = relationship("Employee", back_populates="attendance_records")

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
     password_hash = Column(String, nullable=False)
     role = Column(String, nullable=False) # 'admin', 'operator'
     created_at = Column(DateTime, default=datetime.datetime.utcnow)
     last_login = Column(DateTime, nullable=True)

class AuditLog(Base):
    __tablename__ = 'audit_log'
    id = Column(Integer, primary_key=True)
    table_name = Column(String, nullable=False)
    record_id = Column(Integer, nullable=False)
    action = Column(String, nullable=False)
    changes_json = Column(Text, nullable=True)
    performed_by = Column(String, nullable=False)
    performed_at = Column(DateTime, default=datetime.datetime.utcnow)

engine = None
SessionLocal = None

def get_database_url():
    db_path = config.get_db_path()
    return f"sqlite:///{db_path}"

def init_db():
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

        # --- MIGRATION ---
        inspector = inspect(engine)
        with engine.connect() as connection:
            # --- Attendance Table Migrations ---
            if inspector.has_table('attendance'):
                attendance_columns = [column['name'] for column in inspector.get_columns('attendance')]
                
                migrations = {
                    "leave_start": "ALTER TABLE attendance ADD COLUMN leave_start TIME",
                    "leave_end": "ALTER TABLE attendance ADD COLUMN leave_end TIME",
                    "leave_duration_minutes": "ALTER TABLE attendance ADD COLUMN leave_duration_minutes INTEGER",
                    "launch_duration_minutes": "ALTER TABLE attendance ADD COLUMN launch_duration_minutes INTEGER",
                    "tardiness_minutes": "ALTER TABLE attendance ADD COLUMN tardiness_minutes INTEGER",
                    "main_work_minutes": "ALTER TABLE attendance ADD COLUMN main_work_minutes INTEGER",
                    "overtime_minutes": "ALTER TABLE attendance ADD COLUMN overtime_minutes INTEGER",
                    # HEROIC FIX: Added migration for early_departure_minutes
                    "early_departure_minutes": "ALTER TABLE attendance ADD COLUMN early_departure_minutes INTEGER"
                }
                
                if 'launch_start' in attendance_columns and 'leave_start' not in attendance_columns:
                    logging.warning("Migrating database: renaming 'launch_start' to 'leave_start'.")
                    connection.execute(text("ALTER TABLE attendance RENAME COLUMN launch_start TO leave_start"))
                if 'launch_end' in attendance_columns and 'leave_end' not in attendance_columns:
                    logging.warning("Migrating database: renaming 'launch_end' to 'leave_end'.")
                    connection.execute(text("ALTER TABLE attendance RENAME COLUMN launch_end TO leave_end"))
                
                for col_name, alter_sql in migrations.items():
                    attendance_columns_refreshed = [c['name'] for c in inspector.get_columns('attendance')]
                    if col_name not in attendance_columns_refreshed:
                        logging.warning(f"Migrating database: Adding '{col_name}' column to attendance.")
                        try:
                            trans = connection.begin()
                            connection.execute(text(alter_sql))
                            trans.commit()
                            logging.info(f"Successfully added '{col_name}' column.")
                        except Exception as e:
                            if trans: trans.rollback()
                            logging.critical(f"Failed to add '{col_name}': {e}")

            # --- Employee Table Migrations (HEROIC FIX) ---
            if inspector.has_table('employees'):
                employee_columns = [column['name'] for column in inspector.get_columns('employees')]
                if 'monthly_leave_allowance_minutes' not in employee_columns:
                    logging.warning("Migrating database: Adding 'monthly_leave_allowance_minutes' column to employees.")
                    try:
                        trans = connection.begin()
                        connection.execute(text("ALTER TABLE employees ADD COLUMN monthly_leave_allowance_minutes INTEGER NOT NULL DEFAULT 0"))
                        trans.commit()
                        logging.info("Successfully added 'monthly_leave_allowance_minutes' column.")
                    except Exception as e:
                        if trans: trans.rollback()
                        logging.critical(f"Failed to add 'monthly_leave_allowance_minutes': {e}")

    except Exception as e:
        logging.critical(f"Failed to initialize database: {e}")
        raise

def get_db_session():
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def utcnow():
    return datetime.datetime.utcnow()