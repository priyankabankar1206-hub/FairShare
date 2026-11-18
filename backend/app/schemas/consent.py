"""Pydantic schemas for Consent Recording and Team Data Deletion (Phase 3).

Aligned with Section 4 ("Consent screen: every member agrees before their data is analysed"),
Section 6.6 ("Delete clones after analysis and delete team data on request"),
and Section 7.2 ("No analysis before consent_at is set").
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class MemberConsentRequest(BaseModel):
    """Payload submitted when a member grants or revokes consent."""

    user_id: str = Field(..., description="Unique user identifier")
    consent_given: bool = Field(..., description="True if consent is granted, False if denied/revoked")
    consent_version: str = Field(
        default="1.0",
        description="Version of the consent agreement presented to the user",
    )


class ConsentRecord(BaseModel):
    """Detailed record of a member's consent decision."""

    team_id: str
    user_id: str
    consent_given: bool
    consent_version: str
    consent_at: Optional[datetime] = None
    status: str = Field(..., description="'consented', 'denied', or 'pending'")


class ConsentStatusResponse(BaseModel):
    """Aggregate team consent state."""

    team_id: str
    all_members_consented: bool = Field(
        ...,
        description="Whether all registered team members have granted explicit consent",
    )
    consented_count: int
    total_registered_count: int
    records: List[ConsentRecord] = Field(default_factory=list)


class TeamDeletionResponse(BaseModel):
    """Report returned after a team data deletion request (Section 6.6 & 7.2)."""

    team_id: str
    status: str = Field(..., description="'completed' or 'partially_completed'")
    database_status: str = Field(
        ...,
        description="Status of relational database deletion (coordinated with Database Teammate)",
    )
    filesystem_cleaned: bool = Field(
        ...,
        description="True if all team-related data folders and temp clones were cleaned up",
    )
    deleted_paths: List[str] = Field(
        default_factory=list,
        description="List of filesystem paths purged",
    )
    audit_log_id: str = Field(..., description="Audit log reference for the deletion event")
    deleted_at: datetime
