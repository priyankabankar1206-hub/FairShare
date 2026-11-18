"""Tests for GitHub Repository Ingestion, Git Mining, Pagination, Rate Limits, and Resumption (Phase 4)."""

import asyncio
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
import git
import httpx
import pytest

from app.services.github.client import (
    GitHubService,
    parse_repo_url,
)
from app.services.github.exceptions import (
    GitHubRateLimitError,
    GitHubRepoNotFoundError,
)
from app.services.github.ingestion import IngestionOrchestrator
from app.services.job_service import get_job_service
from app.services.consent_service import get_consent_service
from app.schemas.github import IngestionCheckpoint


# ==============================================================================
# 1. Repository URL Parsing Tests
# ==============================================================================

def test_repo_url_parsing():
    """Verify parsing various GitHub repository URL formats."""
    assert parse_repo_url("https://github.com/octocat/Hello-World") == ("octocat", "Hello-World")
    assert parse_repo_url("https://github.com/octocat/Hello-World.git") == ("octocat", "Hello-World")
    assert parse_repo_url("git@github.com:octocat/Hello-World.git") == ("octocat", "Hello-World")
    assert parse_repo_url("octocat/Hello-World") == ("octocat", "Hello-World")

    with pytest.raises(ValueError):
        parse_repo_url("invalid_url_without_slash")


# ==============================================================================
# 2. Local Git History Mining (Commits, Authors, Diffs, Timestamps)
# ==============================================================================

def test_git_local_mining_commits_and_diffs():
    """Verify mining commits, authors, timestamps, and file changes using GitPython."""
    temp_repo_dir = tempfile.mkdtemp(prefix="fairshare_test_git_")
    try:
        # Initialize a real git repository
        repo = git.Repo.init(temp_repo_dir)

        # Commit 1
        file1 = Path(temp_repo_dir) / "app.py"
        file1.write_text("print('hello world')\n")
        repo.index.add(["app.py"])
        c1 = repo.index.commit("Initial commit", author=git.Actor("Alice Dev", "alice@example.com"))

        # Commit 2
        file2 = Path(temp_repo_dir) / "test_app.py"
        file2.write_text("def test_app():\n    assert True\n")
        repo.index.add(["test_app.py"])
        c2 = repo.index.commit("Add test file", author=git.Actor("Bob Dev", "bob@example.com"))

        service = GitHubService()
        commits = service.mine_repository_commits(temp_repo_dir)

        assert len(commits) == 2
        # Oldest first
        assert commits[0].sha == c1.hexsha
        assert commits[0].author.name == "Alice Dev"
        assert commits[0].author.email == "alice@example.com"
        assert commits[0].message == "Initial commit"
        assert commits[0].author.date is not None

        assert commits[1].sha == c2.hexsha
        assert commits[1].author.name == "Bob Dev"
        assert commits[1].message == "Add test file"

        # Check file changes
        files = [f.path for f in commits[1].files_changed]
        assert "test_app.py" in files

        # Test resumption optimization: mining with resume_after_sha skips c1
        partial = service.mine_repository_commits(temp_repo_dir, resume_after_sha=c1.hexsha)
        assert len(partial) == 1
        assert partial[0].sha == c2.hexsha

    finally:
        shutil.rmtree(temp_repo_dir, ignore_errors=True)


# ==============================================================================
# 3. GitHub API Pagination Handling
# ==============================================================================

def test_github_api_pagination(monkeypatch):
    """Verify handling of multi-page GitHub REST API responses."""
    page_1_data = [
        {"id": 101, "number": 1, "title": "PR 1", "state": "open", "created_at": "2026-11-01T10:00:00Z", "merged_at": None, "user": {"login": "alice"}},
        {"id": 102, "number": 2, "title": "PR 2", "state": "closed", "created_at": "2026-11-02T12:00:00Z", "merged_at": "2026-11-02T13:00:00Z", "user": {"login": "bob"}},
    ]
    page_2_data = [
        {"id": 103, "number": 3, "title": "PR 3", "state": "open", "created_at": "2026-11-03T15:00:00Z", "merged_at": None, "user": {"login": "charlie"}},
    ]

    async def mock_get(client, url, headers=None, params=None):
        req = httpx.Request("GET", url)
        page = params.get("page", 1) if params else 1
        if page == 1:
            resp_headers = {
                "Link": '<https://api.github.com/repos/owner/repo/pulls?page=2>; rel="next"',
                "X-RateLimit-Remaining": "4900",
            }
            return httpx.Response(200, json=page_1_data, headers=resp_headers, request=req)
        else:
            resp_headers = {"X-RateLimit-Remaining": "4899"}
            return httpx.Response(200, json=page_2_data, headers=resp_headers, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    async def run_pagination():
        service = GitHubService()
        prs_p1, has_next_p1 = await service.fetch_pull_requests_page("owner", "repo", page=1, per_page=2)
        assert len(prs_p1) == 2
        assert has_next_p1 is True
        assert prs_p1[0].author_login == "alice"

        prs_p2, has_next_p2 = await service.fetch_pull_requests_page("owner", "repo", page=2, per_page=2)
        assert len(prs_p2) == 1
        assert has_next_p2 is False
        assert prs_p2[0].author_login == "charlie"

    asyncio.run(run_pagination())


# ==============================================================================
# 4. GitHub API Rate Limit & Retry-After Handling
# ==============================================================================

def test_github_api_rate_limit_handling(monkeypatch):
    """Verify HTTP 429/403 rate limits raise GitHubRateLimitError with retry information."""
    async def mock_rate_limited_get(client, url, headers=None, params=None):
        req = httpx.Request("GET", url)
        headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + 120),
            "Retry-After": "120",
        }
        return httpx.Response(
            429,
            content=b'{"message": "API rate limit exceeded for user"}',
            headers=headers,
            request=req,
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_rate_limited_get)

    async def run_rate_limit_check():
        service = GitHubService()
        with pytest.raises(GitHubRateLimitError) as exc_info:
            await service.verify_repository_access("octocat", "Hello-World")
        assert exc_info.value.retry_after_seconds == 120

    asyncio.run(run_rate_limit_check())


# ==============================================================================
# 5. Resumable Ingestion & Checkpointing (Section 7.3)
# ==============================================================================

def test_resumable_ingestion_checkpoint_save_and_load(tmp_path):
    """Verify saving, loading, and resuming from an IngestionCheckpoint in data/{team_id}/raw/."""
    team_id = "t_resumable_team"
    orchestrator = IngestionOrchestrator(base_data_dir=str(tmp_path))

    # Checkpoint does not exist initially
    assert orchestrator.load_checkpoint(team_id) is None

    # Save checkpoint
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    ckpt = IngestionCheckpoint(
        team_id=team_id,
        repo_url="https://github.com/test/repo",
        last_synced_sha="abc1234",
        total_commits_synced=50,
        last_pr_page=3,
        is_completed=False,
        updated_at=now,
    )
    orchestrator.save_checkpoint(team_id, ckpt)

    # Save raw commits
    raw_commits = [{"sha": "abc1234", "message": "feat: init"}]
    orchestrator.save_raw_json(team_id, "commits.json", raw_commits)

    # Verify loaded checkpoint
    loaded = orchestrator.load_checkpoint(team_id)
    assert loaded is not None
    assert loaded.last_synced_sha == "abc1234"
    assert loaded.total_commits_synced == 50
    assert loaded.last_pr_page == 3
    assert loaded.is_completed is False

    # Verify loaded raw data
    loaded_raw = orchestrator.load_raw_json(team_id, "commits.json")
    assert loaded_raw == raw_commits


# ==============================================================================
# 6. Ingestion Endpoints and Job Polling
# ==============================================================================

def test_ingestion_endpoints_flow(client, student_headers):
    """Verify triggering sync, polling job status, and querying sync checkpoint."""
    team_id = "t_sample_001"

    # Ensure consent is registered for student_headers user
    consent_svc = get_consent_service()
    consent_svc.register_team_member(team_id, "usr_student_alice")
    consent_svc.record_member_consent(team_id, "usr_student_alice", consent_given=True)

    # Trigger sync
    sync_resp = client.post(
        f"/api/v1/teams/{team_id}/sync",
        json={"repo_url": "https://github.com/sample/repo", "resume": True},
        headers=student_headers,
    )
    assert sync_resp.status_code == 200
    job = sync_resp.json()
    assert job["team_id"] == team_id
    assert job["kind"] == "sync"
    assert job["status"] == "pending"

    # Poll job status
    poll_resp = client.get(f"/api/v1/jobs/{job['id']}", headers=student_headers)
    assert poll_resp.status_code == 200
    assert poll_resp.json()["id"] == job["id"]

    # Unknown job returns 404
    missing_job = client.get("/api/v1/jobs/job_unknown_9999", headers=student_headers)
    assert missing_job.status_code == 404
