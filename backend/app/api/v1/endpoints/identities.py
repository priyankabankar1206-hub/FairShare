"""Identity Mapping API endpoints (Phase 5 — FairShare Section 6.2 & 6.3).

Endpoints:
    GET  /teams/{team_id}/identities           — View all resolved mappings (student + instructor)
    GET  /teams/{team_id}/identities/unmatched — View unresolved git authors (student + instructor)
    POST /teams/{team_id}/identities/map       — Apply a manual correction (instructor only)
"""

from fastapi import APIRouter, HTTPException, Depends, status

from app.api.deps import verify_team_access, require_instructor
from app.schemas.auth import CurrentUser
from app.schemas.identity import (
    IdentityMappingRecord,
    IdentityMappingListResponse,
    ManualMappingRequest,
    UnmatchedIdentity,
)
from app.services.identity_service import get_identity_service, IdentityMappingService

router = APIRouter()


@router.get(
    "/teams/{team_id}/identities",
    response_model=IdentityMappingListResponse,
    summary="Get all identity mappings for a team",
    description=(
        "Returns all resolved git-author → member mappings plus unmatched identities. "
        "Both students (own team only) and instructors (assigned teams) can call this. "
        "FairShare Section 6.2 & 6.3."
    ),
)
async def list_identity_mappings(
    team_id: str,
    current_user: CurrentUser = Depends(verify_team_access),
    identity_service: IdentityMappingService = Depends(get_identity_service),
) -> IdentityMappingListResponse:
    """Return the full identity mapping state for the team.

    Includes both auto-matched and manually-corrected records,
    plus a list of still-unmatched Git author identities.
    """
    return identity_service.get_mapping_list_response(team_id)


@router.get(
    "/teams/{team_id}/identities/unmatched",
    response_model=list,
    summary="Get unmatched git identities for a team",
    description=(
        "Returns git commit author identities (name + email) that have no mapping "
        "to a team member yet. Includes heuristic suggestions where possible. "
        "FairShare Section 6.2."
    ),
)
async def list_unmatched_identities(
    team_id: str,
    current_user: CurrentUser = Depends(verify_team_access),
    identity_service: IdentityMappingService = Depends(get_identity_service),
) -> list:
    """Return commit author identities that remain unmapped to any team member."""
    unmatched = identity_service.get_unmatched(team_id)
    # Serialize manually to avoid Pydantic list[UnmatchedIdentity] response_model issues
    return [u.model_dump() for u in unmatched]


@router.post(
    "/teams/{team_id}/identities/map",
    response_model=IdentityMappingRecord,
    status_code=status.HTTP_200_OK,
    summary="Manually map a git identity to a team member (instructor only)",
    description=(
        "An instructor submits a correction that links a git commit author "
        "(name + email) to the correct FairShare team member. "
        "Prevents duplicates and conflicting mappings. Recorded in audit log. "
        "FairShare Section 6.2 & 6.6."
    ),
)
async def apply_manual_identity_mapping(
    team_id: str,
    payload: ManualMappingRequest,
    current_user: CurrentUser = Depends(require_instructor),
    identity_service: IdentityMappingService = Depends(get_identity_service),
) -> IdentityMappingRecord:
    """Apply a manual identity correction.

    Authorization: **Instructor only** — students cannot modify identity mappings.

    Business rules enforced:
    - member_id must be a known roster member of this team (422 if not).
    - Same git identity already mapped to the same member: idempotent 200.
    - Same git identity already mapped to a *different* member: 409 Conflict.
    """
    # Also verify the instructor has access to this specific team
    # (require_instructor only checks the role, not team assignment)
    if (
        team_id not in current_user.managed_team_ids
        and "*" not in current_user.managed_team_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Forbidden: Instructor '{current_user.id}' is not assigned to manage team '{team_id}'. "
                f"Assigned teams: {current_user.managed_team_ids}"
            ),
        )

    try:
        record, _is_new = identity_service.apply_manual_mapping(
            team_id=team_id,
            git_name=payload.git_name,
            git_email=payload.git_email,
            member_id=payload.member_id,
            actor_id=current_user.id,
            is_bot=payload.is_bot,
        )
        return record
    except ValueError as exc:
        error_str = str(exc)

        if error_str.startswith("member_not_in_team"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Invalid mapping: member_id '{payload.member_id}' is not registered "
                    f"in team '{team_id}'. Register the member first or check the member ID."
                ),
            ) from exc

        if error_str.startswith("conflict"):
            # Extract current member from error string for helpful message
            parts = {k: v for k, v in (p.split("=", 1) for p in error_str.split("|") if "=" in p)}
            current_member = parts.get("current_member", "another member")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Conflict: Git identity '{payload.git_name}' <{payload.git_email}> "
                    f"is already mapped to member '{current_member}' in team '{team_id}'. "
                    "Delete the existing mapping before creating a new one, or verify the correct member."
                ),
            ) from exc

        # Unexpected ValueError — re-raise as 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error applying mapping: {exc}",
        ) from exc
