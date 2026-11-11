"""Team, Consent, and Repository schemas (Section 6.3)."""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    course: Optional[str] = Field(default=None, max_length=100)
    repo_url: Optional[str] = Field(default=None, description="GitHub repository URL")


class TeamResponse(TeamCreate):
    id: str
    created_at: Optional[datetime] = None


class AttachRepoRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub repository clone URL")


class MemberConsentRequest(BaseModel):
    user_id: str
    consent_given: bool = Field(..., description="Explicit consent agreement")
    consent_version: str = Field(default="1.0", description="Version of the consent agreement presented")


class ConsentResponse(BaseModel):
    team_id: str
    user_id: str
    consent_at: Optional[datetime]
    status: str
    consent_version: str = "1.0"


class IdentityMappingRequest(BaseModel):
    """Payload to resolve or merge git identities into real member accounts."""

    git_name: str
    git_email: str
    member_id: str
    is_bot: bool = False
