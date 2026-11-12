"""Pydantic schemas for Identity Mapping (Phase 5 — Section 6.2 & 6.3).

These schemas model the connection between raw Git commit author information
(name, email) and the actual FairShare team member accounts.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class GitIdentity(BaseModel):
    """A unique author identity extracted from Git commit history."""

    git_name: str = Field(..., description="Author name as it appears in git commits")
    git_email: str = Field(..., description="Author email as it appears in git commits")
    author_logins: List[str] = Field(
        default_factory=list,
        description="GitHub usernames associated with this identity (from PR/API data)",
    )


class IdentityMappingRecord(BaseModel):
    """A resolved mapping between a Git identity and a FairShare team member.

    NOTE FOR DATABASE TEAMMATE:
    This record maps to a table with columns:
        id (PK), team_id, git_name, git_email, member_id,
        mapped_by, mapped_at, is_bot, is_manual, is_active
    """

    id: str = Field(..., description="Unique record identifier")
    team_id: str = Field(..., description="Team this mapping belongs to")
    git_name: str = Field(..., description="Git author name")
    git_email: str = Field(..., description="Git author email")
    member_id: str = Field(..., description="FairShare member account ID")
    mapped_by: str = Field(..., description="Actor who created this mapping (system or instructor ID)")
    mapped_at: datetime = Field(..., description="Timestamp when the mapping was created")
    is_bot: bool = Field(default=False, description="True if this identity belongs to a CI/bot account")
    is_manual: bool = Field(
        default=False,
        description="True if mapping was applied manually by an instructor",
    )


class ManualMappingRequest(BaseModel):
    """Request body for instructor-submitted manual identity correction (POST /identities/map)."""

    git_name: str = Field(..., min_length=1, description="Git author name to map")
    git_email: str = Field(..., min_length=1, description="Git author email to map")
    member_id: str = Field(..., min_length=1, description="FairShare member ID to assign this identity to")
    is_bot: bool = Field(default=False, description="Mark as a bot/CI account (excludes from scoring)")


class UnmatchedIdentity(BaseModel):
    """A Git commit author identity that has not yet been mapped to a team member."""

    git_name: str = Field(..., description="Git author name")
    git_email: str = Field(..., description="Git author email")
    commit_count: int = Field(default=0, description="Number of commits made by this identity")
    possible_members: List[str] = Field(
        default_factory=list,
        description="Member IDs whose known email/username partially matches this identity",
    )


class IdentityMappingListResponse(BaseModel):
    """Full identity mapping state for a team, returned by GET /teams/{team_id}/identities."""

    team_id: str
    total_mappings: int = Field(..., description="Total number of resolved mappings (including auto-mapped)")
    total_unmatched: int = Field(..., description="Number of unresolved git identities")
    mappings: List[IdentityMappingRecord] = Field(default_factory=list)
    unmatched: List[UnmatchedIdentity] = Field(default_factory=list)
