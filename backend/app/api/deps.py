"""Authentication and authorization dependencies for FastAPI endpoints.

Implements:
1. Bearer token extraction and JWT cryptographic verification.
2. HTTP 401 Unauthorized for missing, malformed, or expired tokens.
3. Role-based access control (Student vs. Instructor).
4. Team-level authorization (Students restricted to own team; Instructors restricted to assigned classes).
5. Consent verification (Section 4 & Section 7.2: No analysis before all team members consent).
6. HTTP 403 Forbidden for unauthorized access or unconsented analysis attempts.
"""

from typing import Optional, List, Union, Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.security import (
    decode_access_token,
    TokenExpiredError,
    TokenInvalidError,
)
from app.schemas.auth import CurrentUser, UserRole
from app.db.session import get_db
from app.services.consent_service import get_consent_service, ConsentService
from app.services.audit_service import get_audit_service, AuditLogService

# HTTP Bearer scheme with auto_error=False to provide custom, descriptive 401 errors
http_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
) -> CurrentUser:
    """Validate JWT access token and return the authenticated CurrentUser context.

    Raises:
        HTTPException 401: If header is missing, token is expired, or signature is invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except TokenExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except TokenInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    subject = payload.get("sub")
    role = payload.get("role")
    if not subject or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload: Missing subject or role claims.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(
        id=str(subject),
        github_login=payload.get("github_login", str(subject)),
        role=str(role),
        team_ids=payload.get("team_ids", []),
        managed_team_ids=payload.get("managed_team_ids", []),
    )


def require_role(allowed_roles: Union[str, List[str], UserRole, List[UserRole]]) -> Callable:
    """Factory dependency enforcing that current user possesses an allowed role.

    Raises:
        HTTPException 403: If user role is not authorized.
    """
    if isinstance(allowed_roles, (str, UserRole)):
        roles_set = {str(allowed_roles).lower()}
    else:
        roles_set = {str(r).lower() for r in allowed_roles}

    async def role_checker(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.role.lower() not in roles_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Action requires role in {list(roles_set)}. Current role: '{current_user.role}'.",
            )
        return current_user

    return role_checker


# Convenient pre-configured role dependencies
require_instructor = require_role([UserRole.INSTRUCTOR, "instructor"])
require_student = require_role([UserRole.STUDENT, "student"])


async def verify_team_access(
    team_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Verify team-level authorization.

    Enforces rules from FairShare specification:
    1. Students must only access their own team's data (Section 6.6).
    2. Instructors must only access teams/classes assigned to them (Section 6.6).

    Raises:
        HTTPException 401: Handled by get_current_user if unauthenticated.
        HTTPException 403: If user is authenticated but not authorized for team_id.
    """
    if current_user.is_instructor():
        # Instructors can access teams assigned to their classes (or wildcard "*" in dev)
        if team_id not in current_user.managed_team_ids and "*" not in current_user.managed_team_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access forbidden: Instructor '{current_user.id}' is not assigned to manage team '{team_id}'. "
                    f"Assigned teams: {current_user.managed_team_ids}"
                ),
            )
        return current_user

    # Student verification
    if team_id not in current_user.team_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Access forbidden: Student '{current_user.id}' is only authorized to access their own team. "
                f"Enrolled teams: {current_user.team_ids}"
            ),
        )

    return current_user


async def require_team_consent(
    team_id: str,
    current_user: CurrentUser = Depends(verify_team_access),
    db: Optional[Session] = Depends(get_db),
) -> CurrentUser:
    """Ensure all required team members have provided consent before ingestion/analysis.

    Rule (FairShare Section 4 & Section 7.2):
    "Every member agrees before their data is analysed"
    "No analysis before consent_at is set"

    Raises:
        HTTPException 503: If database cannot be accessed.
        HTTPException 403: If team consent has not been recorded by all members.
    """
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable. Cannot verify consent.",
        )

    consent_service = get_consent_service()
    try:
        is_consented = consent_service.is_team_consented(team_id, db=db)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable. Cannot verify consent.",
        ) from exc

    if not is_consented:
        audit_service = get_audit_service()
        audit_service.log_action(
            actor_id=current_user.id,
            action="ANALYSIS_BLOCKED_NO_CONSENT",
            target=f"team:{team_id}",
            details={"reason": "Missing team member consent"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Analysis blocked: Team consent has not been granted by all members of team '{team_id}'. "
                "Every member must record explicit consent before data ingestion or analysis (FairShare Section 4 & 7.2)."
            ),
        )
    return current_user
