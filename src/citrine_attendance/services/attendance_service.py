# src/citrine_attendance/services/attendance_service.py
import logging
from typing import List, Optional, Dict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
import datetime
from ..database import Attendance, Employee, get_db_session
from ..config import config

class AttendanceServiceError(Exception): pass
class AttendanceNotFoundError(AttendanceServiceError): pass
class AttendanceAlreadyExistsError(AttendanceServiceError): pass

class AttendanceService:
    STATUS_PRESENT = "present"
    STATUS_ABSENT = "absent"
    STATUS_ON_LEAVE = "on_leave" # New status
    STATUS_DISPLAY = {"present": "Present", "absent": "Absent", "on_leave": "On Leave"}

    def _get_session(self) -> Session:
        return next(get_db_session())

    def _calculate_all_fields(self, record: Attendance):
        """Calculates all derived time fields for an attendance record."""
        # Reset all calculated fields
        record.duration_minutes = None
        record.launch_duration_minutes = None
        record.leave_duration_minutes = None
        record.tardiness_minutes = None
        record.main_work_minutes = None
        record.overtime_minutes = None
        record.status = self.STATUS_ABSENT

        # Calculate leave duration first
        leave_minutes = 0
        if record.leave_start and record.leave_end and record.leave_end > record.leave_start:
            leave_dt_start = datetime.datetime.combine(record.date, record.leave_start)
            leave_dt_end = datetime.datetime.combine(record.date, record.leave_end)
            leave_minutes = int((leave_dt_end - leave_dt_start).total_seconds() / 60)
        record.leave_duration_minutes = leave_minutes

        # Determine status based on presence and leave
        if record.time_in:
            record.status = self.STATUS_PRESENT
        if leave_minutes > 0 and not record.time_in:
            record.status = self.STATUS_ON_LEAVE

        # Stop if there's no time_in/time_out range
        if not (record.time_in and record.time_out and record.time_out > record.time_in):
            return

        dt_in = datetime.datetime.combine(record.date, record.time_in)
        dt_out = datetime.datetime.combine(record.date, record.time_out)

        total_duration_minutes = int((dt_out - dt_in).total_seconds() / 60)
        record.duration_minutes = total_duration_minutes
        
        # Calculate launch time based on settings
        launch_minutes = 0
        try:
            start_str = config.settings.get("default_launch_start_time", "12:30")
            end_str = config.settings.get("default_launch_end_time", "13:30")
            h_start, m_start = map(int, start_str.split(':'))
            h_end, m_end = map(int, end_str.split(':'))
            launch_start_time = datetime.time(h_start, m_start)
            launch_end_time = datetime.time(h_end, m_end)
            
            # Check if the work period overlaps with launch time
            if record.time_in < launch_end_time and record.time_out > launch_start_time:
                 launch_minutes = (datetime.datetime.combine(record.date, launch_end_time) - datetime.datetime.combine(record.date, launch_start_time)).total_seconds() / 60

        except (ValueError, TypeError):
            launch_minutes = 0 # Default to 0 if config is invalid
        record.launch_duration_minutes = int(launch_minutes)

        net_work_minutes = max(0, total_duration_minutes - launch_minutes - leave_minutes)

        # Tardiness Calculation
        late_threshold_str = config.settings.get("late_threshold_time", "10:00")
        try:
            hour, minute = map(int, late_threshold_str.split(':'))
            late_threshold_dt = dt_in.replace(hour=hour, minute=minute, second=0, microsecond=0)
            record.tardiness_minutes = max(0, int((dt_in - late_threshold_dt).total_seconds() / 60))
        except (ValueError, TypeError):
            record.tardiness_minutes = 0

        # Overtime Calculation
        workday_minutes = config.settings.get("workday_hours", 8) * 60
        overtime_minutes = max(0, net_work_minutes - workday_minutes)
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
    
    def get_attendance_for_export(self, db: Optional[Session] = None, **filters) -> List[Dict]:
        needs_closing = db is None
        db = db or self._get_session()
        try:
            records = self.get_attendance_records(db=db, **filters)
            return [{
                "Employee Name": f"{r.employee.first_name} {r.employee.last_name}".strip(),
                "Date": r.date, "Time In": r.time_in, "Time Out": r.time_out,
                "Leave (min)": r.leave_duration_minutes, # Added Leave
                "Tardiness (min)": r.tardiness_minutes, 
                "Main Work (min)": r.main_work_minutes,
                "Overtime (min)": r.overtime_minutes, 
                "Launch Time (min)": r.launch_duration_minutes,
                "Total Duration (min)": r.duration_minutes,
                "Status": r.status,
                "Note": r.note or "",
            } for r in records]
        finally:
            if needs_closing: db.close()

attendance_service = AttendanceService()