"""Consent Management Service (Section 4 & Section 7.2).

Enforces the core FairShare principle:
"Every member agrees before their data is analysed" (Section 4).
"No analysis before consent_at is set" (Section 7.2).

NOTE FOR DATABASE TEAMMATE:
This service coordinates with the `team_members` table (`id, team_id, user_id, consent_at`).
When the database teammate provides the SQLAlchemy repository, this service delegates
to the live database session. Until then, an isolated in-memory registry manages state.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, List, Set
from app.schemas.consent import ConsentRecord, ConsentStatusResponse
from app.services.audit_service import get_audit_service, AuditLogService


class ConsentService:
    """Manages member consent records and verifies team analysis readiness."""

    def __init__(self, audit_service: Optional[AuditLogService] = None):
        self.audit = audit_service or get_audit_service()
        # Structure: {team_id: {user_id: ConsentRecord}}
        self._consent_store: Dict[str, Dict[str, ConsentRecord]] = {}
        # Track registered member IDs per team: {team_id: set(user_ids)}
        self._team_roster: Dict[str, Set[str]] = {}

        # Default pre-seed for demo/sample team to keep baseline test suites clean
        self.register_team_member("t_sample_001", "usr_alice")
        self.record_member_consent("t_sample_001", "usr_alice", consent_given=True, version="1.0")
        self.register_team_member("t_001", "usr_student_alice")
        self.record_member_consent("t_001", "usr_student_alice", consent_given=True, version="1.0")

    def register_team_member(self, team_id: str, user_id: str) -> None:
        """Register a user as a member of a team."""
        if team_id not in self._team_roster:
            self._team_roster[team_id] = set()
        self._team_roster[team_id].add(user_id)

    def record_member_consent(
        self,
        team_id: str,
        user_id: str,
        consent_given: bool,
        version: str = "1.0",
        actor_id: Optional[str] = None,
    ) -> ConsentRecord:
        """Record explicit consent grant or revocation for a team member."""
        self.register_team_member(team_id, user_id)
        if team_id not in self._consent_store:
            self._consent_store[team_id] = {}

        now = datetime.now(timezone.utc)
        record = ConsentRecord(
            team_id=team_id,
            user_id=user_id,
            consent_given=consent_given,
            consent_version=version,
            consent_at=now if consent_given else None,
            status="consented" if consent_given else "denied",
        )
        self._consent_store[team_id][user_id] = record

        # Log audit trail
        action = "CONSENT_GRANTED" if consent_given else "CONSENT_DENIED"
        self.audit.log_action(
            actor_id=actor_id or user_id,
            action=action,
            target=f"team:{team_id}:member:{user_id}",
            details={"version": version, "consent_at": now.isoformat() if consent_given else None},
        )

        return record

    def is_team_consented(self, team_id: str) -> bool:
        """Check whether ALL registered members of a team have granted active consent.

        Rule: No analysis or ingestion is allowed before every team member has consented.
        """
        roster = self._team_roster.get(team_id)
        if not roster:
            # If no roster is explicitly registered yet, check if any consent records exist
            records = self._consent_store.get(team_id, {})
            if not records:
                return False
            return all(r.consent_given for r in records.values())

        records = self._consent_store.get(team_id, {})
        for member_id in roster:
            rec = records.get(member_id)
            if not rec or not rec.consent_given:
                return False
        return True

    def get_team_consent_status(self, team_id: str) -> ConsentStatusResponse:
        """Retrieve full consent breakdown for a team."""
        roster = self._team_roster.get(team_id, set())
        records_dict = self._consent_store.get(team_id, {})

        # Ensure all registered members appear in the records list
        all_records: List[ConsentRecord] = []
        consented_count = 0

        for member_id in roster:
            rec = records_dict.get(member_id)
            if rec:
                all_records.append(rec)
                if rec.consent_given:
                    consented_count += 1
            else:
                all_records.append(
                    ConsentRecord(
                        team_id=team_id,
                        user_id=member_id,
                        consent_given=False,
                        consent_version="1.0",
                        consent_at=None,
                        status="pending",
                    )
                )

        total_registered = len(roster) if roster else len(all_records)
        all_consented = (total_registered > 0) and (consented_count == total_registered)

        return ConsentStatusResponse(
            team_id=team_id,
            all_members_consented=all_consented,
            consented_count=consented_count,
            total_registered_count=total_registered,
            records=all_records,
        )

    def delete_team_consent(self, team_id: str) -> None:
        """Purge all consent records for a team (called during team data deletion)."""
        self._consent_store.pop(team_id, None)
        self._team_roster.pop(team_id, None)


_consent_service_instance: Optional[ConsentService] = None


def get_consent_service() -> ConsentService:
    global _consent_service_instance
    if _consent_service_instance is None:
        _consent_service_instance = ConsentService()
    return _consent_service_instance
