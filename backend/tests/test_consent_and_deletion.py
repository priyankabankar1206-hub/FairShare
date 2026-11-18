"""Tests for Consent Recording, Analysis Guarding, and Team Data Deletion (Phase 3)."""

from pathlib import Path
import pytest
from app.core.security import create_access_token
from app.services.consent_service import get_consent_service
from app.services.audit_service import get_audit_service


# ==============================================================================
# 1. Consent Granted & Denied Tests
# ==============================================================================

def test_consent_granted(client):
    """Test recording member consent with timestamp and version."""
    team_id = "team_consent_test_01"
    token = create_access_token(
        subject="usr_student_carol",
        role="student",
        team_ids=[team_id],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Grant consent
    payload = {
        "user_id": "usr_student_carol",
        "consent_given": True,
        "consent_version": "v1.2",
    }
    response = client.post(f"/api/v1/teams/{team_id}/consent", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["team_id"] == team_id
    assert data["user_id"] == "usr_student_carol"
    assert data["status"] == "consented"
    assert data["consent_version"] == "v1.2"
    assert data["consent_at"] is not None

    # Check team consent status
    status_resp = client.get(f"/api/v1/teams/{team_id}/consent", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["all_members_consented"] is True

    # Check audit log
    audit = get_audit_service()
    logs = audit.get_logs_for_target(f"team:{team_id}:member:usr_student_carol")
    assert any(log.action == "CONSENT_GRANTED" for log in logs)


def test_consent_denied(client):
    """Test member revoking/denying consent."""
    team_id = "team_consent_test_02"
    token = create_access_token(
        subject="usr_student_dan",
        role="student",
        team_ids=[team_id],
    )
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "user_id": "usr_student_dan",
        "consent_given": False,
        "consent_version": "v1.0",
    }
    response = client.post(f"/api/v1/teams/{team_id}/consent", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "denied"
    assert data["consent_at"] is None

    # Team consent status should indicate not all consented
    status_resp = client.get(f"/api/v1/teams/{team_id}/consent", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["all_members_consented"] is False

    # Check audit log
    audit = get_audit_service()
    logs = audit.get_logs_for_target(f"team:{team_id}:member:usr_student_dan")
    assert any(log.action == "CONSENT_DENIED" for log in logs)


# ==============================================================================
# 2. Analysis & Sync Blocked Without Consent (FairShare Section 4 & 7.2)
# ==============================================================================

def test_analysis_blocked_without_consent(client):
    """Verify that sync and score endpoints reject unconsented teams with HTTP 403."""
    team_id = "team_unconsented_99"
    token = create_access_token(
        subject="usr_unconsented_student",
        role="student",
        team_ids=[team_id],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Ensure team is registered with a member who hasn't consented
    consent_svc = get_consent_service()
    consent_svc.register_team_member(team_id, "usr_unconsented_student")

    # 1. Attempting scores retrieval must return HTTP 403
    scores_res = client.get(f"/api/v1/teams/{team_id}/scores", headers=headers)
    assert scores_res.status_code == 403
    assert "Analysis blocked: Team consent has not been granted" in scores_res.json()["detail"]

    # 2. Attempting sync trigger must return HTTP 403
    sync_res = client.post(f"/api/v1/teams/{team_id}/sync", headers=headers)
    assert sync_res.status_code == 403
    assert "Analysis blocked" in sync_res.json()["detail"]

    # 3. Check audit log has recorded the blocked attempt
    audit = get_audit_service()
    blocked_logs = audit.get_logs_for_target(f"team:{team_id}")
    assert any(log.action == "ANALYSIS_BLOCKED_NO_CONSENT" for log in blocked_logs)


# ==============================================================================
# 3. Authorized vs. Unauthorized Team Data Deletion (Section 6.6 & 7.2)
# ==============================================================================

def test_authorized_deletion_cleans_files_and_reports_status(client):
    """Authorized team member can delete team data, cleaning files and recording audit."""
    team_id = "team_delete_test"
    token = create_access_token(
        subject="usr_owner",
        role="student",
        team_ids=[team_id],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Create dummy files simulating cached analysis / raw data (Section 7.3)
    dummy_team_dir = Path("data") / team_id / "raw"
    dummy_team_dir.mkdir(parents=True, exist_ok=True)
    sample_file = dummy_team_dir / "sample_cache.json"
    sample_file.write_text("{\"raw\": true}")
    assert sample_file.exists()

    # Request deletion
    del_res = client.delete(f"/api/v1/teams/{team_id}/data", headers=headers)
    assert del_res.status_code == 200
    report = del_res.json()

    assert report["team_id"] == team_id
    assert report["filesystem_cleaned"] is True
    # Verify file was actually purged
    assert not sample_file.exists()
    assert not (Path("data") / team_id).exists()

    # Honest reporting: DB is not connected, so status must state pending DB connection
    assert "pending_database_connection" in report["database_status"]

    # Audit log entry created
    audit = get_audit_service()
    del_logs = audit.get_logs_for_target(f"team:{team_id}")
    assert any(log.action == "TEAM_DATA_DELETED" for log in del_logs)


def test_unauthorized_deletion_forbidden(client):
    """Students attempting to delete other teams' data must be blocked with HTTP 403."""
    attacker_token = create_access_token(
        subject="usr_attacker",
        role="student",
        team_ids=["team_alpha"],
    )
    headers = {"Authorization": f"Bearer {attacker_token}"}

    # Attempt to delete team_beta
    del_res = client.delete("/api/v1/teams/team_beta/data", headers=headers)
    assert del_res.status_code == 403
    assert "only authorized to access their own team" in del_res.json()["detail"]


def test_unauthenticated_deletion_unauthorized(client):
    """Deleting team data without Authorization header must return HTTP 401."""
    del_res = client.delete("/api/v1/teams/team_any/data")
    assert del_res.status_code == 401


# ==============================================================================
# 4. Database-Backed Consent & Identity Verification Tests
# ==============================================================================

def test_consent_student_cannot_consent_for_other_student(client):
    """Student cannot record consent for another student (HTTP 403)."""
    team_id = "team_cross_consent"
    token = create_access_token(
        subject="usr_student_eve",
        role="student",
        team_ids=[team_id],
    )
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "user_id": "usr_student_frank",
        "consent_given": True,
        "consent_version": "v1.0",
    }
    response = client.post(f"/api/v1/teams/{team_id}/consent", json=payload, headers=headers)
    assert response.status_code == 403
    assert "You can only record consent for yourself" in response.json()["detail"]


def test_consent_database_unavailable_returns_503(client):
    """When database is unavailable (None), consent endpoints return HTTP 503."""
    from app.main import app
    from app.db.session import get_db

    team_id = "team_db_unavailable_test"
    token = create_access_token(
        subject="usr_test_student",
        role="student",
        team_ids=[team_id],
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Override get_db to simulate database connection loss
    def override_get_db():
        yield None

    app.dependency_overrides[get_db] = override_get_db
    try:
        # 1. Recording consent returns 503
        payload = {
            "user_id": "usr_test_student",
            "consent_given": True,
            "consent_version": "1.0",
        }
        res_post = client.post(f"/api/v1/teams/{team_id}/consent", json=payload, headers=headers)
        assert res_post.status_code == 503
        assert "Database unavailable" in res_post.json()["detail"]

        # 2. Checking consent status returns 503
        res_get = client.get(f"/api/v1/teams/{team_id}/consent", headers=headers)
        assert res_get.status_code == 503
        assert "Database unavailable" in res_get.json()["detail"]

        # 3. Guard dependency (require_team_consent) returns 503
        res_scores = client.get(f"/api/v1/teams/{team_id}/scores", headers=headers)
        assert res_scores.status_code == 503
        assert "Database unavailable" in res_scores.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_database_backed_consent_lifecycle(client):
    """Verify full DB-backed consent lifecycle with real PostgreSQL records."""
    import uuid
    from app.db.session import get_engine, SessionLocal
    from app.models.team import User, Team, TeamMember

    engine = get_engine()
    db = SessionLocal()

    team_id = f"t_db_test_{uuid.uuid4().hex[:8]}"
    u1_id = f"usr_db_1_{uuid.uuid4().hex[:8]}"
    u2_id = f"usr_db_2_{uuid.uuid4().hex[:8]}"

    try:
        # Create users
        u1 = User(id=u1_id, github_login=f"gh_{u1_id}", role="student")
        u2 = User(id=u2_id, github_login=f"gh_{u2_id}", role="student")
        db.add_all([u1, u2])

        # Create team
        team = Team(id=team_id, name="DB Test Team", course="CS 401", repo_url="https://github.com/db/test")
        db.add(team)

        # Create members with NO consent initially
        m1 = TeamMember(id=f"tm_{uuid.uuid4().hex[:8]}", team_id=team_id, user_id=u1_id, consent_at=None)
        m2 = TeamMember(id=f"tm_{uuid.uuid4().hex[:8]}", team_id=team_id, user_id=u2_id, consent_at=None)
        db.add_all([m1, m2])
        db.commit()

        # Tokens
        t1 = create_access_token(subject=u1_id, role="student", team_ids=[team_id])
        t2 = create_access_token(subject=u2_id, role="student", team_ids=[team_id])
        h1 = {"Authorization": f"Bearer {t1}"}
        h2 = {"Authorization": f"Bearer {t2}"}

        # 1. Check status: 0 of 2 consented
        status_res = client.get(f"/api/v1/teams/{team_id}/consent", headers=h1)
        assert status_res.status_code == 200
        data = status_res.json()
        assert data["all_members_consented"] is False
        assert data["consented_count"] == 0
        assert data["total_registered_count"] == 2

        # 2. Analysis blocked
        scores_res = client.get(f"/api/v1/teams/{team_id}/scores", headers=h1)
        assert scores_res.status_code == 403

        # 3. User 1 grants consent
        res_c1 = client.post(
            f"/api/v1/teams/{team_id}/consent",
            json={"user_id": u1_id, "consent_given": True, "consent_version": "1.0"},
            headers=h1,
        )
        assert res_c1.status_code == 200
        assert res_c1.json()["status"] == "consented"

        # 4. Check status: 1 of 2 consented -> all_members_consented still False
        status_res = client.get(f"/api/v1/teams/{team_id}/consent", headers=h1)
        assert status_res.status_code == 200
        assert status_res.json()["all_members_consented"] is False
        assert status_res.json()["consented_count"] == 1

        # 5. Analysis still blocked
        scores_res = client.get(f"/api/v1/teams/{team_id}/scores", headers=h2)
        assert scores_res.status_code == 403

        # 6. Attempting to record consent for unknown user returns 404
        bad_res = client.post(
            f"/api/v1/teams/{team_id}/consent",
            json={"user_id": "usr_nonexistent", "consent_given": True, "consent_version": "1.0"},
            headers={"Authorization": f"Bearer {create_access_token(subject='usr_nonexistent', role='student', team_ids=[team_id])}"},
        )
        assert bad_res.status_code == 404
        assert "not a registered member" in bad_res.json()["detail"]

        # 7. User 2 grants consent
        res_c2 = client.post(
            f"/api/v1/teams/{team_id}/consent",
            json={"user_id": u2_id, "consent_given": True, "consent_version": "1.0"},
            headers=h2,
        )
        assert res_c2.status_code == 200

        # 8. All consented!
        status_res = client.get(f"/api/v1/teams/{team_id}/consent", headers=h1)
        assert status_res.status_code == 200
        assert status_res.json()["all_members_consented"] is True
        assert status_res.json()["consented_count"] == 2

    finally:
        # Clean up database
        db.query(TeamMember).filter(TeamMember.team_id == team_id).delete()
        db.query(Team).filter(Team.id == team_id).delete()
        db.query(User).filter(User.id.in_([u1_id, u2_id])).delete()
        db.commit()
        db.close()
