# src/citrine_attendance/services/attendance_service.py
"""
Service layer for managing attendance records.
Handles clock-in/out, manual entry/editing, calculations, and data retrieval.
"""
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import datetime
from ..database import Attendance, Employee, get_db_session
import jdatetime # Assuming jdatetime is available


class AttendanceServiceError(Exception):
    """Base exception for attendance service errors."""
    pass

class AttendanceNotFoundError(AttendanceServiceError):
    """Raised when an attendance record is not found."""
    pass

class AttendanceAlreadyExistsError(AttendanceServiceError):
    """Raised if trying to create a conflicting record (e.g., clock-in when already clocked in for the day)."""
    pass

class AttendanceService:
    """Service class to handle attendance-related business logic."""

    # --- Status Definitions (aligned with proposal, but modified to remove late/halfday) ---
    STATUS_PRESENT = "present"
    STATUS_ABSENT = "absent"
    # STATUS_LATE = "late"  # Removed
    # STATUS_HALFDAY = "halfday"  # Removed

    # --- Constants for status display names (updated) ---
    STATUS_DISPLAY = {
        STATUS_PRESENT: "Present",
        STATUS_ABSENT: "Absent",
        # Late and Half Day entries removed
    }

    # --- Configuration (could be moved to settings later) ---
    # Standard work start time (9:00 AM) - Kept for potential future use or logic reference
    STANDARD_START_TIME = datetime.time(9, 0)
    # Threshold for being marked 'late' (30 minutes past start time) - Removed logic, kept for reference
    # LATE_THRESHOLD_MINUTES = 30
    # Threshold for being considered a 'halfday' (4 hours = 240 minutes) - Removed logic, kept for reference
    # HALFDAY_MINUTES_THRESHOLD = 240

    def __init__(self):
        """Initialize the service."""
        pass

    def _get_session(self) -> Session:
        """Helper to get a database session."""
        session_gen = get_db_session()
        return next(session_gen)

    # --- Core Attendance Actions (Clock In/Out) ---

    def clock_in(self, employee_id: int, clock_in_time: Optional[datetime.datetime] = None, db: Optional[Session] = None) -> Attendance:
        """
        Record a clock-in for an employee.

        Args:
            employee_id (int): The ID of the employee.
            clock_in_time (datetime.datetime, optional): The clock-in time.
                Defaults to datetime.now() if None.
            db (Session, optional): Database session. If None, a new one is created.

        Returns:
            Attendance: The created or updated Attendance record.

        Raises:
            AttendanceServiceError: If clock-in fails (e.g., already clocked in).
            EmployeeNotFoundError: If the employee ID is invalid (implicitly via DB).
        """
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            if clock_in_time is None:
                clock_in_time = datetime.datetime.now()

            # --- Rule: Prevent duplicate clock-in on the same day ---
            existing_today_record = db.query(Attendance).filter(
                and_(
                    Attendance.employee_id == employee_id,
                    Attendance.date == clock_in_time.date(),
                    Attendance.time_in != None
                )
            ).first()

            if existing_today_record:
                raise AttendanceAlreadyExistsError(
                    f"Employee ID {employee_id} is already clocked in for {clock_in_time.date()}.")

            # --- Find or Create the attendance record for the day ---
            attendance_record = db.query(Attendance).filter(
                and_(
                    Attendance.employee_id == employee_id,
                    Attendance.date == clock_in_time.date()
                )
            ).first()

            if not attendance_record:
                # Create a new record for the day
                attendance_record = Attendance(
                    employee_id=employee_id,
                    date=clock_in_time.date(),
                    created_by="system_clock_in" # Placeholder, should come from context
                )
                db.add(attendance_record)
                logging.debug(f"Created new attendance record for employee ID {employee_id} on {clock_in_time.date()}.")

            # --- Update the record with clock-in time ---
            # This handles cases where a record exists but time_in was None (e.g., clocked out first)
            attendance_record.time_in = clock_in_time.time()
            # Reset time_out and derived fields as this is a new session start
            attendance_record.time_out = None
            attendance_record.duration_minutes = None
            attendance_record.status = self.STATUS_ABSENT # Reset status, will be finalized on clock-out

            db.commit()
            db.refresh(attendance_record)
            logging.info(f"Clock-in recorded for employee ID {employee_id} at {clock_in_time}.")
            return attendance_record

        except AttendanceAlreadyExistsError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logging.error(f"Error recording clock-in for employee ID {employee_id}: {e}", exc_info=True)
            raise AttendanceServiceError(f"Failed to record clock-in: {e}") from e
        finally:
            if managed_session:
                db.close()

    def clock_out(self, employee_id: int, clock_out_time: Optional[datetime.datetime] = None, db: Optional[Session] = None) -> Attendance:
        """
        Record a clock-out for an employee.

        Args:
            employee_id (int): The ID of the employee.
            clock_out_time (datetime.datetime, optional): The clock-out time.
                Defaults to datetime.now() if None.
            db (Session, optional): Database session. If None, a new one is created.

        Returns:
            Attendance: The updated Attendance record.

        Raises:
            AttendanceServiceError: If clock-out fails (e.g., invalid time, already clocked out).
            EmployeeNotFoundError: If the employee ID is invalid.
        """
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            if clock_out_time is None:
                clock_out_time = datetime.datetime.now()

            # --- Find the attendance record for the day ---
            attendance_record = db.query(Attendance).filter(
                and_(
                    Attendance.employee_id == employee_id,
                    Attendance.date == clock_out_time.date()
                )
            ).first()

            if not attendance_record:
                # Create a new record if none exists for the day (clock-out without clock-in)
                logging.warning(f"Clock-out recorded for employee ID {employee_id} without prior clock-in on {clock_out_time.date()}. Creating record.")
                attendance_record = Attendance(
                    employee_id=employee_id,
                    date=clock_out_time.date(),
                    time_in=None, # No clock-in recorded
                    created_by="system_clock_out" # Placeholder, should come from context
                )
                db.add(attendance_record)

            elif attendance_record.time_out:
                # Already clocked out
                raise AttendanceServiceError(f"Employee ID {employee_id} is already clocked out for {clock_out_time.date()}.")

            # --- Validate clock-out time ---
            if attendance_record.time_in and clock_out_time.time() <= attendance_record.time_in:
                raise AttendanceServiceError("Clock-out time must be after clock-in time.")

            # --- Update the record ---
            attendance_record.time_out = clock_out_time.time()
            # Calculate duration and determine status based on simplified rules
            self._calculate_duration_and_status(attendance_record) # Logic inside this method is updated

            db.commit()
            db.refresh(attendance_record)
            logging.info(f"Clock-out recorded for employee ID {employee_id} at {clock_out_time}. Status: {attendance_record.status}")
            return attendance_record

        except AttendanceServiceError: # Catches our custom errors and validation errors
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logging.error(f"Error recording clock-out for employee ID {employee_id}: {e}", exc_info=True)
            raise AttendanceServiceError(f"Failed to record clock-out: {e}") from e
        finally:
            if managed_session:
                db.close()

    def _calculate_duration_and_status(self, attendance_record: Attendance):
        """
        Calculates duration in minutes and determines status.
        Simplified logic: Present if both times exist and out > in, Absent otherwise.

        Status Logic (Updated):
        1. If both time_in and time_out exist and time_out > time_in:
           - Calculate duration.
           - Status = 'present'.
        2. In all other cases (missing times, invalid times): Status = 'absent'.
        """
        try:
            # Reset calculated fields
            attendance_record.duration_minutes = None
            attendance_record.status = self.STATUS_ABSENT # Default

            if (attendance_record.time_in and attendance_record.time_out and
                attendance_record.time_out > attendance_record.time_in):
                # Combine date and time for calculation
                dt_in = datetime.datetime.combine(attendance_record.date, attendance_record.time_in)
                dt_out = datetime.datetime.combine(attendance_record.date, attendance_record.time_out)

                # Calculate duration
                duration_td = dt_out - dt_in
                duration_minutes = int(duration_td.total_seconds() / 60)
                attendance_record.duration_minutes = duration_minutes

                # Set status to present as duration is positive
                attendance_record.status = self.STATUS_PRESENT

            # If conditions are not met, status remains 'absent' (default set above)
            # This covers cases like:
            # - Only time_in or only time_out
            # - time_out <= time_in
            # - times are None

        except Exception as e:
            logging.error(f"Error calculating duration/status for record ID {attendance_record.id}: {e}", exc_info=True)
            # On calculation error, ensure status is absent
            attendance_record.duration_minutes = None
            attendance_record.status = self.STATUS_ABSENT

    # --- Manual Record Management ---

    def add_manual_attendance(self, employee_id: int, date: datetime.date,
                              time_in: Optional[datetime.time] = None,
                              time_out: Optional[datetime.time] = None,
                              note: Optional[str] = None,
                              created_by: str = "manual_entry", # Should ideally come from user context
                              db: Optional[Session] = None) -> Attendance:
        """
        Add a manual attendance record.

        Args:
            employee_id (int): The ID of the employee.
            date (datetime.date): The date of the attendance.
            time_in (datetime.time, optional): Clock-in time.
            time_out (datetime.time, optional): Clock-out time.
            note (str, optional): An optional note.
            created_by (str): Identifier for who created the record.
            db (Session, optional): Database session.

        Returns:
            Attendance: The created Attendance record.

        Raises:
            AttendanceAlreadyExistsError: If a record for that employee/date already exists.
            AttendanceServiceError: For other creation errors.
        """
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            # Check for existing record to prevent duplicates
            existing_record = db.query(Attendance).filter(
                and_(
                    Attendance.employee_id == employee_id,
                    Attendance.date == date
                )
            ).first()

            if existing_record:
                raise AttendanceAlreadyExistsError(
                    f"Attendance record already exists for employee ID {employee_id} on {date}. Use update instead."
                )

            # Validate time logic if both times are provided
            if time_in and time_out and time_out <= time_in:
                 raise AttendanceServiceError("Manual entry: Clock-out time must be after clock-in time.")

            new_record = Attendance(
                employee_id=employee_id,
                date=date,
                time_in=time_in,
                time_out=time_out,
                note=note,
                created_by=created_by
            )
            # Calculate duration and status for the new manual record using updated logic
            self._calculate_duration_and_status(new_record)
            db.add(new_record)
            db.commit()
            db.refresh(new_record)
            logging.info(f"Manual attendance record added for employee ID {employee_id} on {date}.")
            return new_record

        except AttendanceAlreadyExistsError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logging.error(f"Error adding manual attendance for employee ID {employee_id} on {date}: {e}", exc_info=True)
            raise AttendanceServiceError(f"Failed to add manual attendance: {e}") from e
        finally:
            if managed_session:
                db.close()

    def update_attendance(self, attendance_id: int,
                          time_in: Optional[datetime.time] = None,
                          time_out: Optional[datetime.time] = None,
                          note: Optional[str] = None,
                          db: Optional[Session] = None) -> Attendance:
        """
        Update an existing attendance record.

        Args:
            attendance_id (int): The ID of the attendance record to update.
            time_in (datetime.time, optional): New clock-in time.
            time_out (datetime.time, optional): New clock-out time.
            note (str, optional): New note.
            db (Session, optional): Database session.

        Returns:
            Attendance: The updated Attendance record.

        Raises:
            AttendanceNotFoundError: If the record ID is not found.
            AttendanceServiceError: For update errors or validation failures.
        """
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            record = db.query(Attendance).filter(Attendance.id == attendance_id).first()
            if not record:
                raise AttendanceNotFoundError(f"Attendance record with ID {attendance_id} not found.")

            # Update fields if provided
            # Store original times for validation
            original_time_in = record.time_in
            original_time_out = record.time_out

            if time_in is not None:
                record.time_in = time_in
            if time_out is not None:
                record.time_out = time_out
            if note is not None:
                record.note = note

            # --- Validate updated times ---
            # Add validation: time_out must be after time_in if both exist
            # Handle cases where only one time is being updated
            final_time_in = record.time_in
            final_time_out = record.time_out

            if final_time_in and final_time_out and final_time_out <= final_time_in:
                # Revert changes if validation fails
                record.time_in = original_time_in
                record.time_out = original_time_out
                raise AttendanceServiceError("Updated clock-out time must be after clock-in time.")

            # Recalculate duration and status based on updated times using simplified logic
            self._calculate_duration_and_status(record)
            # updated_at is handled by the ORM

            db.commit()
            db.refresh(record)
            logging.info(f"Attendance record ID {attendance_id} updated.")
            return record

        except (AttendanceNotFoundError, AttendanceServiceError): # Catch our specific errors
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logging.error(f"Error updating attendance record ID {attendance_id}: {e}", exc_info=True)
            raise AttendanceServiceError(f"Failed to update attendance: {e}") from e
        finally:
            if managed_session:
                db.close()

    def delete_attendance(self, attendance_id: int, db: Optional[Session] = None):
        """
        Delete an attendance record.

        Args:
            attendance_id (int): The ID of the attendance record to delete.
            db (Session, optional): Database session.

        Raises:
            AttendanceNotFoundError: If the record ID is not found.
            AttendanceServiceError: For deletion errors.
        """
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            record = db.query(Attendance).filter(Attendance.id == attendance_id).first()
            if not record:
                raise AttendanceNotFoundError(f"Attendance record with ID {attendance_id} not found for deletion.")

            db.delete(record)
            db.commit()
            logging.info(f"Deleted attendance record ID {attendance_id}.")

        except AttendanceNotFoundError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logging.error(f"Error deleting attendance record ID {attendance_id}: {e}", exc_info=True)
            raise AttendanceServiceError(f"Failed to delete attendance: {e}") from e
        finally:
            if managed_session:
                db.close()

    # --- Data Retrieval ---

    def get_attendance_records(self, employee_id: Optional[int] = None,
                               start_date: Optional[datetime.date] = None,
                               end_date: Optional[datetime.date] = None,
                               statuses: Optional[List[str]] = None,
                               db: Optional[Session] = None) -> List[Attendance]:
        """
        Retrieve attendance records based on optional filters.

        Args:
            employee_id (int, optional): Filter by employee ID.
            start_date (datetime.date, optional): Filter records on or after this date.
            end_date (datetime.date, optional): Filter records on or before this date.
            statuses (List[str], optional): Filter by list of statuses (e.g., ['present', 'absent']).
                                            Note: 'late' and 'halfday' are no longer valid statuses.
            db (Session, optional): Database session.

        Returns:
            List[Attendance]: A list of Attendance records matching the filters.
        """
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            query = db.query(Attendance)

            if employee_id:
                query = query.filter(Attendance.employee_id == employee_id)
            if start_date:
                query = query.filter(Attendance.date >= start_date)
            if end_date:
                query = query.filter(Attendance.date <= end_date)
            if statuses:
                # Filter by the provided list of statuses (e.g., ['present', 'absent'])
                query = query.filter(Attendance.status.in_(statuses))

            # Order by date descending, then by employee ID for consistency
            records = query.order_by(Attendance.date.desc(), Attendance.employee_id).all()
            return records

        except Exception as e:
            logging.error(f"Error retrieving attendance records: {e}", exc_info=True)
            raise AttendanceServiceError(f"Failed to retrieve attendance records: {e}") from e
        finally:
            if managed_session:
                db.close()

    def get_attendance_by_id(self, attendance_id: int, db: Optional[Session] = None) -> Optional[Attendance]:
        """
        Retrieve a single attendance record by its ID.

        Args:
            attendance_id (int): The ID of the attendance record.
            db (Session, optional): Database session.

        Returns:
            Attendance or None: The Attendance record if found, otherwise None.
        """
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            record = db.query(Attendance).filter(Attendance.id == attendance_id).first()
            return record
        finally:
            if managed_session:
                db.close()

    # --- Aggregations & Summaries ---

    def get_daily_summary(self, target_date: datetime.date, db: Optional[Session] = None) -> dict:
        """
        Get a summary of attendance for a specific date.

        Args:
            target_date (datetime.date): The date for which to get the summary.
            db (Session, optional): Database session.

        Returns:
            dict: A dictionary containing counts for present and absent.
                  Late and Half Day counts are always 0.
        """
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False

        try:
            # Query the database for counts
            present_count = db.query(Attendance).filter(
                and_(Attendance.date == target_date, Attendance.status == self.STATUS_PRESENT)
            ).count()
            absent_count = db.query(Attendance).filter(
                and_(Attendance.date == target_date, Attendance.status == self.STATUS_ABSENT)
            ).count()
            # late_count and halfday_count are no longer relevant, set to 0
            late_count = 0
            halfday_count = 0

            return {
                "date": target_date,
                "present": present_count,
                "late": late_count, # 0
                "absent": absent_count,
                "halfday": halfday_count # 0
            }
        finally:
            if managed_session:
                db.close()

    # --- Export Helper Method ---
    def get_attendance_for_export(self, employee_id=None, start_date=None, end_date=None, statuses=None, db=None):
        """
        Fetches attendance data suitable for export (list of dictionaries).
        Applies filters based on provided arguments.
        """
        # Ensure we have a database session
        if db is None:
            db = self._get_session()
            needs_closing = True
        else:
            needs_closing = False

        try:
            query = db.query(Attendance).join(Employee) # Join with Employee for name

            # Apply filters
            if employee_id:
                query = query.filter(Attendance.employee_id == employee_id)
            if start_date:
                query = query.filter(Attendance.date >= start_date)
            if end_date:
                query = query.filter(Attendance.date <= end_date)
            if statuses:
                query = query.filter(Attendance.status.in_(statuses))

            attendance_records = query.all()

            # --- Prepare data for export ---
            export_data = []
            for attendance_record in attendance_records:
                employee = attendance_record.employee # Get employee from relationship
                employee_name = f"{employee.first_name} {employee.last_name}".strip()
                if not employee_name:
                    employee_name = employee.email

                # --- Use the STATUS_DISPLAY mapping (now without late/halfday) ---
                status_display_name = self.STATUS_DISPLAY.get(attendance_record.status, attendance_record.status)

                export_data.append({
                    "Employee Name": employee_name,
                    "Employee ID": employee.employee_id or "", # Include optional employee_id
                    "Email": employee.email,
                    "Date": attendance_record.date, # Will be converted by export service
                    "Time In": attendance_record.time_in,
                    "Time Out": attendance_record.time_out,
                    "Duration (Minutes)": attendance_record.duration_minutes or 0,
                    "Status": status_display_name, # Use the display name
                    "Note": attendance_record.note or "",
                    # Consider adding created/updated by/at if needed in exports
                })
            return export_data

        except Exception as e:
            # Note: self.logger doesn't exist in this service class, using module-level logging
            logging.error(f"Error retrieving attendance for export: {e}", exc_info=True)
            raise AttendanceServiceError(f"Failed to retrieve data for export: {e}") from e
        finally:
            if needs_closing:
                db.close()

    # --- Archive Methods ---
    def archive_records(self, record_ids: List[int], db: Session = None):
        """Mark a list of attendance records as archived."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False
        try:
            # Update records where ID is in the list and not already archived
            updated_count = db.query(Attendance).filter(
                and_(Attendance.id.in_(record_ids), Attendance.is_archived == False)
            ).update({Attendance.is_archived: True}, synchronize_session=False)
            db.commit()
            logging.info(f"Archived {updated_count} attendance records.")
            return updated_count
        except Exception as e:
            db.rollback()
            logging.error(f"Error archiving records: {e}", exc_info=True)
            raise AttendanceServiceError(f"Failed to archive records: {e}") from e
        finally:
            if managed_session:
                db.close()

    def unarchive_records(self, record_ids: List[int], db: Session = None):
        """Mark a list of attendance records as NOT archived."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False
        try:
            # Update records where ID is in the list and currently archived
            updated_count = db.query(Attendance).filter(
                and_(Attendance.id.in_(record_ids), Attendance.is_archived == True)
            ).update({Attendance.is_archived: False}, synchronize_session=False)
            db.commit()
            logging.info(f"Unarchived {updated_count} attendance records.")
            return updated_count
        except Exception as e:
            db.rollback()
            logging.error(f"Error unarchiving records: {e}", exc_info=True)
            raise AttendanceServiceError(f"Failed to unarchive records: {e}") from e
        finally:
            if managed_session:
                db.close()

    def get_archived_attendance_records(self, employee_id: int = None,
                                        start_date: datetime.date = None,
                                        end_date: datetime.date = None,
                                        db: Session = None) -> List[Attendance]:
        """Retrieve archived attendance records based on optional filters."""
        if db is None:
            db = self._get_session()
            managed_session = True
        else:
            managed_session = False
        try:
            query = db.query(Attendance).filter(Attendance.is_archived == True)
            if employee_id:
                query = query.filter(Attendance.employee_id == employee_id)
            if start_date:
                query = query.filter(Attendance.date >= start_date)
            if end_date:
                query = query.filter(Attendance.date <= end_date)
            records = query.order_by(Attendance.date.desc(), Attendance.employee_id).all()
            return records
        except Exception as e:
            logging.error(f"Error retrieving archived attendance records: {e}", exc_info=True)
            raise AttendanceServiceError(f"Failed to retrieve archived records: {e}") from e
        finally:
            if managed_session:
                db.close()


# Global instance for easy access throughout the application
attendance_service = AttendanceService()