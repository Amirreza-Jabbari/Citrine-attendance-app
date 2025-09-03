# src/citrine_attendance/services/attendance_service.py
import logging
from typing import List, Optional, Dict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func, extract
import datetime
from ..database import Attendance, Employee, get_db_session
from ..config import config
from .employee_service import employee_service
from ..date_utils import get_jalali_month_range

logger = logging.getLogger(__name__)

class AttendanceServiceError(Exception): pass
class AttendanceNotFoundError(AttendanceServiceError): pass
class AttendanceAlreadyExistsError(AttendanceServiceError): pass
class AlreadyClockedInError(AttendanceServiceError): pass
class NotClockedInError(AttendanceServiceError): pass
class LeaveBalanceExceededError(AttendanceServiceError): pass


class AttendanceService:
    STATUS_PRESENT = "present"
    STATUS_ABSENT = "absent"
    STATUS_ON_LEAVE = "on_leave"
    STATUS_PARTIAL = "partial"
    STATUS_DISPLAY = {"present": "Present", "absent": "Absent", "on_leave": "On Leave"}

    def _get_session(self) -> Session:
        return next(get_db_session())

    def get_monthly_leave_taken(self, employee_id: int, date: datetime.date, db: Session) -> int:
        """Calculates the total leave minutes taken by an employee in a specific Jalali month."""
        start_of_month, end_of_month = get_jalali_month_range(date)

        total_leave = db.query(func.sum(Attendance.leave_duration_minutes)).filter(
            Attendance.employee_id == employee_id,
            Attendance.date.between(start_of_month, end_of_month),
            Attendance.leave_duration_minutes.isnot(None)
        ).scalar()

        return int(total_leave or 0)

    def _calculate_all_fields(self, record: Attendance):
        """
        Calculates derived fields for an attendance record.

        Key points of the algorithm:
        - leave_duration_minutes: minutes of leave overlapping with the attendance window (time_in..time_out)
        - launch_duration_minutes: minutes of launch (lunch) overlapping with the attendance window
        - duration_minutes: total minutes between time_in and time_out (if both present)
        - net_work_minutes = duration - launch_overlap - leave_overlap
        - tardiness_minutes = minutes late relative to configured base_start_time (or late_threshold_time)
        - main_work_minutes is computed so that (tardiness + main_work) == workday_minutes whenever possible:
            desired_main_work = max(0, workday_minutes - tardiness)
            main_work = min(net_work_minutes, desired_main_work)
        - overtime_minutes (IMPORTANT - per your request): overtime starts after
            time_in + workday_hours (i.e. lunch is NOT subtracted from overtime threshold).
            overtime = max(0, time_out - (time_in + workday_hours))
        """
        # Reset fields
        record.duration_minutes = None
        record.launch_duration_minutes = None
        record.leave_duration_minutes = None
        record.tardiness_minutes = None
        record.main_work_minutes = None
        record.overtime_minutes = None
        record.status = self.STATUS_ABSENT

        # If no time_in and leave exists, possibly mark on leave
        if not record.time_in:
            # compute leave_minutes even if no time_in (useful for leave-only records)
            leave_minutes = 0
            if record.leave_start and record.leave_end:
                try:
                    leave_dt_start = datetime.datetime.combine(record.date, record.leave_start)
                    leave_dt_end = datetime.datetime.combine(record.date, record.leave_end)
                    if leave_dt_end <= leave_dt_start:
                        # assume next day
                        leave_dt_end += datetime.timedelta(days=1)
                    leave_minutes = int((leave_dt_end - leave_dt_start).total_seconds() / 60)
                except Exception:
                    leave_minutes = 0
            record.leave_duration_minutes = int(leave_minutes)
            if record.leave_duration_minutes and not record.time_in:
                record.status = self.STATUS_ON_LEAVE
            return

        # Combine time_in/date
        dt_in = datetime.datetime.combine(record.date, record.time_in)

        # If time_out invalid or missing, set status partial after calculating tardiness and leave overlap if possible
        # Compute tardiness relative to configured base_start_time (fall back to late_threshold_time)
        base_start_str = config.settings.get("base_start_time", config.settings.get("late_threshold_time", "10:00"))
        try:
            bh, bm = map(int, base_start_str.split(':'))
            base_dt = dt_in.replace(hour=bh, minute=bm, second=0, microsecond=0)
            tardiness_minutes = int(max(0, (dt_in - base_dt).total_seconds() / 60))
        except Exception:
            tardiness_minutes = 0
        record.tardiness_minutes = int(tardiness_minutes)

        # If no valid time_out, leave other numeric values None and return partial
        if not (record.time_out and record.time_out > record.time_in):
            record.status = self.STATUS_PARTIAL
            # compute leave_duration_minutes if provided (full overlap with attendance window can't be computed without time_out)
            # but try to compute partial overlap if leave times exist
            leave_minutes = 0
            if record.leave_start and record.leave_end:
                try:
                    leave_dt_start = datetime.datetime.combine(record.date, record.leave_start)
                    leave_dt_end = datetime.datetime.combine(record.date, record.leave_end)
                    if leave_dt_end <= leave_dt_start:
                        leave_dt_end += datetime.timedelta(days=1)
                    # If only time_in exists, assume attendance window from dt_in to dt_in (0)
                    # So leave overlap is 0 in absence of time_out
                    leave_minutes = 0
                except Exception:
                    leave_minutes = 0
            record.leave_duration_minutes = int(leave_minutes)
            return

        # We have valid time_in and time_out
        dt_out = datetime.datetime.combine(record.date, record.time_out)
        if dt_out <= dt_in:
            # if time_out on next day (time_out <= time_in), assume next day
            dt_out += datetime.timedelta(days=1)

        # Total duration between in and out
        total_duration_minutes = int((dt_out - dt_in).total_seconds() / 60)
        record.duration_minutes = int(total_duration_minutes)

        # --- Leave overlap with attendance window
        leave_minutes = 0
        if record.leave_start and record.leave_end:
            try:
                leave_dt_start = datetime.datetime.combine(record.date, record.leave_start)
                leave_dt_end = datetime.datetime.combine(record.date, record.leave_end)
                if leave_dt_end <= leave_dt_start:
                    leave_dt_end += datetime.timedelta(days=1)
                overlap_start = max(dt_in, leave_dt_start)
                overlap_end = min(dt_out, leave_dt_end)
                if overlap_end > overlap_start:
                    leave_minutes = int((overlap_end - overlap_start).total_seconds() / 60)
            except Exception:
                leave_minutes = 0
        record.leave_duration_minutes = int(leave_minutes)

        # --- Launch (lunch) overlap calculation
        launch_minutes = 0
        try:
            start_str = config.settings.get("default_launch_start_time", "14:00")
            end_str = config.settings.get("default_launch_end_time", "16:00")
            h_start, m_start = map(int, start_str.split(':'))
            h_end, m_end = map(int, end_str.split(':'))
            launch_start_time = datetime.time(h_start, m_start)
            launch_end_time = datetime.time(h_end, m_end)
            launch_start_dt = datetime.datetime.combine(record.date, launch_start_time)
            launch_end_dt = datetime.datetime.combine(record.date, launch_end_time)
            if launch_end_dt <= launch_start_dt:
                launch_end_dt += datetime.timedelta(days=1)

            overlap_start = max(dt_in, launch_start_dt)
            overlap_end = min(dt_out, launch_end_dt)
            if overlap_end > overlap_start:
                launch_minutes = int((overlap_end - overlap_start).total_seconds() / 60)
        except Exception:
            launch_minutes = 0
        record.launch_duration_minutes = int(launch_minutes)

        # --- Net work = total duration - lunch overlap - leave overlap
        net_work_minutes = max(0, total_duration_minutes - launch_minutes - leave_minutes)

        # --- Workday minutes from config
        try:
            workday_hours = int(config.settings.get("workday_hours", 8))
        except Exception:
            workday_hours = 8
        workday_minutes = workday_hours * 60

        # --- Main work: ensure tardiness + main_work == workday when possible
        desired_main_work = max(0, workday_minutes - int(record.tardiness_minutes or 0))
        main_work_minutes = min(net_work_minutes, desired_main_work)
        record.main_work_minutes = int(main_work_minutes)

        # --- Overtime: per requested rule - overtime starts at (time_in + workday_hours)
        # Note: lunch is NOT subtracted from the overtime threshold (this matches the requirement)
        overtime_minutes = 0
        try:
            overtime_start_dt = dt_in + datetime.timedelta(minutes=workday_minutes)
            if dt_out > overtime_start_dt:
                overtime_minutes = int((dt_out - overtime_start_dt).total_seconds() / 60)
            else:
                overtime_minutes = 0
        except Exception:
            # fallback: compute overtime from net_work - workday
            overtime_minutes = max(0, net_work_minutes - workday_minutes)
        record.overtime_minutes = int(overtime_minutes)

        # Final status
        record.status = self.STATUS_PRESENT if (record.time_in and record.time_out) else self.STATUS_PARTIAL

    def _validate_leave_balance(self, employee_id: int, date: datetime.date, new_leave_minutes: int, db: Session, old_record: Attendance = None):
        """Checks if adding a leave record exceeds the employee's monthly allowance."""
        employee = employee_service.get_employee_by_id(employee_id, db=db)
        if not employee or getattr(employee, "monthly_leave_allowance_minutes", 0) <= 0:
            return # No limit set, so no need to check

        current_month_leave = self.get_monthly_leave_taken(employee_id, date, db)

        # If updating, subtract the old leave duration from the current total
        if old_record and getattr(old_record, "leave_duration_minutes", None):
            current_month_leave -= int(old_record.leave_duration_minutes)

        if current_month_leave + new_leave_minutes > employee.monthly_leave_allowance_minutes:
            raise LeaveBalanceExceededError(
                f"Exceeds monthly leave allowance of {employee.monthly_leave_allowance_minutes} minutes. "
                f"Current usage: {current_month_leave} minutes."
            )

    def add_manual_attendance(self, db: Optional[Session] = None, **kwargs) -> Attendance:
        managed = db is None
        db = db or self._get_session()
        try:
            if db.query(Attendance).filter(and_(Attendance.employee_id == kwargs['employee_id'], Attendance.date == kwargs['date'])).first():
                raise AttendanceAlreadyExistsError("Record already exists.")
            
            new_record = Attendance(**kwargs)
            self._calculate_all_fields(new_record)
            
            # Validate leave balance before adding
            if new_record.leave_duration_minutes and new_record.leave_duration_minutes > 0:
                self._validate_leave_balance(
                    employee_id=new_record.employee_id,
                    date=new_record.date,
                    new_leave_minutes=new_record.leave_duration_minutes,
                    db=db
                )

            db.add(new_record)
            db.commit()
            db.refresh(new_record)
            return new_record
        except Exception as e:
            db.rollback()
            logger.exception("Failed to add record.")
            raise AttendanceServiceError(f"Failed to add record: {e}") from e
        finally:
            if managed: db.close()

    def update_attendance(self, attendance_id: int, db: Optional[Session] = None, **kwargs) -> Attendance:
        managed = db is None
        db = db or self._get_session()
        try:
            record = db.query(Attendance).options(joinedload(Attendance.employee)).filter(Attendance.id == attendance_id).first()
            if not record: raise AttendanceNotFoundError("Record not found.")

            # Store old leave duration for validation
            old_leave_duration = int(record.leave_duration_minutes or 0)

            for key, value in kwargs.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            
            self._calculate_all_fields(record)
            
            # Validate leave balance before updating
            new_leave_duration = int(record.leave_duration_minutes or 0)
            if new_leave_duration > 0 or old_leave_duration > 0:
                 self._validate_leave_balance(
                    employee_id=record.employee_id,
                    date=record.date,
                    new_leave_minutes=new_leave_duration,
                    db=db,
                    old_record=Attendance(leave_duration_minutes=old_leave_duration) # temporary holder
                )

            db.commit()
            db.refresh(record)
            return record
        except Exception as e:
            db.rollback()
            logger.exception("Failed to update attendance.")
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
            logger.exception("Failed to delete attendance.")
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
            query = query.filter(Attendance.is_archived == False)
            return query.order_by(Attendance.date.desc(), Employee.last_name).all()
        finally:
            if managed: db.close()

    def get_archived_attendance_records(self, db: Optional[Session] = None, **filters) -> List[Attendance]:
        managed = db is None
        db = db or self._get_session()
        try:
            query = db.query(Attendance).join(Attendance.employee).options(joinedload(Attendance.employee))
            if filters.get('employee_id'): query = query.filter(Attendance.employee_id == filters['employee_id'])
            if filters.get('start_date'): query = query.filter(Attendance.date >= filters['start_date'])
            if filters.get('end_date'): query = query.filter(Attendance.date <= filters['end_date'])
            if filters.get('statuses'): query = query.filter(Attendance.status.in_(filters['statuses']))
            query = query.filter(Attendance.is_archived == True)
            return query.order_by(Attendance.date.desc(), Employee.last_name).all()
        finally:
            if managed: db.close()

    def unarchive_records(self, record_ids: List[int], db: Optional[Session] = None) -> int:
        managed = db is None
        db = db or self._get_session()
        try:
            updated_count = db.query(Attendance).filter(Attendance.id.in_(record_ids)).update({"is_archived": False}, synchronize_session=False)
            db.commit()
            return updated_count
        except Exception as e:
            db.rollback()
            logger.exception("Failed to unarchive records.")
            raise AttendanceServiceError(f"Failed to unarchive records: {e}") from e
        finally:
            if managed: db.close()
    
    def get_attendance_for_export(self, db: Optional[Session] = None, **filters) -> List[Dict]:
        needs_closing = db is None
        db = db or self._get_session()
        try:
            records = self.get_attendance_records(db=db, **filters)
            
            # Pre-calculate monthly leave for efficiency
            monthly_leave_cache = {}
            for r in records:
                start_of_period, _ = get_jalali_month_range(r.date)
                cache_key = (r.employee_id, start_of_period)
                if cache_key not in monthly_leave_cache:
                    monthly_leave_cache[cache_key] = self.get_monthly_leave_taken(r.employee_id, r.date, db)

            export_data = []
            for r in records:
                allowance = r.employee.monthly_leave_allowance_minutes if r.employee else 0
                start_of_period, _ = get_jalali_month_range(r.date)
                used_leave = monthly_leave_cache.get((r.employee_id, start_of_period), 0)
                remaining_leave = max(0, allowance - used_leave)

                export_data.append({
                    "Employee Name": f"{r.employee.first_name} {r.employee.last_name}".strip(),
                    "Date": r.date, "Time In": r.time_in, "Time Out": r.time_out,
                    "Leave (min)": r.leave_duration_minutes,
                    "Used Leave This Month (min)": used_leave,
                    "Remaining Leave This Month (min)": remaining_leave,
                    "Tardiness (min)": r.tardiness_minutes, 
                    "Main Work (min)": r.main_work_minutes,
                    "Overtime (min)": r.overtime_minutes, 
                    "Launch Time (min)": r.launch_duration_minutes,
                    "Total Duration (min)": r.duration_minutes,
                    "Status": r.status,
                    "Note": r.note or "",
                })
            return export_data
        finally:
            if needs_closing: db.close()

    def clock_in(self, employee_id: int, db: Optional[Session] = None) -> Attendance:
        managed = db is None
        db = db or self._get_session()
        try:
            today = datetime.date.today()
            now = datetime.datetime.now().time()
            
            record = db.query(Attendance).filter(and_(Attendance.employee_id == employee_id, Attendance.date == today)).first()
            
            if record and record.time_in and not record.time_out:
                raise AlreadyClockedInError("Employee is already clocked in today.")

            if record:
                record.time_in = now
            else:
                record = Attendance(employee_id=employee_id, date=today, time_in=now)
                db.add(record)
            
            self._calculate_all_fields(record)
            db.commit()
            db.refresh(record)
            return record
        except Exception as e:
            db.rollback()
            logger.exception("Failed to clock in.")
            raise AttendanceServiceError(f"Failed to clock in: {e}") from e
        finally:
            if managed: db.close()

    def clock_out(self, employee_id: int, db: Optional[Session] = None) -> Attendance:
        managed = db is None
        db = db or self._get_session()
        try:
            today = datetime.date.today()
            now = datetime.datetime.now().time()
            
            record = db.query(Attendance).filter(and_(Attendance.employee_id == employee_id, Attendance.date == today)).first()
            
            if not record or not record.time_in:
                raise NotClockedInError("Employee is not clocked in today.")
            
            if record.time_out:
                raise AttendanceServiceError("Employee has already clocked out today.")

            record.time_out = now
            self._calculate_all_fields(record)
            db.commit()
            db.refresh(record)
            return record
        except Exception as e:
            db.rollback()
            logger.exception("Failed to clock out.")
            raise AttendanceServiceError(f"Failed to clock out: {e}") from e
        finally:
            if managed: db.close()

    def get_daily_summary(self, date: datetime.date, db: Optional[Session] = None) -> Dict[str, int]:
        managed = db is None
        db = db or self._get_session()
        try:
            present_count = db.query(Attendance).filter(and_(Attendance.date == date, Attendance.status == self.STATUS_PRESENT)).count()
            
            total_employees = db.query(Employee).count()
            absent_count = total_employees - present_count
            
            return {"present": present_count, "absent": absent_count}
        finally:
            if managed: db.close()

attendance_service = AttendanceService()
