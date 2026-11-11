"""Authentication and user schemas (Section 6.2 & 6.3)."""

from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """User roles specified in Section 4 and 6.2."""
    STUDENT = "student"
    INSTRUCTOR = "instructor"


class UserBase(BaseModel):
    github_login: str
    role: UserRole = Field(default=UserRole.STUDENT, description="'student' or 'instructor'")


class UserResponse(BaseModel):
    id: str
    github_login: str
    role: str
    team_ids: List[str] = Field(default_factory=list, description="Teams the user is a member of")
    managed_team_ids: List[str] = Field(default_factory=list, description="Teams/courses managed by this instructor")
    created_at: Optional[datetime] = None


class GitHubAuthCallbackRequest(BaseModel):
    """Payload received to finish GitHub sign-in."""

    code: str = Field(..., description="GitHub OAuth authorization code")
    state: Optional[str] = Field(default=None, description="CSRF state parameter")


class AuthTokenResponse(BaseModel):
    """Session access token response."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenPayload(BaseModel):
    """Decoded JWT payload structure."""

    sub: str = Field(..., description="User ID subject")
    role: str = Field(..., description="'student' or 'instructor'")
    github_login: str
    team_ids: List[str] = Field(default_factory=list)
    managed_team_ids: List[str] = Field(default_factory=list)
    exp: int
    iat: Optional[int] = None


class CurrentUser(BaseModel):
    """Authenticated user context injected into endpoints via dependency."""

    id: str
    github_login: str
    role: str
    team_ids: List[str] = Field(default_factory=list)
    managed_team_ids: List[str] = Field(default_factory=list)

    def is_instructor(self) -> bool:
        return self.role.lower() == UserRole.INSTRUCTOR.value

    def is_student(self) -> bool:
        return self.role.lower() == UserRole.STUDENT.value

    def can_access_team(self, team_id: str) -> bool:
        """Verify if current user is authorized to view or manage team_id."""
        if self.is_instructor():
            # Instructors can access teams assigned to their classes
            return team_id in self.managed_team_ids or "*" in self.managed_team_ids
        # Students can only access their own team
        return team_id in self.team_ids


class DevTokenRequest(BaseModel):
    """Request payload for issuing development/testing tokens.

    NOTE: For development and testing use only. Clearly separated from production auth.
    """

    user_id: str = Field(default="usr_dev_student", description="Simulated user ID")
    github_login: str = Field(default="dev_user", description="Simulated GitHub username")
    role: UserRole = Field(default=UserRole.STUDENT, description="'student' or 'instructor'")
    team_ids: List[str] = Field(default_factory=lambda: ["t_001"], description="Enrolled teams (for students)")
    managed_team_ids: List[str] = Field(default_factory=list, description="Managed teams (for instructors)")
    expire_minutes: Optional[int] = Field(default=60, description="Token lifetime in minutes")
