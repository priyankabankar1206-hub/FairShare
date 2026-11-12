"""Team lifecycle, consent, and repository management routes (Section 6.3)."""

from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, status

from app.api.deps import (
    get_current_user,
    verify_team_access,
    require_instructor,
)
from app.schemas.auth import CurrentUser
from app.schemas.team import (
    TeamCreate,
    TeamResponse,
    AttachRepoRequest,
    MemberConsentRequest,
    ConsentResponse,
    IdentityMappingRequest,
)
from app.schemas.consent import ConsentStatusResponse, TeamDeletionResponse
from app.services.consent_service import get_consent_service
from app.services.cleanup_service import get_cleanup_service

router = APIRouter()


@router.post(
    "/teams",
    response_model=TeamResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new team",
)
async def create_team(
    payload: TeamCreate,
    current_user: CurrentUser = Depends(get_current_user),
) -> TeamResponse:
    """Create a new team record.

    Awaits Team database model from Database Teammate.
    """
    return TeamResponse(
        id="t_sample_001",
        name=payload.name,
        course=payload.course,
        repo_url=payload.repo_url,
        created_at=datetime.now(timezone.utc),
    )


@router.get(
    "/teams",
    response_model=List[TeamResponse],
    summary="List all teams accessible to user",
)
async def list_teams(
    current_user: CurrentUser = Depends(get_current_user),
) -> List[TeamResponse]:
    """List teams based on user role (student sees own team, instructor sees classes)."""
    authorized_ids = current_user.managed_team_ids if current_user.is_instructor() else current_user.team_ids
    sample_team = TeamResponse(
        id="t_sample_001",
        name="Sample Team",
        course="CS 401",
        repo_url="https://github.com/sample/repo",
        created_at=datetime.now(timezone.utc),
    )
    if not authorized_ids or "t_sample_001" in authorized_ids or "*" in authorized_ids:
        return [sample_team]
    return []


@router.get(
    "/teams/{team_id}",
    response_model=TeamResponse,
    summary="Get team by ID",
)
async def get_team(
    team_id: str,
    current_user: CurrentUser = Depends(verify_team_access),
) -> TeamResponse:
    """Retrieve team by ID, protected by team authorization check."""
    return TeamResponse(
        id=team_id,
        name="Sample Team",
        course="CS 401",
        repo_url="https://github.com/sample/repo",
        created_at=datetime.now(timezone.utc),
    )


@router.post(
    "/teams/{team_id}/consent",
    response_model=ConsentResponse,
    summary="Record member consent",
    description="Rule: No analysis occurs before member consent is recorded (Section 4 & 7.2).",
)
async def record_consent(
    team_id: str,
    payload: MemberConsentRequest,
    current_user: CurrentUser = Depends(verify_team_access),
) -> ConsentResponse:
    """Record consent for a team member, ensuring the user belongs to the team."""
    consent_service = get_consent_service()
    record = consent_service.record_member_consent(
        team_id=team_id,
        user_id=payload.user_id,
        consent_given=payload.consent_given,
        version=payload.consent_version,
        actor_id=current_user.id,
    )
    return ConsentResponse(
        team_id=team_id,
        user_id=payload.user_id,
        consent_at=record.consent_at,
        status=record.status,
        consent_version=record.consent_version,
    )


@router.get(
    "/teams/{team_id}/consent",
    response_model=ConsentStatusResponse,
    summary="Get team consent status",
    description="Check whether all required team members have agreed to data analysis.",
)
async def get_consent_status(
    team_id: str,
    current_user: CurrentUser = Depends(verify_team_access),
) -> ConsentStatusResponse:
    consent_service = get_consent_service()
    return consent_service.get_team_consent_status(team_id)


@router.post(
    "/teams/{team_id}/repo",
    response_model=TeamResponse,
    summary="Attach GitHub repository to team",
)
async def attach_repository(
    team_id: str,
    payload: AttachRepoRequest,
    current_user: CurrentUser = Depends(verify_team_access),
) -> TeamResponse:
    return TeamResponse(
        id=team_id,
        name="Sample Team",
        course="CS 401",
        repo_url=payload.repo_url,
        created_at=datetime.now(timezone.utc),
    )


@router.post(
    "/teams/{team_id}/identity-map",
    summary="[DEPRECATED] Fix git identity mappings",
    description=(
        "This stub endpoint has been superseded by the dedicated Identity Mapping API (Phase 5). "
        "Use POST /api/v1/teams/{team_id}/identities/map instead."
    ),
    deprecated=True,
)
async def map_identity_deprecated(
    team_id: str,
    payload: IdentityMappingRequest,
    current_user: CurrentUser = Depends(verify_team_access),
):
    """Deprecated stub — superseded by POST /api/v1/teams/{team_id}/identities/map (Phase 5)."""
    return {
        "status": "success",
        "message": (
            "This endpoint is deprecated. "
            "Use POST /api/v1/teams/{team_id}/identities/map for manual identity mapping."
        ),
        "team_id": team_id,
        "mapped": {
            "git_email": payload.git_email,
            "member_id": payload.member_id,
            "is_bot": payload.is_bot,
        },
    }


@router.delete(
    "/teams/{team_id}/data",
    response_model=TeamDeletionResponse,
    summary="Delete all data for a team",
    description="Purges all team activity, temporary git clones, and analysis caches (Section 6.3 & 7.2).",
)
async def delete_team_data(
    team_id: str,
    current_user: CurrentUser = Depends(verify_team_access),
) -> TeamDeletionResponse:
    cleanup_service = get_cleanup_service()
    return cleanup_service.delete_team_data(
        team_id=team_id,
        actor_id=current_user.id,
        db_connected=False,  # Database teammate's DB not connected yet
    )
