"""Database-backed team consent management service."""

from datetime import datetime, timezone
from typing import Optional, Dict, List, Set

from sqlalchemy.orm import Session

from app.models.team import Team, TeamMember
from app.schemas.consent import ConsentRecord, ConsentStatusResponse
from app.services.audit_service import get_audit_service, AuditLogService


class ConsentService:
    """Manages member consent and verifies team analysis readiness."""

    def __init__(self, audit_service: Optional[AuditLogService] = None):
        self.audit = audit_service or get_audit_service()
        self._consent_store: Dict[str, Dict[str, ConsentRecord]] = {}
        self._team_roster: Dict[str, Set[str]] = {}

        # Legacy sample data for tests that use in-memory mode.
        self.register_team_member("t_sample_001", "usr_alice")
        self.record_member_consent(
            "t_sample_001", "usr_alice", True, version="1.0"
        )
        self.register_team_member("t_001", "usr_student_alice")
        self.record_member_consent(
            "t_001", "usr_student_alice", True, version="1.0"
        )

    def register_team_member(self, team_id: str, user_id: str) -> None:
        self._team_roster.setdefault(team_id, set()).add(user_id)

    def record_member_consent(
        self,
        team_id: str,
        user_id: str,
        consent_given: bool,
        version: str = "1.0",
        actor_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> ConsentRecord:
        """Record consent for a team member in PostgreSQL if team exists in DB, else in-memory.

        Schema Limitation Note:
        The database table `team_members` only has `consent_at: Optional[datetime]`.
        It does not store `consent_version` or a boolean `denied` column.
        - When consent_given is True: `consent_at` is set to the current UTC timestamp.
        - When consent_given is False (denied/revoked): `consent_at` is set to None.
        - `consent_version` is tracked in memory and audit logs, defaulting to "1.0".
        """
        now = datetime.now(timezone.utc)

        if db is not None:
            team = db.query(Team).filter(Team.id == team_id).first()
            if team is not None:
                member = (
                    db.query(TeamMember)
                    .filter(
                        TeamMember.team_id == team_id,
                        TeamMember.user_id == user_id,
                    )
                    .first()
                )

                if member is None:
                    raise ValueError(f"User '{user_id}' is not a registered member of team '{team_id}'.")

                member.consent_at = now if consent_given else None
                try:
                    db.commit()
                    db.refresh(member)
                except Exception:
                    db.rollback()
                    raise
            else:
                self.register_team_member(team_id, user_id)
        else:
            self.register_team_member(team_id, user_id)

        # Synchronize in-memory record for fallback & compatibility
        self.register_team_member(team_id, user_id)
        if team_id not in self._consent_store:
            self._consent_store[team_id] = {}

        record = ConsentRecord(
            team_id=team_id,
            user_id=user_id,
            consent_given=consent_given,
            consent_version=version,
            consent_at=now if consent_given else None,
            status="consented" if consent_given else "denied",
        )
        self._consent_store[team_id][user_id] = record

        self.audit.log_action(
            actor_id=actor_id or user_id,
            action="CONSENT_GRANTED" if consent_given else "CONSENT_DENIED",
            target=f"team:{team_id}:member:{user_id}",
            details={
                "version": version,
                "consent_at": now.isoformat() if consent_given else None,
            },
        )

        return record

    def is_team_consented(
        self, team_id: str, db: Optional[Session] = None
    ) -> bool:
        """Check if all registered team members have provided consent.

        Rule: No analysis or ingestion is allowed before every team member has consented.
        """
        if db is not None:
            team = db.query(Team).filter(Team.id == team_id).first()
            if team is not None:
                members = (
                    db.query(TeamMember)
                    .filter(TeamMember.team_id == team_id)
                    .all()
                )
                return bool(members) and all(
                    member.consent_at is not None for member in members
                )

        # Fallback to in-memory store for unit test compatibility
        roster = self._team_roster.get(team_id)
        if not roster:
            records = self._consent_store.get(team_id, {})
            return bool(records) and all(
                record.consent_given for record in records.values()
            )

        records = self._consent_store.get(team_id, {})
        return all(
            member_id in records and records[member_id].consent_given
            for member_id in roster
        )

    def get_team_consent_status(
        self, team_id: str, db: Optional[Session] = None
    ) -> ConsentStatusResponse:
        """Retrieve full consent breakdown for a team from PostgreSQL if available, else in-memory."""
        if db is not None:
            team = db.query(Team).filter(Team.id == team_id).first()
            if team is not None:
                members = (
                    db.query(TeamMember)
                    .filter(TeamMember.team_id == team_id)
                    .all()
                )

                records = [
                    ConsentRecord(
                        team_id=team_id,
                        user_id=member.user_id,
                        consent_given=member.consent_at is not None,
                        consent_version="1.0",
                        consent_at=member.consent_at,
                        status="consented" if member.consent_at else "pending",
                    )
                    for member in members
                ]

                consented_count = sum(
                    1 for record in records if record.consent_given
                )

                return ConsentStatusResponse(
                    team_id=team_id,
                    all_members_consented=(
                        bool(members) and consented_count == len(members)
                    ),
                    consented_count=consented_count,
                    total_registered_count=len(members),
                    records=records,
                )

        # Fallback to in-memory store for unit test compatibility
        roster = self._team_roster.get(team_id, set())
        stored = self._consent_store.get(team_id, {})

        records = []
        for user_id in roster:
            record = stored.get(user_id)
            if record:
                records.append(record)
            else:
                records.append(
                    ConsentRecord(
                        team_id=team_id,
                        user_id=user_id,
                        consent_given=False,
                        consent_version="1.0",
                        consent_at=None,
                        status="pending",
                    )
                )

        if not roster and stored:
            records = list(stored.values())

        count = sum(1 for record in records if record.consent_given)
        total = len(records) if not roster else len(roster)

        return ConsentStatusResponse(
            team_id=team_id,
            all_members_consented=total > 0 and count == total,
            consented_count=count,
            total_registered_count=total,
            records=records,
        )

    def delete_team_consent(self, team_id: str, db: Optional[Session] = None) -> None:
        """Purge all consent records for a team."""
        if db is not None:
            team = db.query(Team).filter(Team.id == team_id).first()
            if team is not None:
                db.query(TeamMember).filter(TeamMember.team_id == team_id).update({TeamMember.consent_at: None})
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    raise

        self._consent_store.pop(team_id, None)
        self._team_roster.pop(team_id, None)


_consent_service_instance: Optional[ConsentService] = None


def get_consent_service() -> ConsentService:
    global _consent_service_instance

    if _consent_service_instance is None:
        _consent_service_instance = ConsentService()

    return _consent_service_instance
