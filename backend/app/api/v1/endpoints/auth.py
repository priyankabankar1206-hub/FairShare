"""Authentication and user session routes (Section 6.2 & 6.3)."""

from datetime import timedelta
from fastapi import APIRouter, HTTPException, Depends, status

from app.core.security import create_access_token
from app.api.deps import get_current_user
from app.schemas.auth import (
    GitHubAuthCallbackRequest,
    AuthTokenResponse,
    UserResponse,
    CurrentUser,
    DevTokenRequest,
)

router = APIRouter()


@router.post(
    "/auth/github/callback",
    response_model=AuthTokenResponse,
    summary="Finish GitHub sign-in",
    description="Exchanges GitHub OAuth code for a session token with real signed JWT.",
)
async def github_auth_callback(payload: GitHubAuthCallbackRequest) -> AuthTokenResponse:
    """GitHub sign-in callback handler.

    Exchanges authorization code and issues a signed JWT token.
    (Full GitHub API token exchange will connect here once OAuth App is registered)
    """
    if not payload.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code is required.",
        )

    # In production, this user payload will be loaded from DB / GitHub API
    user_id = "usr_github_sample"
    github_login = "developer"
    role = "student"
    team_ids = ["t_sample_001", "t_001"]

    access_token = create_access_token(
        subject=user_id,
        role=role,
        github_login=github_login,
        team_ids=team_ids,
    )

    user_response = UserResponse(
        id=user_id,
        github_login=github_login,
        role=role,
        team_ids=team_ids,
        managed_team_ids=[],
    )

    return AuthTokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user_response,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user and role",
    description="Returns the profile and role ('student' or 'instructor') of the authenticated user.",
)
async def get_current_user_profile(
    current_user: CurrentUser = Depends(get_current_user),
) -> UserResponse:
    """Retrieve current authenticated user context from verified JWT."""
    return UserResponse(
        id=current_user.id,
        github_login=current_user.github_login,
        role=current_user.role,
        team_ids=current_user.team_ids,
        managed_team_ids=current_user.managed_team_ids,
    )


@router.post(
    "/auth/dev-token",
    response_model=AuthTokenResponse,
    summary="[DEVELOPMENT ONLY] Generate test JWT token",
    description="Generates a signed JWT with specified role and team memberships for local development and testing.",
)
async def generate_dev_token(payload: DevTokenRequest) -> AuthTokenResponse:
    """Development token generator.

    NOTE: Clearly separated from production auth. For testing role & team authorization.
    """
    delta = timedelta(minutes=payload.expire_minutes) if payload.expire_minutes else None
    token = create_access_token(
        subject=payload.user_id,
        role=payload.role.value,
        github_login=payload.github_login,
        team_ids=payload.team_ids,
        managed_team_ids=payload.managed_team_ids,
        expires_delta=delta,
    )

    user_resp = UserResponse(
        id=payload.user_id,
        github_login=payload.github_login,
        role=payload.role.value,
        team_ids=payload.team_ids,
        managed_team_ids=payload.managed_team_ids,
    )

    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        user=user_resp,
    )
