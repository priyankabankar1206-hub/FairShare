"""Phase 5 — Identity Mapping & Manual Correction API tests.

Tests:
    1. test_auto_match_from_commits          — email match auto-creates a mapping
    2. test_get_unmatched_identities         — unknown email appears as unmatched
    3. test_manual_mapping_success_instructor — instructor maps identity → 200 + audit log
    4. test_manual_mapping_invalid_member    — unknown member_id → 422
    5. test_manual_mapping_duplicate         — same mapping submitted twice → 200 (idempotent)
    6. test_manual_mapping_conflict          — same git identity → different member → 409
    7. test_manual_mapping_unauthorized_student — student POST → 403
    8. test_manual_mapping_unauthorized_no_token — no auth → 401
"""

import sys
from pathlib import Path
import pytest

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.services.identity_service import IdentityMappingService, get_identity_service
from app.services.audit_service import get_audit_service
from app.schemas.github import MinedCommit, CommitAuthor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_service() -> IdentityMappingService:
    """Return the global identity service, cleared of any previous test state."""
    svc = get_identity_service()
    # Clear both test teams to prevent state leakage between tests
    svc.clear_team("t_phase5_test")
    svc.clear_team("t_001")
    svc.clear_team("t_sample_001")
    return svc


def _instructor_headers() -> dict:
    token = create_access_token(
        subject="usr_prof_smith",
        role="instructor",
        github_login="prof_smith",
        managed_team_ids=["t_phase5_test", "t_sample_001", "t_001"],
    )
    return {"Authorization": f"Bearer {token}"}


def _student_headers() -> dict:
    token = create_access_token(
        subject="usr_student_alice",
        role="student",
        github_login="alice_dev",
        team_ids=["t_phase5_test", "t_sample_001", "t_001"],
    )
    return {"Authorization": f"Bearer {token}"}


TEAM_ID = "t_phase5_test"


# ---------------------------------------------------------------------------
# Test 1: Auto-match from commits (service-level unit test)
# ---------------------------------------------------------------------------

def test_auto_match_from_commits():
    """Auto-matching by email creates an IdentityMappingRecord with is_manual=False."""
    svc = _fresh_service()

    # Register a team member with a known email
    svc.register_team_member(
        team_id=TEAM_ID,
        member_id="mem_alice_001",
        github_login="alice_dev",
        email="alice@university.edu",
    )

    # Create a commit whose author email matches the registered member
    commits = [
        MinedCommit(
            sha="abc123",
            message="Initial commit",
            author=CommitAuthor(
                name="Alice Dev",
                email="alice@university.edu",
                date=None,
            ),
            files_changed=[],
            stats={"additions": 10, "deletions": 2, "total": 12},
        )
    ]

    created = svc.auto_match_from_commits(team_id=TEAM_ID, commits=commits)

    assert created == 1, f"Expected 1 auto-match, got {created}"

    mappings = svc.get_all_mappings(TEAM_ID)
    assert len(mappings) == 1
    record = mappings[0]
    assert record.member_id == "mem_alice_001"
    assert record.git_email == "alice@university.edu"
    assert record.is_manual is False
    assert record.is_bot is False
    assert record.mapped_by == "system:auto_match"


# ---------------------------------------------------------------------------
# Test 2: Unmatched identities appear in get_unmatched()
# ---------------------------------------------------------------------------

def test_get_unmatched_identities():
    """A commit author whose email doesn't match any member appears as unmatched."""
    svc = _fresh_service()

    # Register a member with a DIFFERENT email (no match)
    svc.register_team_member(
        team_id=TEAM_ID,
        member_id="mem_bob_002",
        github_login="bob_coder",
        email="bob@university.edu",
    )

    commits = [
        MinedCommit(
            sha="xyz789",
            message="Fix bug",
            author=CommitAuthor(
                name="Unknown Person",
                email="stranger@otherdomain.com",
                date=None,
            ),
            files_changed=[],
            stats={"additions": 5, "deletions": 1, "total": 6},
        )
    ]

    svc.auto_match_from_commits(team_id=TEAM_ID, commits=commits)

    unmatched = svc.get_unmatched(TEAM_ID)
    assert len(unmatched) == 1, f"Expected 1 unmatched identity, got {len(unmatched)}"
    assert unmatched[0].git_email == "stranger@otherdomain.com"
    assert unmatched[0].commit_count == 1


# ---------------------------------------------------------------------------
# Test 3: Instructor applies a manual mapping successfully
# ---------------------------------------------------------------------------

def test_manual_mapping_success_instructor():
    """Instructor POST to /identities/map creates a mapping and adds an audit log entry."""
    svc = _fresh_service()

    # Register the member so the service accepts the mapping
    svc.register_team_member(
        team_id=TEAM_ID,
        member_id="mem_carol_003",
        github_login="carol_gh",
        email="carol@uni.edu",
    )

    # Clear audit log for clean assertion
    audit_svc = get_audit_service()
    audit_svc.clear()

    client = TestClient(app)
    response = client.post(
        f"/api/v1/teams/{TEAM_ID}/identities/map",
        json={
            "git_name": "Carol C",
            "git_email": "carol.c@personal.com",
            "member_id": "mem_carol_003",
            "is_bot": False,
        },
        headers=_instructor_headers(),
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["member_id"] == "mem_carol_003"
    assert data["git_email"] == "carol.c@personal.com"
    assert data["is_manual"] is True
    assert data["mapped_by"] == "usr_prof_smith"

    # Verify audit log entry was created
    audit_entries = audit_svc.get_logs_for_target(f"team:{TEAM_ID}")
    assert any(
        e.action == "IDENTITY_MAPPED_MANUALLY" for e in audit_entries
    ), "Expected IDENTITY_MAPPED_MANUALLY audit entry"


# ---------------------------------------------------------------------------
# Test 4: Invalid member_id → 422
# ---------------------------------------------------------------------------

def test_manual_mapping_invalid_member():
    """Mapping to a member_id not in the team roster returns 422."""
    svc = _fresh_service()
    # Do NOT register "mem_ghost" — it should be unknown to the service

    client = TestClient(app)
    response = client.post(
        f"/api/v1/teams/{TEAM_ID}/identities/map",
        json={
            "git_name": "Ghost Dev",
            "git_email": "ghost@nowhere.com",
            "member_id": "mem_ghost_not_registered",
            "is_bot": False,
        },
        headers=_instructor_headers(),
    )

    assert response.status_code == 422, response.text
    assert "not registered" in response.json()["detail"].lower() or \
           "not registered" in response.text.lower()


# ---------------------------------------------------------------------------
# Test 5: Duplicate mapping (idempotent) → 200
# ---------------------------------------------------------------------------

def test_manual_mapping_duplicate():
    """Submitting the identical mapping twice returns 200 both times (idempotent)."""
    svc = _fresh_service()
    svc.register_team_member(
        team_id=TEAM_ID,
        member_id="mem_dave_004",
        github_login="dave_gh",
        email="dave@uni.edu",
    )

    payload = {
        "git_name": "Dave D",
        "git_email": "dave.d@work.com",
        "member_id": "mem_dave_004",
        "is_bot": False,
    }

    client = TestClient(app)

    # First submission
    r1 = client.post(
        f"/api/v1/teams/{TEAM_ID}/identities/map",
        json=payload,
        headers=_instructor_headers(),
    )
    assert r1.status_code == 200, r1.text

    # Second identical submission — must still succeed (not conflict)
    r2 = client.post(
        f"/api/v1/teams/{TEAM_ID}/identities/map",
        json=payload,
        headers=_instructor_headers(),
    )
    assert r2.status_code == 200, r2.text

    # Both should return the same member
    assert r1.json()["member_id"] == r2.json()["member_id"] == "mem_dave_004"


# ---------------------------------------------------------------------------
# Test 6: Conflicting mapping (same git identity → different member) → 409
# ---------------------------------------------------------------------------

def test_manual_mapping_conflict():
    """Mapping the same git identity to a different member returns 409 Conflict."""
    svc = _fresh_service()
    svc.register_team_member(
        team_id=TEAM_ID,
        member_id="mem_eve_005",
        github_login="eve_gh",
        email="eve@uni.edu",
    )
    svc.register_team_member(
        team_id=TEAM_ID,
        member_id="mem_frank_006",
        github_login="frank_gh",
        email="frank@uni.edu",
    )

    client = TestClient(app)
    shared_git_identity = {
        "git_name": "Shared Author",
        "git_email": "shared@email.com",
    }

    # First: map to eve
    r1 = client.post(
        f"/api/v1/teams/{TEAM_ID}/identities/map",
        json={**shared_git_identity, "member_id": "mem_eve_005"},
        headers=_instructor_headers(),
    )
    assert r1.status_code == 200, r1.text

    # Second: map same identity to frank — should conflict
    r2 = client.post(
        f"/api/v1/teams/{TEAM_ID}/identities/map",
        json={**shared_git_identity, "member_id": "mem_frank_006"},
        headers=_instructor_headers(),
    )
    assert r2.status_code == 409, r2.text
    assert "conflict" in r2.json()["detail"].lower() or \
           "already mapped" in r2.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 7: Student cannot POST to /identities/map → 403
# ---------------------------------------------------------------------------

def test_manual_mapping_unauthorized_student():
    """A student attempting a manual identity mapping receives 403 Forbidden."""
    client = TestClient(app)
    response = client.post(
        f"/api/v1/teams/{TEAM_ID}/identities/map",
        json={
            "git_name": "Student Attempt",
            "git_email": "student@uni.edu",
            "member_id": "mem_any",
        },
        headers=_student_headers(),
    )
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# Test 8: Unauthenticated request → 401
# ---------------------------------------------------------------------------

def test_manual_mapping_unauthorized_no_token():
    """An unauthenticated request to /identities/map receives 401 Unauthorized."""
    client = TestClient(app)
    response = client.post(
        f"/api/v1/teams/{TEAM_ID}/identities/map",
        json={
            "git_name": "No Auth Person",
            "git_email": "noauth@uni.edu",
            "member_id": "mem_any",
        },
        # No Authorization header
    )
    assert response.status_code == 401, response.text
