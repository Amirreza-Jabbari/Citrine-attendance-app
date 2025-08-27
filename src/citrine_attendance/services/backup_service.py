# src/citrine_attendance/services/backup_service.py
"""Service for handling database backups."""
import gzip
import shutil
import logging
import os
from pathlib import Path
from datetime import datetime
import tempfile

from ..database import engine, BackupRecord
from ..config import config
from sqlalchemy.orm import sessionmaker


class BackupServiceError(Exception):
    """Base exception for backup service errors."""
    pass

class BackupService:
    """Handles creating, listing, and restoring database backups."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_backup_dir(self) -> Path:
        """Get the path to the backups directory."""
        backup_dir = config.user_data_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    def create_backup(self, manual: bool = False) -> Path:
        """
        Create a timestamped backup of the database.
        Returns the path to the created backup file.
        """
        try:
            # Ensure backup directory exists
            backup_dir = self.get_backup_dir()

            # Get current DB path
            db_path = config.get_db_path()
            if not db_path.exists():
                raise BackupServiceError(f"Source database file not found: {db_path}")

            # Create timestamped filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"attendance_{timestamp}.db.gz"
            backup_path = backup_dir / backup_filename

            # Perform the backup: compress the DB file
            with open(db_path, 'rb') as f_in:
                with gzip.open(backup_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Get file size
            size_bytes = backup_path.stat().st_size

            # Record the backup in the database
            # Use a new session to avoid conflicts
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            db_session = SessionLocal()
            try:
                backup_record = BackupRecord(
                    file_name=backup_filename,
                    file_path=str(backup_path),
                    size_bytes=size_bytes,
                    encrypted=False # TODO: Implement encryption logic
                )
                db_session.add(backup_record)
                db_session.commit()
                self.logger.info(f"Backup created: {backup_path} (Size: {size_bytes} bytes)")
            except Exception as e:
                db_session.rollback()
                self.logger.error(f"Failed to record backup in DB: {e}", exc_info=True)
                # Don't fail the backup process if recording fails, but log it
            finally:
                db_session.close()

            # Enforce retention policy
            self._enforce_retention_policy()

            return backup_path

        except Exception as e:
            self.logger.error(f"Error creating backup: {e}", exc_info=True)
            raise BackupServiceError(f"Failed to create backup: {e}") from e

    def list_backups(self):
        """Retrieve a list of backup records from the database."""
        # Use a new session
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db_session = SessionLocal()
        try:
            backups = db_session.query(BackupRecord).order_by(BackupRecord.created_at.desc()).all()
            # Convert to list of dicts or objects as needed by UI
            return backups
        except Exception as e:
            self.logger.error(f"Error listing backups: {e}", exc_info=True)
            raise BackupServiceError(f"Failed to list backups: {e}") from e
        finally:
            db_session.close()

    def restore_backup(self, backup_id: int):
        """
        Restore the database from a specific backup.
        This is a critical operation.
        """
        try:
            # Use a new session
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            db_session = SessionLocal()
            try:
                backup_record = db_session.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
                if not backup_record:
                    raise BackupServiceError(f"Backup record with ID {backup_id} not found.")

                backup_path = Path(backup_record.file_path)
                if not backup_path.exists():
                    raise BackupServiceError(f"Backup file not found: {backup_path}")

                db_path = config.get_db_path()

                # --- CRITICAL: Close all database connections ---
                # This is tricky in a single-threaded app with Qt.
                # SQLAlchemy engine holds connections.
                # For simplicity, and because this is a desktop app,
                # we will assume the main app logic stops database interaction
                # before calling restore. The main window should warn/disallow
                # other actions during restore.
                # A more robust solution involves a central connection manager.

                # Perform the restore: decompress the backup file to DB location
                # Use a temporary file to ensure atomicity
                temp_db_path = db_path.with_suffix(db_path.suffix + '.tmp')
                try:
                    with gzip.open(backup_path, 'rb') as f_in:
                        with open(temp_db_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)

                    # Atomically replace the old DB file
                    # On Windows, replace() might fail if the file is locked.
                    # Ensure the main app has closed its session/pool.
                    shutil.move(temp_db_path, db_path) # replace or move

                    self.logger.info(f"Database restored from backup: {backup_path}")

                except Exception as restore_error:
                    # Clean up temp file if it exists
                    if temp_db_path.exists():
                        temp_db_path.unlink()
                    raise restore_error

            finally:
                db_session.close()

        except Exception as e:
            self.logger.error(f"Error restoring backup ID {backup_id}: {e}", exc_info=True)
            raise BackupServiceError(f"Failed to restore backup: {e}") from e

    def delete_backup(self, backup_id: int):
        """Delete a specific backup file and its record."""
        try:
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            db_session = SessionLocal()
            try:
                backup_record = db_session.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
                if not backup_record:
                    raise BackupServiceError(f"Backup record with ID {backup_id} not found for deletion.")

                backup_path = Path(backup_record.file_path)
                # Delete the file
                if backup_path.exists():
                    backup_path.unlink()
                    self.logger.info(f"Backup file deleted: {backup_path}")
                else:
                    self.logger.warning(f"Backup file not found for deletion (record deleted): {backup_path}")

                # Delete the record
                db_session.delete(backup_record)
                db_session.commit()
                self.logger.info(f"Backup record ID {backup_id} deleted from database.")

            except Exception as e:
                db_session.rollback()
                raise e
            finally:
                db_session.close()

        except Exception as e:
            self.logger.error(f"Error deleting backup ID {backup_id}: {e}", exc_info=True)
            raise BackupServiceError(f"Failed to delete backup: {e}") from e

    def _enforce_retention_policy(self):
        """Delete old backups based on the configured retention count."""
        try:
            retention_count = config.settings.get("backup_retention_count", 10)
            if retention_count <= 0:
                self.logger.debug("Backup retention count is 0 or negative, skipping cleanup.")
                return

            backups = self.list_backups()
            if len(backups) > retention_count:
                backups_to_delete = backups[retention_count:]
                self.logger.info(f"Enforcing retention policy: deleting {len(backups_to_delete)} old backups.")
                for backup in backups_to_delete:
                    try:
                        self.delete_backup(backup.id)
                    except BackupServiceError as e:
                        self.logger.warning(f"Failed to delete old backup (ID: {backup.id}): {e}")

        except Exception as e:
            # Don't let retention policy errors break the main backup creation
            self.logger.error(f"Error enforcing retention policy: {e}", exc_info=True)


# Global instance
backup_service = BackupService()