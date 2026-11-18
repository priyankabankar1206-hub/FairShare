"""Audit Logging Service (Section 6.6 & Section 7.2).

Logs security-relevant and privacy events, such as member consent decisions,
analysis access, and team data deletion requests.

NOTE FOR DATABASE TEAMMATE:
Once the `audit_log` table (id, actor_id, action, target, at) is ready in SQLAlchemy,
the `persist_to_database` hook below can be wired to your ORM repository.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

logger = logging.getLogger("fairshare.audit")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


class AuditLogRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"aud_{uuid.uuid4().hex[:12]}")
    actor_id: str
    action: str
    target: str
    details: Dict[str, Any] = Field(default_factory=dict)
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditLogService:
    """Service capturing audit logs in compliance with Section 6.6."""

    def __init__(self):
        self._in_memory_logs: List[AuditLogRecord] = []

    def log_action(
        self,
        actor_id: str,
        action: str,
        target: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create and record an audit log entry.

        Args:
            actor_id: Identifier of the user or system component performing the action.
            action: Standard action verb (e.g. 'CONSENT_GRANTED', 'TEAM_DELETED').
            target: Identifier of the target resource (e.g. 'team:t_001').
            details: Optional metadata dictionary.

        Returns:
            str: Unique audit log identifier.
        """
        record = AuditLogRecord(
            actor_id=actor_id,
            action=action,
            target=target,
            details=details or {},
        )
        self._in_memory_logs.append(record)
        logger.info(
            f"[AUDIT] id={record.id} actor={record.actor_id} action={record.action} "
            f"target={record.target} at={record.at.isoformat()}"
        )

        # Hook for Database Teammate:
        # self._persist_to_database(record)
        return record.id

    def get_logs_for_target(self, target: str) -> List[AuditLogRecord]:
        """Retrieve audit log entries for a given target resource."""
        return [log for log in self._in_memory_logs if log.target == target]

    def clear(self):
        """Clear in-memory buffer (primarily for unit test isolation)."""
        self._in_memory_logs.clear()


_audit_service_instance: Optional[AuditLogService] = None


def get_audit_service() -> AuditLogService:
    global _audit_service_instance
    if _audit_service_instance is None:
        _audit_service_instance = AuditLogService()
    return _audit_service_instance
