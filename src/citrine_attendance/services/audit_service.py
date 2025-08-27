# src/citrine_attendance/services/audit_service.py
"""Service for handling audit logging."""
import json
import logging
from typing import Any, Dict

from ..database import AuditLog, get_db_session


class AuditServiceError(Exception):
    """Base exception for audit service errors."""
    pass

class AuditService:
    """Handles creating audit log entries."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def log_action(self, table_name: str, record_id: int, action: str, changes: Dict[str, Any], performed_by: str):
        """
        Log an action to the audit log.

        Args:
            table_name: The name of the table affected.
            record_id: The ID of the record affected.
            action: The action performed (create, update, delete).
            changes: A dictionary of changes made (for updates).
            performed_by: The username of the person who performed the action.
        """
        try:
            db_session_gen = get_db_session()
            db_session = next(db_session_gen)
            try:
                audit_entry = AuditLog(
                    table_name=table_name,
                    record_id=record_id,
                    action=action,
                    changes_json=json.dumps(changes, default=str), # Serialize changes
                    performed_by=performed_by
                )
                db_session.add(audit_entry)
                db_session.commit()
                self.logger.info(f"Audit log entry created: {table_name} {action} ID {record_id} by {performed_by}")
            except Exception as e:
                db_session.rollback()
                self.logger.error(f"Failed to create audit log entry: {e}", exc_info=True)
                raise AuditServiceError(f"Failed to log action: {e}") from e
            finally:
                db_session.close()
        except Exception as e:
            self.logger.error(f"Error getting DB session for audit log: {e}", exc_info=True)
            raise AuditServiceError(f"Failed to get DB session for audit log: {e}") from e


# Global instance
audit_service = AuditService()