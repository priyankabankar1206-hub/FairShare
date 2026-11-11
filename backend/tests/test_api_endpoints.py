"""Tests for modular API v1 endpoints (Teams, Auth, Jobs)."""

def test_auth_callback_and_me(client):
    """Test OAuth callback exchange and /me profile endpoint."""
    res_callback = client.post("/api/v1/auth/github/callback", json={"code": "sample_oauth_code"})
    assert res_callback.status_code == 200
    token_data = res_callback.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["user"]["role"] in ["student", "instructor"]

    # Verify authenticated /me profile call with the issued token
    auth_headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    res_me = client.get("/api/v1/me", headers=auth_headers)
    assert res_me.status_code == 200
    me_data = res_me.json()
    assert "github_login" in me_data
    assert "role" in me_data


def test_teams_crud_and_consent(client, student_headers):
    """Test team creation, listing, repository attaching, and consent logging."""
    # Create team
    res_create = client.post(
        "/api/v1/teams",
        json={"name": "Alpha Team", "course": "CS 401", "repo_url": "https://github.com/example/repo"},
        headers=student_headers,
    )
    assert res_create.status_code == 201
    team_data = res_create.json()
    assert team_data["name"] == "Alpha Team"

    # List teams
    res_list = client.get("/api/v1/teams", headers=student_headers)
    assert res_list.status_code == 200
    assert isinstance(res_list.json(), list)

    # Consent recording (Rule: No analysis before consent is set)
    res_consent = client.post(
        f"/api/v1/teams/{team_data['id']}/consent",
        json={"user_id": "usr_alice", "consent_given": True},
        headers=student_headers,
    )
    assert res_consent.status_code == 200
    assert res_consent.json()["status"] == "consented"

    # Identity mapping
    res_id_map = client.post(
        f"/api/v1/teams/{team_data['id']}/identity-map",
        json={
            "git_name": "Alice Developer",
            "git_email": "alice@school.edu",
            "member_id": "m_alice",
            "is_bot": False,
        },
        headers=student_headers,
    )
    assert res_id_map.status_code == 200
    assert res_id_map.json()["status"] == "success"

    # Team data deletion (cascading delete request)
    res_delete = client.delete(f"/api/v1/teams/{team_data['id']}/data", headers=student_headers)
    assert res_delete.status_code == 200
    del_data = res_delete.json()
    assert del_data["team_id"] == team_data["id"]
    assert del_data["filesystem_cleaned"] is True
    assert "cascade" in del_data["database_status"].lower()


def test_jobs_sync_and_polling(client, student_headers):
    """Test sync job trigger and status polling."""
    res_sync = client.post("/api/v1/teams/t_001/sync", headers=student_headers)
    assert res_sync.status_code == 200
    job_data = res_sync.json()
    assert job_data["status"] == "pending"
    assert job_data["kind"] == "sync"

    res_poll = client.get(f"/api/v1/jobs/{job_data['id']}", headers=student_headers)
    assert res_poll.status_code == 200
    assert res_poll.json()["id"] == job_data["id"]
