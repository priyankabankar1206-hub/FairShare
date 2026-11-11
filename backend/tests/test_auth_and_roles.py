"""Comprehensive tests for JWT Authentication, RBAC, and Team Scoping (Phase 2)."""

from datetime import timedelta
import pytest
from app.core.security import (
    create_access_token,
    decode_access_token,
    TokenExpiredError,
    TokenInvalidError,
    get_password_hash,
    verify_password,
)


# ==============================================================================
# 1. JWT Creation and Verification Tests
# ==============================================================================

def test_jwt_create_and_decode_valid():
    """Verify that a freshly generated token decodes properly with expected claims."""
    token = create_access_token(
        subject="usr_test_123",
        role="student",
        github_login="octocat",
        team_ids=["team_a", "team_b"],
    )
    payload = decode_access_token(token)

    assert payload["sub"] == "usr_test_123"
    assert payload["role"] == "student"
    assert payload["github_login"] == "octocat"
    assert payload["team_ids"] == ["team_a", "team_b"]
    assert "exp" in payload
    assert "iat" in payload


def test_jwt_expired_token_handling():
    """Verify that an expired token triggers TokenExpiredError."""
    expired_token = create_access_token(
        subject="usr_expired",
        role="student",
        expires_delta=timedelta(seconds=-10),  # expired 10 seconds ago
    )
    with pytest.raises(TokenExpiredError):
        decode_access_token(expired_token)


def test_jwt_tampered_token_handling():
    """Verify that a tampered or invalid token triggers TokenInvalidError."""
    token = create_access_token(subject="usr_valid", role="student")
    tampered_token = token[:-5] + "XXXXX"

    with pytest.raises(TokenInvalidError):
        decode_access_token(tampered_token)

    with pytest.raises(TokenInvalidError):
        decode_access_token("completely_invalid_garbage_token")


# ==============================================================================
# 2. HTTP 401 Unauthorized API Tests
# ==============================================================================

def test_unauthenticated_request_returns_401(client):
    """Calling protected endpoints without Authorization header must return HTTP 401."""
    # /me endpoint
    res_me = client.get("/api/v1/me")
    assert res_me.status_code == 401
    assert "Authentication required" in res_me.json()["detail"]
    assert "WWW-Authenticate" in res_me.headers

    # Team endpoint
    res_team = client.get("/api/v1/teams/t_001")
    assert res_team.status_code == 401

    # Scores endpoint
    res_scores = client.get("/api/v1/teams/t_001/scores")
    assert res_scores.status_code == 401


def test_expired_token_header_returns_401(client):
    """Calling protected endpoint with expired token must return HTTP 401."""
    expired_token = create_access_token(
        subject="usr_expired",
        role="student",
        expires_delta=timedelta(seconds=-30),
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    response = client.get("/api/v1/me", headers=headers)

    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_invalid_token_header_returns_401(client):
    """Calling protected endpoint with forged token must return HTTP 401."""
    headers = {"Authorization": "Bearer forged_invalid_jwt_signature"}
    response = client.get("/api/v1/me", headers=headers)

    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]


# ==============================================================================
# 3. Role-Based and Team-Level Authorization (HTTP 403 Forbidden)
# ==============================================================================

def test_student_can_only_access_own_team(client):
    """Rule 5: Students must only access their own team's data.

    Accessing other teams must return HTTP 403 Forbidden.
    """
    student_token = create_access_token(
        subject="usr_student_bob",
        role="student",
        team_ids=["team_bob"],
    )
    headers = {"Authorization": f"Bearer {student_token}"}

    # Authorized team access
    res_allowed = client.get("/api/v1/teams/team_bob", headers=headers)
    assert res_allowed.status_code == 200
    assert res_allowed.json()["id"] == "team_bob"

    # Unauthorized team access
    res_forbidden = client.get("/api/v1/teams/team_charlie", headers=headers)
    assert res_forbidden.status_code == 403
    assert "only authorized to access their own team" in res_forbidden.json()["detail"]

    # Scores on forbidden team
    res_scores_forbidden = client.get("/api/v1/teams/team_charlie/scores", headers=headers)
    assert res_scores_forbidden.status_code == 403


def test_instructor_can_only_access_assigned_classes(client):
    """Rule 6: Instructors must only access teams/classes assigned to them."""
    instructor_token = create_access_token(
        subject="usr_prof_alan",
        role="instructor",
        managed_team_ids=["team_cs101_group1", "team_cs101_group2"],
    )
    headers = {"Authorization": f"Bearer {instructor_token}"}

    # Access assigned team -> 200 OK
    res_allowed = client.get("/api/v1/teams/team_cs101_group1", headers=headers)
    assert res_allowed.status_code == 200

    # Access unassigned team -> 403 Forbidden
    res_forbidden = client.get("/api/v1/teams/team_ee200_group1", headers=headers)
    assert res_forbidden.status_code == 403
    assert "not assigned to manage team" in res_forbidden.json()["detail"]


def test_dev_token_endpoint(client):
    """Verify that development token generation creates working tokens with requested roles."""
    payload = {
        "user_id": "usr_dev_instructor",
        "github_login": "instructor_dave",
        "role": "instructor",
        "managed_team_ids": ["team_demo_101"],
    }
    response = client.post("/api/v1/auth/dev-token", json=payload)
    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data

    # Use generated dev token
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    me_resp = client.get("/api/v1/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "instructor"
    assert me_resp.json()["managed_team_ids"] == ["team_demo_101"]


# ==============================================================================
# 4. Secure Password Hashing
# ==============================================================================

def test_password_hashing_and_verification():
    """Verify PBKDF2 password hashing produces salted hashes and verifies in constant time."""
    password = "SuperSecurePassword123!"
    hashed = get_password_hash(password)

    assert hashed != password
    assert hashed.startswith("pbkdf2:sha256:100000$")

    # Correct password verifies
    assert verify_password(password, hashed) is True

    # Incorrect password fails
    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password("", hashed) is False
