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
        Robust calculation of derived attendance fields with correct leave handling.
        - Computes leave overlap with an appropriate work window (real attendance window or expected window).
        - Normalizes string times (supports Persian/Arabic digits).
        - Ensures overtime threshold is calculated after workday + launch + counted leave.
        """

        import datetime
        import logging
        logger = logging.getLogger(__name__)

        def _norm_digits(s: str) -> str:
            if s is None:
                return ""
            s = str(s).strip()
            trans = str.maketrans({
                '۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'7','۸':'8','۹':'9',
                '٠':'0','١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7','٨':'8','٩':'9'
            })
            return s.translate(trans)

        def _to_time(obj):
            """Return a datetime.time from either a datetime.time or a string 'HH:MM' (tolerant)."""
            if obj is None:
                return None
            if isinstance(obj, datetime.time):
                return obj
            s = _norm_digits(obj)
            if not s:
                return None
            try:
                parts = s.split(':')
                if len(parts) != 2:
                    # permissive parse (allow 'HHMM' or 'H:MM' variants)
                    import re
                    m = re.search(r'(\d{1,2}).?[:\u061b\-\. ]?(\d{1,2})', s)
                    if not m:
                        raise ValueError(f"Bad time format: {s}")
                    parts = [m.group(1), m.group(2)]
                h, m = int(parts[0]), int(parts[1])
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    raise ValueError(f"Time out of range: {s}")
                return datetime.time(h, m)
            except Exception as e:
                logger.warning(f"Failed to parse time value '{obj}': {e}")
                return None

        # Reset fields first (keep consistent types)
        record.duration_minutes = None
        record.launch_duration_minutes = None
        record.leave_duration_minutes = None
        record.tardiness_minutes = None
        record.main_work_minutes = None
        record.overtime_minutes = None
        record.status = self.STATUS_ABSENT

        # convert record times (handle strings from DB or None)
        time_in = _to_time(record.time_in)
        time_out = _to_time(record.time_out)
        leave_start = _to_time(record.leave_start)
        leave_end = _to_time(record.leave_end)

        # Workday minutes from config (default 8 hours)
        try:
            workday_hours = int(config.settings.get("workday_hours", 8))
        except Exception:
            workday_hours = 8
        workday_minutes = workday_hours * 60

        # --- Launch (lunch) overlap: tolerant config keys + digit normalization
        launch_candidates_start = [
            config.settings.get("default_launch_start_time"),
            config.settings.get("default_lunch_start_time"),
            config.settings.get("launch_start_time"),
            config.settings.get("launch_start"),
        ]
        launch_candidates_end = [
            config.settings.get("default_launch_end_time"),
            config.settings.get("default_lunch_end_time"),
            config.settings.get("launch_end_time"),
            config.settings.get("launch_end"),
        ]
        def _first_nonempty(lst, fallback):
            for x in lst:
                if x:
                    return x
            return fallback

        start_str = _first_nonempty(launch_candidates_start, "14:00")
        end_str = _first_nonempty(launch_candidates_end, "16:00")

        try:
            s = _norm_digits(start_str); e = _norm_digits(end_str)
            sh, sm = map(int, s.split(':')); eh, em = map(int, e.split(':'))
            launch_start_time = datetime.time(sh, sm)
            launch_end_time = datetime.time(eh, em)
        except Exception as e:
            logger.warning(f"Failed to parse launch times from settings '{start_str}'/'{end_str}': {e}")
            # defaults
            launch_start_time = datetime.time(14, 0)
            launch_end_time = datetime.time(16, 0)

        # Helper to compute overlap between two datetimes (returns minutes)
        def _overlap_minutes(a_start: datetime.datetime, a_end: datetime.datetime, b_start: datetime.datetime, b_end: datetime.datetime) -> int:
            start = max(a_start, b_start)
            end = min(a_end, b_end)
            return int((end - start).total_seconds() / 60) if end > start else 0

        # Helper to normalize leave interval datetimes (handles cross-day by adding day if end <= start)
        def _normalize_interval(date_obj: datetime.date, t_start: datetime.time, t_end: datetime.time):
            s_dt = datetime.datetime.combine(date_obj, t_start)
            e_dt = datetime.datetime.combine(date_obj, t_end)
            if e_dt <= s_dt:
                e_dt += datetime.timedelta(days=1)
            return s_dt, e_dt

        # If no time_in: handle "leave only" scenario by counting leave overlap with standard expected work window
        if not time_in:
            # default base start for expected window (use base_start_time or late_threshold_time or 09:00)
            base_start_str = config.settings.get("base_start_time", config.settings.get("late_threshold_time", "09:00"))
            try:
                bstr = _norm_digits(base_start_str)
                bh, bm = map(int, bstr.split(':'))
                base_start_time = datetime.time(bh, bm)
            except Exception as e:
                logger.warning(f"Failed to parse base start time '{base_start_str}': {e}")
                base_start_time = datetime.time(9, 0)

            # expected work window: base_start_time -> + workday + launch duration
            launch_s_dt, launch_e_dt = _normalize_interval(record.date, launch_start_time, launch_end_time)
            launch_minutes_full = int((launch_e_dt - launch_s_dt).total_seconds() / 60)

            expected_start_dt = datetime.datetime.combine(record.date, base_start_time)
            expected_end_dt = expected_start_dt + datetime.timedelta(minutes=(workday_minutes + launch_minutes_full))

            # compute leave overlap with expected window
            leave_minutes = 0
            if leave_start and leave_end:
                try:
                    ls_dt, le_dt = _normalize_interval(record.date, leave_start, leave_end)
                    leave_minutes = _overlap_minutes(expected_start_dt, expected_end_dt, ls_dt, le_dt)
                except Exception as e:
                    logger.warning(f"Error computing leave-only duration for record {getattr(record,'id',None)}: {e}")
                    leave_minutes = 0

            record.leave_duration_minutes = int(leave_minutes)
            # count launch duration as 0 when no clock-in (we only count launch when attendance exists)
            record.launch_duration_minutes = 0
            record.duration_minutes = 0
            record.tardiness_minutes = 0
            record.main_work_minutes = 0
            record.overtime_minutes = 0

            if record.leave_duration_minutes and record.leave_duration_minutes > 0:
                record.status = self.STATUS_ON_LEAVE
            else:
                record.status = self.STATUS_ABSENT
            return

        # Now we have time_in (whether time_out exists or not)
        try:
            dt_in = datetime.datetime.combine(record.date, time_in)
        except Exception as e:
            logger.exception(f"Invalid time_in for record {getattr(record,'id',None)}: {e}")
            return

        # tardiness: base start time comes from config: prefer base_start_time, fall back to late_threshold_time
        base_start_str = config.settings.get("base_start_time", config.settings.get("late_threshold_time", "09:00"))
        try:
            bstr = _norm_digits(base_start_str)
            bh, bm = map(int, bstr.split(':'))
            base_dt = datetime.datetime.combine(record.date, datetime.time(bh, bm))
            # If base time is logically after dt_in because dt_in rolled to next day, keep day aligned
            record.tardiness_minutes = int(max(0, (dt_in - base_dt).total_seconds() / 60))
        except Exception as e:
            logger.warning(f"Failed to parse base start/late threshold '{base_start_str}': {e}")
            record.tardiness_minutes = 0

        # Prepare launch interval for this date
        launch_start_dt = datetime.datetime.combine(record.date, launch_start_time)
        launch_end_dt = datetime.datetime.combine(record.date, launch_end_time)
        if launch_end_dt <= launch_start_dt:
            launch_end_dt += datetime.timedelta(days=1)
        launch_minutes_full = int((launch_end_dt - launch_start_dt).total_seconds() / 60)

        # If time_out missing: assume expected end (dt_in + workday + launch) for the purpose of calculating overlaps
        expected_dt_out = dt_in + datetime.timedelta(minutes=(workday_minutes + launch_minutes_full))

        if not time_out:
            # partial record: treat dt_out as expected end for overlap calculations but mark as partial
            dt_out = expected_dt_out
            is_partial = True
        else:
            dt_out = datetime.datetime.combine(record.date, time_out)
            if dt_out <= dt_in:
                dt_out += datetime.timedelta(days=1)
            is_partial = False

        # total duration between dt_in and dt_out (for stored actual clocked out records it's real; for missing time_out it's expected duration)
        total_duration_minutes = int((dt_out - dt_in).total_seconds() / 60)
        record.duration_minutes = int(total_duration_minutes)

        # --- Leave overlap
        # Robust logging and strict guards: leave is only counted when it intersects the attendance window [dt_in, dt_out]
        leave_minutes = 0
        if leave_start and leave_end:
            try:
                ls_dt, le_dt = _normalize_interval(record.date, leave_start, leave_end)

                # DEBUG: log the datetimes used so you can inspect them in logs
                logger.debug(
                    f"Computing leave overlap for record id={getattr(record,'id',None)} "
                    f"dt_in={dt_in.isoformat()} dt_out={dt_out.isoformat()} "
                    f"leave_start={ls_dt.isoformat()} leave_end={le_dt.isoformat()}"
                )

                # If the leave interval is completely outside attendance window, leave_minutes stays 0
                # Overlap function already does that, but we keep explicit check for clarity and to avoid accidental day shifts:
                if le_dt <= dt_in or ls_dt >= dt_out:
                    # no overlap
                    leave_minutes = 0
                    logger.debug(f"No leave overlap (leave outside attendance window) for record id={getattr(record,'id',None)}")
                else:
                    # compute the precise overlap
                    leave_minutes = _overlap_minutes(dt_in, dt_out, ls_dt, le_dt)
                    logger.debug(f"Leave overlap minutes computed={leave_minutes} for record id={getattr(record,'id',None)}")
            except Exception as e:
                logger.warning(f"Error computing leave overlap for record {getattr(record,'id',None)}: {e}")
                leave_minutes = 0
        record.leave_duration_minutes = int(leave_minutes)

        # --- Launch (lunch) overlap WITHIN the attendance window
        try:
            launch_overlap = _overlap_minutes(dt_in, dt_out, launch_start_dt, launch_end_dt)
            launch_minutes = int(launch_overlap)
        except Exception as e:
            logger.warning(f"Failed to compute launch overlap for record {getattr(record,'id',None)} using '{start_str}'/'{end_str}': {e}")
            launch_minutes = 0
        record.launch_duration_minutes = int(launch_minutes)

        # net work: total minus counted launch and counted leave (never negative)
        net_work_minutes = max(0, total_duration_minutes - launch_minutes - leave_minutes)

        # main work (ensures tardiness + main_work == workday when possible)
        desired_main_work = max(0, workday_minutes - int(record.tardiness_minutes or 0))
        main_work_minutes = min(net_work_minutes, desired_main_work)
        record.main_work_minutes = int(main_work_minutes)

        # --- Overtime: starts after workday_minutes + launch_minutes + counted leave_minutes
        overtime_minutes = 0
        try:
            overtime_threshold_dt = dt_in + datetime.timedelta(minutes=(workday_minutes + launch_minutes + leave_minutes))
            if dt_out > overtime_threshold_dt:
                overtime_minutes = int((dt_out - overtime_threshold_dt).total_seconds() / 60)
            else:
                overtime_minutes = 0
        except Exception as e:
            logger.warning(f"Overtime calc fallback for record {getattr(record,'id',None)}: {e}")
            overtime_minutes = max(0, net_work_minutes - workday_minutes)
        record.overtime_minutes = int(overtime_minutes)

        # status
        if total_duration_minutes > 0:
            # If the employee has no real clock-out (we used expected_dt_out), consider status partial unless leave covers full expected work window
            if is_partial:
                # if leave covered the entire expected window, mark on_leave
                if leave_minutes >= (workday_minutes):
                    record.status = self.STATUS_ON_LEAVE
                else:
                    record.status = self.STATUS_PARTIAL
            else:
                record.status = self.STATUS_PRESENT
        else:
            record.status = self.STATUS_ABSENT

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
