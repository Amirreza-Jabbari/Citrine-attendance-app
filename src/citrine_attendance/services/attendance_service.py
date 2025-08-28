# src/citrine_attendance/services/attendance_service.py
"""
Service layer for managing attendance records.
Handles clock-in/out, manual entry/editing, calculations, and data retrieval.
"""
import logging
from typing import List, Optional, Dict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_
import datetime
from ..database import Attendance, Employee, get_db_session
from ..config import config


class AttendanceServiceError(Exception):
    """Base exception for attendance service errors."""
    pass

class AttendanceNotFoundError(AttendanceServiceError):
    """Raised when an attendance record is not found."""
    pass

class AttendanceAlreadyExistsError(AttendanceServiceError):
    """Raised if trying to create a conflicting record."""
    pass

class AttendanceService:
    """Service class to handle attendance-related business logic."""

    STATUS_PRESENT = "present"
    STATUS_ABSENT = "absent"
    STATUS_DISPLAY = {"present": "Present", "absent": "Absent"}

    def __init__(self):
        """Initialize the service."""
        pass

    def _get_session(self) -> Session:
        """Helper to get a database session."""
        session_gen = get_db_session()
        return next(session_gen)

    def _calculate_all_fields(self, record: Attendance):
        """
        Calculates all derived time fields for an attendance record.
        """
        record.duration_minutes = None
        record.launch_duration_minutes = None
        record.tardiness_minutes = None
        record.main_work_minutes = None
        record.overtime_minutes = None
        record.status = self.STATUS_ABSENT

        if not (record.time_in and record.time_out and record.time_out > record.time_in):
            # If there's no valid time in/out, we can't calculate anything.
            # Set status based on whether there's at least a time_in.
            if record.time_in:
                record.status = self.STATUS_PRESENT # Considered present if clocked in
            return

        dt_in = datetime.datetime.combine(record.date, record.time_in)
        dt_out = datetime.datetime.combine(record.date, record.time_out)

        total_duration_minutes = int((dt_out - dt_in).total_seconds() / 60)
        record.duration_minutes = total_duration_minutes
        record.status = self.STATUS_PRESENT

        launch_minutes = 0
        # --- CORRECTED: Use record.launch_start and record.launch_end ---
        if record.launch_start and record.launch_end and record.launch_end > record.launch_start:
            launch_dt_start = datetime.datetime.combine(record.date, record.launch_start)
            launch_dt_end = datetime.datetime.combine(record.date, record.launch_end)
            launch_minutes = int((launch_dt_end - launch_dt_start).total_seconds() / 60)
        elif total_duration_minutes > (config.settings.get("workday_hours", 8) * 60) / 2:
            launch_minutes = config.settings.get("default_launch_time_minutes", 60)
        record.launch_duration_minutes = launch_minutes

        net_work_minutes = max(0, total_duration_minutes - launch_minutes)

        late_threshold_str = config.settings.get("late_threshold_time", "10:00")
        try:
            hour, minute = map(int, late_threshold_str.split(':'))
            late_threshold_dt = dt_in.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError:
            late_threshold_dt = dt_in.replace(hour=10, minute=0, second=0, microsecond=0)

        record.tardiness_minutes = max(0, int((dt_in - late_threshold_dt).total_seconds() / 60))

        workday_minutes = config.settings.get("workday_hours", 8) * 60
        official_end_dt = dt_in + datetime.timedelta(minutes=(workday_minutes + launch_minutes))

        overtime_minutes = 0
        if dt_out > official_end_dt:
            overtime_minutes = int((dt_out - official_end_dt).total_seconds() / 60)
        record.overtime_minutes = overtime_minutes

        record.main_work_minutes = max(0, net_work_minutes - overtime_minutes)

    def add_manual_attendance(self, db: Optional[Session] = None, **kwargs) -> Attendance:
        managed = db is None
        db = db or self._get_session()
        try:
            if db.query(Attendance).filter(and_(Attendance.employee_id == kwargs['employee_id'], Attendance.date == kwargs['date'])).first():
                raise AttendanceAlreadyExistsError("Record already exists.")
            new_record = Attendance(**kwargs)
            self._calculate_all_fields(new_record)
            db.add(new_record)
            db.commit()
            db.refresh(new_record)
            return new_record
        except Exception as e:
            db.rollback()
            raise AttendanceServiceError(f"Failed to add record: {e}") from e
        finally:
            if managed: db.close()

    def update_attendance(self, attendance_id: int, db: Optional[Session] = None, **kwargs) -> Attendance:
        managed = db is None
        db = db or self._get_session()
        try:
            record = db.query(Attendance).filter(Attendance.id == attendance_id).first()
            if not record: raise AttendanceNotFoundError("Record not found.")
            for key, value in kwargs.items():
                if hasattr(record, key): setattr(record, key, value)
            
            # Explicitly handle time fields to ensure recalculation
            if 'time_in' in kwargs: record.time_in = kwargs['time_in']
            if 'time_out' in kwargs: record.time_out = kwargs['time_out']
            if 'launch_start' in kwargs: record.launch_start = kwargs['launch_start']
            if 'launch_end' in kwargs: record.launch_end = kwargs['launch_end']

            self._calculate_all_fields(record)
            db.commit()
            db.refresh(record)
            return record
        except Exception as e:
            db.rollback()
            raise AttendanceServiceError(f"Failed to update record: {e}") from e
        finally:
            if managed: db.close()

    def delete_attendance(self, attendance_id: int, db: Optional[Session] = None):
        managed = db is None
        db = db or self._get_session()
        try:
            record = db.query(Attendance).filter(Attendance.id == attendance_id).first()
            if not record: raise AttendanceNotFoundError("Record not found.")
            db.delete(record)
            db.commit()
        except Exception as e:
            db.rollback()
            raise AttendanceServiceError(f"Failed to delete record: {e}") from e
        finally:
            if managed: db.close()

    def get_attendance_records(self, db: Optional[Session] = None, **filters) -> List[Attendance]:
        managed = db is None
        db = db or self._get_session()
        try:
            query = db.query(Attendance).join(Attendance.employee).options(joinedload(Attendance.employee))
            if filters.get('employee_id'): query = query.filter(Attendance.employee_id == filters['employee_id'])
            if filters.get('start_date'): query = query.filter(Attendance.date >= filters['start_date'])
            if filters.get('end_date'): query = query.filter(Attendance.date <= filters['end_date'])
            if filters.get('statuses'): query = query.filter(Attendance.status.in_(filters['statuses']))
            return query.order_by(Attendance.date.desc(), Employee.last_name).all()
        finally:
            if managed: db.close()

    def get_daily_summary(self, target_date: datetime.date, db: Optional[Session] = None) -> dict:
        managed = db is None
        db = db or self._get_session()
        try:
            present = db.query(Attendance).filter(and_(Attendance.date == target_date, Attendance.status == self.STATUS_PRESENT)).count()
            absent = db.query(Attendance).filter(and_(Attendance.date == target_date, Attendance.status == self.STATUS_ABSENT)).count()
            return {"present": present, "absent": absent}
        finally:
            if managed: db.close()

    def get_attendance_for_export(self, db: Optional[Session] = None, **filters) -> List[Dict]:
        needs_closing = db is None
        db = db or self._get_session()
        try:
            records = self.get_attendance_records(db=db, **filters)
            return [{
                "Employee Name": f"{r.employee.first_name} {r.employee.last_name}".strip(),
                "Date": r.date, "Time In": r.time_in, "Time Out": r.time_out,
                "Tardiness (min)": r.tardiness_minutes, "Main Work (min)": r.main_work_minutes,
                "Overtime (min)": r.overtime_minutes, "Launch Time (min)": r.launch_duration_minutes,
                "Total Duration (min)": r.duration_minutes,
                # CHANGE THIS LINE: Return the raw status key instead of the display string
                "Status": r.status,
                "Note": r.note or "",
            } for r in records]
        finally:
            if needs_closing: db.close()
                
    def get_archived_attendance_records(self, db: Optional[Session] = None, **filters) -> List[Attendance]:
        managed = db is None
        db = db or self._get_session()
        try:
            query = db.query(Attendance).options(joinedload(Attendance.employee)).filter(Attendance.is_archived == True)
            if filters.get('employee_id'): query = query.filter(Attendance.employee_id == filters['employee_id'])
            if filters.get('start_date'): query = query.filter(Attendance.date >= filters['start_date'])
            if filters.get('end_date'): query = query.filter(Attendance.date <= filters['end_date'])
            return query.order_by(Attendance.date.desc()).all()
        finally:
            if managed: db.close()

# Global instance
attendance_service = AttendanceService()