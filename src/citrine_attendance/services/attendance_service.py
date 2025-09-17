# src/citrine_attendance/services/attendance_service.py
import logging
import re
from typing import List, Optional, Dict
from sqlalchemy.orm import Session, joinedload, aliased
from sqlalchemy import and_, func
import datetime
from ..database import Attendance, Employee, get_db_session
from ..config import config
from .employee_service import employee_service
from ..date_utils import get_jalali_month_range
from ..locale import _

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
    STATUS_DISPLAY = {"present": "Present", "absent": "Absent", "on_leave": "On Leave", "partial": "Partial"}

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
        Robust calculation of derived attendance fields with correct leave, overtime, and early departure handling.
        """
        def _norm_digits(s: str) -> str:
            if s is None: return ""
            s = str(s).strip()
            trans = str.maketrans({
                '۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'7','۸':'8','۹':'9',
                '٠':'0','١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7','٨':'8','٩':'9'
            })
            return s.translate(trans)

        def _to_time(obj):
            if obj is None: return None
            if isinstance(obj, datetime.time): return obj
            s = _norm_digits(obj)
            if not s: return None
            try:
                parts = re.findall(r'\d+', s)
                if len(parts) >= 2:
                    h, m = int(parts[0]), int(parts[1])
                    if 0 <= h <= 23 and 0 <= m <= 59:
                        return datetime.time(h, m)
                raise ValueError(f"Bad time format: {s}")
            except Exception as e:
                logger.warning(f"Failed to parse time value '{obj}': {e}")
                return None

        # Reset fields
        record.duration_minutes = 0
        record.launch_duration_minutes = 0
        record.leave_duration_minutes = 0
        record.tardiness_minutes = 0
        record.early_departure_minutes = 0 # HEROIC
        record.main_work_minutes = 0
        record.overtime_minutes = 0
        record.status = self.STATUS_ABSENT

        time_in = _to_time(record.time_in)
        time_out = _to_time(record.time_out)
        leave_start = _to_time(record.leave_start)
        leave_end = _to_time(record.leave_end)
        
        workday_minutes = int(config.settings.get("workday_duration", 8)) * 60
        launch_start_time = _to_time(config.settings.get("default_launch_start_time", "14:00"))
        launch_end_time = _to_time(config.settings.get("default_launch_end_time", "15:30"))
        late_threshold_time = _to_time(config.settings.get("late_threshold", "10:00"))

        if not all([launch_start_time, launch_end_time, late_threshold_time]):
            logger.error("Could not parse critical time settings from config.")
            return

        def _normalize_interval(date_obj, t_start, t_end):
            s_dt = datetime.datetime.combine(date_obj, t_start)
            e_dt = datetime.datetime.combine(date_obj, t_end)
            if e_dt <= s_dt: e_dt += datetime.timedelta(days=1)
            return s_dt, e_dt

        def _overlap_minutes(a_start, a_end, b_start, b_end):
            start = max(a_start, b_start)
            end = min(a_end, b_end)
            return max(0, int((end - start).total_seconds() / 60))

        if leave_start and leave_end:
            ls_dt, le_dt = _normalize_interval(record.date, leave_start, leave_end)
            record.leave_duration_minutes = max(0, int((le_dt - ls_dt).total_seconds() / 60))

        if not time_in:
            if record.leave_duration_minutes > 0:
                record.status = self.STATUS_ON_LEAVE
            return

        dt_in = datetime.datetime.combine(record.date, time_in)
        late_threshold_dt = datetime.datetime.combine(record.date, late_threshold_time)
        record.tardiness_minutes = max(0, int((dt_in - late_threshold_dt).total_seconds() / 60))
        
        if not time_out:
            record.status = self.STATUS_PARTIAL
            return

        dt_out = datetime.datetime.combine(record.date, time_out)
        if dt_out <= dt_in: dt_out += datetime.timedelta(days=1)

        record.duration_minutes = int((dt_out - dt_in).total_seconds() / 60)
        
        launch_s_dt, launch_e_dt = _normalize_interval(record.date, launch_start_time, launch_end_time)
        record.launch_duration_minutes = _overlap_minutes(dt_in, dt_out, launch_s_dt, launch_e_dt)
        
        # HEROIC FIX: Implemented new overtime and early departure logic
        try:
            total_launch_duration = int((launch_e_dt - launch_s_dt).total_seconds() / 60)
            end_of_work_dt = late_threshold_dt + datetime.timedelta(minutes=(workday_minutes + total_launch_duration))

            if dt_out > end_of_work_dt:
                record.overtime_minutes = int((dt_out - end_of_work_dt).total_seconds() / 60)
                record.early_departure_minutes = 0
            elif dt_out < end_of_work_dt:
                record.early_departure_minutes = int((end_of_work_dt - dt_out).total_seconds() / 60)
                record.overtime_minutes = 0
            else:
                record.overtime_minutes = 0
                record.early_departure_minutes = 0

        except Exception as e:
            logger.warning(f"Overtime/Early Departure calculation failed, falling back to old method: {e}")
            net_work_minutes_fallback = record.duration_minutes - record.launch_duration_minutes - record.leave_duration_minutes
            record.overtime_minutes = max(0, net_work_minutes_fallback - workday_minutes)
            record.early_departure_minutes = 0 # No fallback for early departure

        net_work_minutes = record.duration_minutes - record.launch_duration_minutes - record.leave_duration_minutes
        record.main_work_minutes = max(0, net_work_minutes - record.overtime_minutes)
        
        record.status = self.STATUS_PRESENT

    def _validate_leave_balance(self, employee_id: int, date: datetime.date, new_leave_minutes: int, db: Session, old_record_id: Optional[int] = None):
        """Checks if adding a leave record exceeds the employee's monthly allowance."""
        employee = employee_service.get_employee_by_id(employee_id, db=db)
        if not employee or not employee.monthly_leave_allowance_minutes:
            return

        current_month_leave = self.get_monthly_leave_taken(employee_id, date, db)

        if old_record_id:
            old_record = db.query(Attendance.leave_duration_minutes).filter(Attendance.id == old_record_id).scalar()
            current_month_leave -= (old_record or 0)

        if current_month_leave + new_leave_minutes > employee.monthly_leave_allowance_minutes:
            raise LeaveBalanceExceededError(
                _("leave_exceeded_error", 
                  allowance=employee.monthly_leave_allowance_minutes,
                  current=current_month_leave)
            )

    def add_manual_attendance(self, db: Optional[Session] = None, **kwargs) -> Attendance:
        managed = db is None
        session = db or self._get_session()
        try:
            if session.query(Attendance).filter_by(employee_id=kwargs['employee_id'], date=kwargs['date']).first():
                raise AttendanceAlreadyExistsError(_("record_already_exists_for_date", date=kwargs['date']))
            
            new_record = Attendance(**kwargs)
            self._calculate_all_fields(new_record)
            
            if new_record.leave_duration_minutes > 0:
                self._validate_leave_balance(new_record.employee_id, new_record.date, new_record.leave_duration_minutes, session)

            session.add(new_record)
            session.commit()
            session.refresh(new_record)
            return new_record
        except Exception:
            session.rollback()
            raise
        finally:
            if managed: session.close()

    def update_attendance(self, attendance_id: int, db: Optional[Session] = None, **kwargs) -> Attendance:
        managed = db is None
        session = db or self._get_session()
        try:
            record = session.query(Attendance).filter_by(id=attendance_id).options(joinedload(Attendance.employee)).first()
            if not record: raise AttendanceNotFoundError("Record not found.")

            for key, value in kwargs.items():
                setattr(record, key, value)
            
            self._calculate_all_fields(record)
            
            if record.leave_duration_minutes > 0:
                 self._validate_leave_balance(record.employee_id, record.date, record.leave_duration_minutes, session, old_record_id=attendance_id)

            session.commit()
            session.refresh(record)
            return record
        except Exception:
            session.rollback()
            raise
        finally:
            if managed: session.close()

    def delete_attendance(self, attendance_id: int, db: Optional[Session] = None):
        managed = db is None
        session = db or self._get_session()
        try:
            record = session.query(Attendance).filter_by(id=attendance_id).first()
            if not record: raise AttendanceNotFoundError("Record not found.")
            session.delete(record)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            if managed: session.close()

    def get_attendance_records(self, db: Optional[Session] = None, **filters) -> List[Attendance]:
        managed = db is None
        session = db or self._get_session()
        try:
            employee_alias = aliased(Employee)
            query = session.query(Attendance).outerjoin(employee_alias, Attendance.employee)
            
            employee_id = filters.get('employee_id')
            start_date = filters.get('start_date')
            end_date = filters.get('end_date')

            if employee_id and start_date and end_date:
                query = query.filter(Attendance.employee_id == employee_id, Attendance.date.between(start_date, end_date))
                
                existing_records = query.all()
                existing_dates = {rec.date for rec in existing_records}
                
                all_records = list(existing_records)
                current_date = start_date
                while current_date <= end_date:
                    if current_date not in existing_dates:
                        placeholder = Attendance(employee_id=employee_id, date=current_date, status=self.STATUS_ABSENT)
                        all_records.append(placeholder)
                    current_date += datetime.timedelta(days=1)
                
                statuses = filters.get('statuses')
                if statuses:
                    all_records = [r for r in all_records if r.status in statuses]

                return sorted(all_records, key=lambda r: r.date, reverse=True)
            else:
                if filters.get('start_date'): query = query.filter(Attendance.date >= filters['start_date'])
                if filters.get('end_date'): query = query.filter(Attendance.date <= filters['end_date'])
                if filters.get('statuses'): query = query.filter(Attendance.status.in_(filters['statuses']))
                
                return query.order_by(Attendance.date.desc(), employee_alias.last_name).all()
        finally:
            if managed: session.close()


    def get_archived_attendance_records(self, db: Optional[Session] = None, **filters) -> List[Attendance]:
        managed = db is None
        session = db or self._get_session()
        try:
            employee_alias = aliased(Employee)
            query = session.query(Attendance).join(employee_alias, Attendance.employee)
            if filters.get('employee_id'): query = query.filter(Attendance.employee_id == filters['employee_id'])
            if filters.get('start_date'): query = query.filter(Attendance.date >= filters['start_date'])
            if filters.get('end_date'): query = query.filter(Attendance.date <= filters['end_date'])
            if filters.get('statuses'): query = query.filter(Attendance.status.in_(filters['statuses']))
            query = query.filter(Attendance.is_archived == True)
            return query.order_by(Attendance.date.desc(), employee_alias.last_name).all()
        finally:
            if managed: session.close()

    def unarchive_records(self, record_ids: List[int], db: Optional[Session] = None) -> int:
        managed = db is None
        session = db or self._get_session()
        try:
            updated_count = session.query(Attendance).filter(Attendance.id.in_(record_ids)).update({"is_archived": False})
            session.commit()
            return updated_count
        except Exception:
            session.rollback()
            raise
        finally:
            if managed: session.close()
    
    def get_attendance_for_export(self, db: Optional[Session] = None, **filters) -> List[Dict]:
        managed = db is None
        session = db or self._get_session()
        try:
            query = session.query(Attendance).options(joinedload(Attendance.employee))
            if filters.get('employee_id'): query = query.filter(Attendance.employee_id == filters['employee_id'])
            if filters.get('start_date'): query = query.filter(Attendance.date >= filters['start_date'])
            if filters.get('end_date'): query = query.filter(Attendance.date <= filters['end_date'])
            records = query.order_by(Attendance.date.desc()).all()

            if not records: return []

            monthly_leave_cache = {}
            unique_emp_dates = {(r.employee_id, r.date) for r in records}
            for emp_id, date_val in unique_emp_dates:
                # HEROIC FIX: Use a different variable name to avoid overwriting the '_' function
                start_of_period, _end_of_period = get_jalali_month_range(date_val)
                cache_key = (emp_id, start_of_period)
                if cache_key not in monthly_leave_cache:
                    monthly_leave_cache[cache_key] = self.get_monthly_leave_taken(emp_id, date_val, session)

            export_data = []
            for r in records:
                allowance = r.employee.monthly_leave_allowance_minutes if r.employee else 0
                # HEROIC FIX: Use a different variable name here as well
                start_of_period, _end_of_period = get_jalali_month_range(r.date)
                used_leave = monthly_leave_cache.get((r.employee_id, start_of_period), 0)
                
                export_data.append({
                    _("Employee Name"): f"{r.employee.first_name or ''} {r.employee.last_name or ''}".strip(),
                    _("Date"): r.date.isoformat(), 
                    _("Time In"): r.time_in.strftime("%H:%M") if r.time_in else "",
                    _("Time Out"): r.time_out.strftime("%H:%M") if r.time_out else "",
                    _("Leave (min)"): r.leave_duration_minutes or 0,
                    _("Used Leave This Month (min)"): used_leave,
                    _("Remaining Leave This Month (min)"): max(0, (allowance or 0) - used_leave),
                    _("Tardiness (min)"): r.tardiness_minutes or 0,
                    _("Early Departure (min)"): r.early_departure_minutes or 0, # HEROIC
                    _("Main Work (min)"): r.main_work_minutes or 0,
                    _("Overtime (min)"): r.overtime_minutes or 0, 
                    _("Launch Time (min)"): r.launch_duration_minutes or 0,
                    _("Total Duration (min)"): r.duration_minutes or 0,
                    _("Status"): self.STATUS_DISPLAY.get(r.status, r.status),
                    _("Note"): r.note or "",
                })
            return export_data
        finally:
            if managed: session.close()

    def clock_in(self, employee_id: int, db: Optional[Session] = None) -> Attendance:
        managed = db is None
        session = db or self._get_session()
        try:
            today = datetime.date.today()
            now = datetime.datetime.now().time().replace(second=0, microsecond=0)
            
            record = session.query(Attendance).filter_by(employee_id=employee_id, date=today).first()
            
            if record and record.time_in and not record.time_out:
                raise AlreadyClockedInError("Employee is already clocked in today.")

            if record:
                record.time_in = now
            else:
                record = Attendance(employee_id=employee_id, date=today, time_in=now)
                session.add(record)
            
            self._calculate_all_fields(record)
            session.commit()
            session.refresh(record)
            return record
        except Exception:
            session.rollback()
            raise
        finally:
            if managed: session.close()

    def clock_out(self, employee_id: int, db: Optional[Session] = None) -> Attendance:
        managed = db is None
        session = db or self._get_session()
        try:
            today = datetime.date.today()
            now = datetime.datetime.now().time().replace(second=0, microsecond=0)
            
            record = session.query(Attendance).filter_by(employee_id=employee_id, date=today).first()
            
            if not record or not record.time_in:
                raise NotClockedInError("Employee is not clocked in today.")
            
            if record.time_out:
                raise AttendanceServiceError("Employee has already clocked out today.")

            record.time_out = now
            self._calculate_all_fields(record)
            session.commit()
            session.refresh(record)
            return record
        except Exception:
            session.rollback()
            raise
        finally:
            if managed: session.close()

    def get_daily_summary(self, date: datetime.date, db: Optional[Session] = None) -> Dict[str, int]:
        managed = db is None
        session = db or self._get_session()
        try:
            present_count = session.query(Attendance).filter_by(date=date, status=self.STATUS_PRESENT).count()
            total_employees = session.query(Employee).count()
            
            return {"present": present_count, "absent": total_employees - present_count}
        finally:
            if managed: session.close()

attendance_service = AttendanceService()