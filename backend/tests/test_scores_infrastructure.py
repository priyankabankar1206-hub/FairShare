"""Tests for Part A — Scoring Infrastructure, Caching, and Member Resolution.

All tests operate offline with mocked dependencies; zero network access.
"""

import sys
from pathlib import Path
import pytest
from datetime import datetime, timezone

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.schemas.aiml_contract import (
    AIMLAnalysisResponse,
    MemberScoreReport,
    FacetScores,
    ImbalanceAssessment,
    AIMLMemberInput,
)
from app.schemas.github import IngestionCheckpoint, MinedCommit, CommitAuthor
from app.services.identity_service import get_identity_service
from app.services.aiml.service import (
    get_aiml_service,
    save_cached_analysis,
    load_cached_analysis,
    invalidate_cached_analysis,
    validate_safe_team_id,
)
from app.services.github.ingestion import get_ingestion_orchestrator
from app.services.github.client import get_github_service
from app.services.consent_service import get_consent_service


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def student_headers() -> dict:
    token = create_access_token(
        subject="usr_student_alice",
        role="student",
        github_login="alice_dev",
        team_ids=["t_infra_001", "t_001"],
    )
    return {"Authorization": f"Bearer {token}"}


TEAM_ID = "t_infra_001"


def setup_function():
    """Ensure clean state for each test."""
    identity_svc = get_identity_service()
    identity_svc.clear_team(TEAM_ID)
    identity_svc.clear_team("t_001")
    invalidate_cached_analysis(TEAM_ID)
    invalidate_cached_analysis("t_001")
    # Grant consent for test teams so require_team_consent passes
    consent_svc = get_consent_service()
    consent_svc.record_member_consent(TEAM_ID, "usr_student_alice", True)
    consent_svc.record_member_consent("t_001", "usr_student_alice", True)
    # Reset model callable
    aiml_svc = get_aiml_service()
    aiml_svc.register_model_callable(None)


# ---------------------------------------------------------------------------
# Test 1: Identity mapping member & email aggregation
# ---------------------------------------------------------------------------

def test_get_team_aiml_members_filtering_and_bots():
    """Verify that get_team_aiml_members aggregates registered emails and excludes bots."""
    identity_svc = get_identity_service()

    # Register real member
    identity_svc.register_team_member(
        team_id=TEAM_ID,
        member_id="mem_alice",
        github_login="alice_dev",
        email="alice@school.edu",
    )

    # Map a non-bot git email
    identity_svc.apply_manual_mapping(
        team_id=TEAM_ID,
        git_name="Alice Dev",
        git_email="alice.dev@work.com",
        member_id="mem_alice",
        actor_id="instructor_1",
        is_bot=False,
    )

    # Map a bot email to this member (e.g. CI token attribution)
    identity_svc.apply_manual_mapping(
        team_id=TEAM_ID,
        git_name="CI Bot",
        git_email="bot@automated.ci",
        member_id="mem_alice",
        actor_id="instructor_1",
        is_bot=True,
    )

    members = identity_svc.get_team_aiml_members(TEAM_ID)
    assert len(members) == 1
    m = members[0]
    assert m.member_id == "mem_alice"
    # Should include profile email and non-bot email, but NOT the bot email
    assert "alice@school.edu" in m.emails
    assert "alice.dev@work.com" in m.emails
    assert "bot@automated.ci" not in m.emails


def test_get_team_aiml_members_empty_for_unregistered_team():
    """Verify that an unconfigured team returns an empty list (never fabricates members)."""
    identity_svc = get_identity_service()
    members = identity_svc.get_team_aiml_members("t_nonexistent")
    assert members == []


# ---------------------------------------------------------------------------
# Test 2: Cache Lifecycle and Safety
# ---------------------------------------------------------------------------

def test_cache_save_load_invalidate_lifecycle():
    """Verify that analysis results can be safely saved, loaded, and invalidated."""
    sample_response = AIMLAnalysisResponse(
        team_id=TEAM_ID,
        model_version="lite-0.1",
        as_of="2026-11-20",
        members=[
            MemberScoreReport(
                member_id="mem_1",
                share=1.0,
                facets=FacetScores(code=1.0, review=0.0, testing=0.0, docs=0.0, coordination=0.0),
                flags=[],
                evidence=[],
            )
        ],
        imbalance=ImbalanceAssessment(gini=0.0, label="balanced"),
        warnings=[],
    )

    # 1. Save to cache
    save_cached_analysis(TEAM_ID, sample_response)

    # 2. Load from cache
    loaded = load_cached_analysis(TEAM_ID)
    assert loaded is not None
    assert loaded.team_id == TEAM_ID
    assert loaded.members[0].member_id == "mem_1"

    # 3. Invalidate
    assert invalidate_cached_analysis(TEAM_ID) is True
    assert load_cached_analysis(TEAM_ID) is None


def test_validate_safe_team_id():
    """Verify that path traversal strings are rejected."""
    assert validate_safe_team_id("t_001") == "t_001"
    assert validate_safe_team_id("valid-team-123_abc") == "valid-team-123_abc"

    with pytest.raises(ValueError):
        validate_safe_team_id("../hack")
    with pytest.raises(ValueError):
        validate_safe_team_id("team/slash")
    with pytest.raises(ValueError):
        validate_safe_team_id("")


# ---------------------------------------------------------------------------
# Test 3: Endpoint Serves Cached Results
# ---------------------------------------------------------------------------

def test_scores_endpoint_returns_cached_analysis(client, student_headers):
    """Verify that GET /scores immediately returns cached results when present."""
    cached_data = AIMLAnalysisResponse(
        team_id=TEAM_ID,
        model_version="lite-0.1",
        as_of="2026-11-20",
        members=[
            MemberScoreReport(
                member_id="mem_alice",
                share=1.0,
                facets=FacetScores(code=1.0, review=0.0, testing=0.0, docs=0.0, coordination=0.0),
                flags=["split_commits"],
                evidence=[],
            )
        ],
        imbalance=ImbalanceAssessment(gini=0.0, label="balanced"),
        warnings=[],
    )
    save_cached_analysis(TEAM_ID, cached_data)

    response = client.get(f"/api/v1/teams/{TEAM_ID}/scores", headers=student_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["team_id"] == TEAM_ID
    assert data["members"][0]["member_id"] == "mem_alice"
    assert data["members"][0]["flags"] == ["split_commits"]


# ---------------------------------------------------------------------------
# Test 4: Endpoint returns empty insufficient_data when 0 members exist
# ---------------------------------------------------------------------------

def test_scores_endpoint_empty_members_insufficient_data(client, student_headers):
    """Verify that an un-rostered team returns HTTP 200 with members=[] and insufficient_data."""
    response = client.get(f"/api/v1/teams/{TEAM_ID}/scores", headers=student_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["team_id"] == TEAM_ID
    assert data["members"] == []
    assert data["warnings"] == ["insufficient_data"]
    assert data["imbalance"]["label"] == "balanced"


# ---------------------------------------------------------------------------
# Test 5: Endpoint raises 503 when model is unregistered for ready team
# ---------------------------------------------------------------------------

def test_scores_endpoint_503_when_model_unregistered(client, student_headers):
    """Verify that when members and repository exist but no model is registered, HTTP 503 is returned."""
    identity_svc = get_identity_service()
    identity_svc.register_team_member(TEAM_ID, "mem_alice", "alice_dev", "alice@test.edu")

    # Set up a checkpoint with repo_url
    orchestrator = get_ingestion_orchestrator()
    orchestrator.save_checkpoint(
        TEAM_ID,
        IngestionCheckpoint(
            team_id=TEAM_ID,
            repo_url="https://github.com/mock/repo",
            total_commits_synced=5,
            is_completed=True,
            updated_at=datetime.now(timezone.utc),
        ),
    )

    # Ensure model callable is None
    aiml_svc = get_aiml_service()
    aiml_svc.register_model_callable(None)

    response = client.get(f"/api/v1/teams/{TEAM_ID}/scores", headers=student_headers)
    assert response.status_code == 503
    assert "inference engine is not ready" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test 6: On-demand analysis with temporary clone and guaranteed cleanup
# ---------------------------------------------------------------------------

def test_scores_endpoint_on_demand_analysis_with_cleanup(client, student_headers, monkeypatch):
    """Verify that on-demand analysis clones temporarily, executes model, caches result, and cleans up."""
    identity_svc = get_identity_service()
    identity_svc.register_team_member(TEAM_ID, "mem_alice", "alice_dev", "alice@test.edu")

    orchestrator = get_ingestion_orchestrator()
    orchestrator.save_checkpoint(
        TEAM_ID,
        IngestionCheckpoint(
            team_id=TEAM_ID,
            repo_url="https://github.com/mock/repo",
            total_commits_synced=10,
            is_completed=True,
            updated_at=datetime.now(timezone.utc),
        ),
    )

    # Track clone and cleanup calls
    cleanup_called = []
    github_svc = get_github_service()

    def mock_clone(repo_url, auth_token=None):
        return "C:/fake/temp/clone_dir"

    def mock_cleanup(path):
        cleanup_called.append(path)

    monkeypatch.setattr(github_svc, "clone_repository_temporarily", mock_clone)
    monkeypatch.setattr(github_svc, "cleanup_temporary_clone", mock_cleanup)

    # Register mock model callable
    aiml_svc = get_aiml_service()
    def mock_model(input_data):
        return {
            "team_id": input_data["team_id"],
            "model_version": "lite-0.1",
            "as_of": "2026-11-20",
            "members": [
                {
                    "member_id": "mem_alice",
                    "share": 1.0,
                    "facets": {"code": 1.0, "review": 0.0, "testing": 0.0, "docs": 0.0, "coordination": 0.0},
                    "flags": [],
                    "evidence": [],
                }
            ],
            "imbalance": {"gini": 0.0, "label": "balanced"},
            "warnings": [],
        }

    aiml_svc.register_model_callable(mock_model)

    response = client.get(f"/api/v1/teams/{TEAM_ID}/scores", headers=student_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["members"][0]["member_id"] == "mem_alice"
    assert data["members"][0]["share"] == 1.0

    # Verify cleanup was called
    assert cleanup_called == ["C:/fake/temp/clone_dir"]

    # Verify result was cached
    cached = load_cached_analysis(TEAM_ID)
    assert cached is not None
    assert cached.members[0].member_id == "mem_alice"


# ---------------------------------------------------------------------------
# Test 7: Cleanup guaranteed even on model failure
# ---------------------------------------------------------------------------

def test_scores_endpoint_cleanup_on_model_failure(client, student_headers, monkeypatch):
    """Verify that temporary clone is cleaned up even if the ML model raises an exception."""
    identity_svc = get_identity_service()
    identity_svc.register_team_member(TEAM_ID, "mem_alice", "alice_dev", "alice@test.edu")

    orchestrator = get_ingestion_orchestrator()
    orchestrator.save_checkpoint(
        TEAM_ID,
        IngestionCheckpoint(
            team_id=TEAM_ID,
            repo_url="https://github.com/mock/repo",
            total_commits_synced=10,
            is_completed=True,
            updated_at=datetime.now(timezone.utc),
        ),
    )

    cleanup_called = []
    github_svc = get_github_service()

    def mock_clone(repo_url, auth_token=None):
        return "C:/fake/temp/clone_to_fail"

    def mock_cleanup(path):
        cleanup_called.append(path)

    monkeypatch.setattr(github_svc, "clone_repository_temporarily", mock_clone)
    monkeypatch.setattr(github_svc, "cleanup_temporary_clone", mock_cleanup)

    aiml_svc = get_aiml_service()
    def failing_model(input_data):
        raise RuntimeError("Inference algorithm crashed")

    aiml_svc.register_model_callable(failing_model)

    response = client.get(f"/api/v1/teams/{TEAM_ID}/scores", headers=student_headers)
    assert response.status_code == 500
    assert "error executing ai/ml model" in response.json()["detail"].lower()

    # Guaranteed cleanup
    assert cleanup_called == ["C:/fake/temp/clone_to_fail"]


# ---------------------------------------------------------------------------
# Test 8: Auto-match invalidates cache only when mappings are created
# ---------------------------------------------------------------------------

def test_auto_match_invalidates_cache_only_when_created():
    """Verify that auto_match_from_commits invalidates cache if and only if new mappings are made."""
    identity_svc = get_identity_service()
    identity_svc.register_team_member(TEAM_ID, "mem_bob", "bob_dev", "bob@school.edu")

    sample_resp = AIMLAnalysisResponse(
        team_id=TEAM_ID,
        model_version="lite-0.1",
        as_of="2026-11-20",
        members=[],
        imbalance=ImbalanceAssessment(gini=0.0, label="balanced"),
        warnings=["insufficient_data"],
    )

    commits = [
        MinedCommit(
            sha="sha_bob_1",
            message="Initial commit",
            author=CommitAuthor(name="Bob Dev", email="bob@school.edu", date=None),
            files_changed=[],
            stats={"additions": 1, "deletions": 0, "total": 1},
        )
    ]

    # Pre-populate cache
    save_cached_analysis(TEAM_ID, sample_resp)
    assert load_cached_analysis(TEAM_ID) is not None

    # First auto-match creates a mapping -> must invalidate cache
    created = identity_svc.auto_match_from_commits(TEAM_ID, commits)
    assert created == 1
    assert load_cached_analysis(TEAM_ID) is None

    # Pre-populate cache again
    save_cached_analysis(TEAM_ID, sample_resp)
    assert load_cached_analysis(TEAM_ID) is not None

    # Second auto-match on same commit creates 0 mappings -> must NOT invalidate cache
    created2 = identity_svc.auto_match_from_commits(TEAM_ID, commits)
    assert created2 == 0
    assert load_cached_analysis(TEAM_ID) is not None


# ---------------------------------------------------------------------------
# Test 9: Successful sync invalidates cache; failed sync does not
# ---------------------------------------------------------------------------

def test_sync_cache_invalidation_behavior(monkeypatch):
    """Verify that successful sync invalidates cache, but failed sync preserves it."""
    import asyncio
    from app.services.job_service import get_job_service
    from app.services.github.exceptions import GitHubCloningError

    orchestrator = get_ingestion_orchestrator()
    job_svc = get_job_service()
    github_svc = get_github_service()

    sample_resp = AIMLAnalysisResponse(
        team_id=TEAM_ID,
        model_version="lite-0.1",
        as_of="2026-11-20",
        members=[],
        imbalance=ImbalanceAssessment(gini=0.0, label="balanced"),
        warnings=["insufficient_data"],
    )

    # 1. Test failed sync does NOT invalidate cache
    save_cached_analysis(TEAM_ID, sample_resp)
    assert load_cached_analysis(TEAM_ID) is not None

    def failing_clone(repo_url, auth_token=None):
        raise GitHubCloningError("Simulated network clone failure")

    monkeypatch.setattr(github_svc, "clone_repository_temporarily", failing_clone)

    failed_job = job_svc.create_job(team_id=TEAM_ID, kind="sync")
    asyncio.run(
        orchestrator.execute_sync(
            job_id=failed_job.id,
            team_id=TEAM_ID,
            repo_url="https://github.com/mock/repo",
            resume=False,
        )
    )

    job_state = job_svc.get_job(failed_job.id)
    assert job_state.status == "failed"
    # Cache must still be present!
    assert load_cached_analysis(TEAM_ID) is not None

    # 2. Test successful sync DOES invalidate cache
    def successful_clone(repo_url, auth_token=None):
        return "C:/fake/temp/clone_success"

    def mock_mine(repo_path, max_commits=None, resume_after_sha=None):
        return []

    async def mock_prs(owner, repo, page=1, per_page=30):
        return [], False

    monkeypatch.setattr(github_svc, "clone_repository_temporarily", successful_clone)
    monkeypatch.setattr(github_svc, "cleanup_temporary_clone", lambda p: None)
    monkeypatch.setattr(github_svc, "mine_repository_commits", mock_mine)
    monkeypatch.setattr(github_svc, "fetch_pull_requests_page", mock_prs)

    success_job = job_svc.create_job(team_id=TEAM_ID, kind="sync")
    asyncio.run(
        orchestrator.execute_sync(
            job_id=success_job.id,
            team_id=TEAM_ID,
            repo_url="https://github.com/mock/repo",
            resume=False,
        )
    )

    job_state2 = job_svc.get_job(success_job.id)
    assert job_state2.status == "completed"
    # Cache must be invalidated!
    assert load_cached_analysis(TEAM_ID) is None

