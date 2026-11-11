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
