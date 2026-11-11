from datetime import datetime, timezone
from typing import List, Tuple
from sqlalchemy.orm import Session

from app.models.team import Team, TeamMember


class ConsentRequiredError(Exception):
    """Raised when repository analysis or commit ingestion is attempted without full consent."""
    pass


def check_team_consent(db: Session, team_id: str) -> Tuple[bool, List[str]]:
    """
    Check if all registered members in a team have given consent.
    Returns (is_fully_consented, list_of_unconsented_member_ids).
    Section 7.2 requirement: 'No analysis before consent_at is set'.
    """
    members = db.query(TeamMember).filter(TeamMember.team_id == team_id).all()
    if not members:
        # A team with no members cannot proceed with analysis
        return False, []

    unconsented_member_ids = [m.id for m in members if m.consent_at is None]
    is_fully_consented = len(unconsented_member_ids) == 0
    return is_fully_consented, unconsented_member_ids


def enforce_team_consent(db: Session, team_id: str) -> None:
    """
    Gatekeeper function to call before any ingestion, feature extraction,
    graph construction, or scoring task.
    """
    is_consented, missing_ids = check_team_consent(db, team_id)
    if not is_consented:
        raise ConsentRequiredError(
            f"Cannot run ingestion or analysis for team '{team_id}': "
            f"{len(missing_ids)} member(s) have not provided consent."
        )


def record_member_consent(db: Session, member_id: str) -> TeamMember:
    """Record consent timestamp for a specific member."""
    member = db.get(TeamMember, member_id)
    if not member:
        raise ValueError(f"TeamMember with ID '{member_id}' not found.")

    member.consent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(member)
    return member

