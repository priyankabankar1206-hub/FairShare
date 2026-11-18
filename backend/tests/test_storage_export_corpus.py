"""Tests for Storage Structure, Research Export, Seed Idempotency, and Corpus Mining."""

import os
import shutil
import tempfile
import uuid
from pathlib import Path
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import SessionLocal
from app.models.team import User, Team, TeamMember
from app.models.git_data import Identity, Commit, FileChange, PullRequest, Review, Issue
from app.models.analysis import Score, Evidence, Alert, Note, Survey
from app.models.operational import Job, AuditLog, CorpusRepo
from app.services.storage import FileStorageManager, storage_manager, delete_team_completely
from scripts.seed import seed_database
from scripts.export_research import export_anonymised_team, hash_path, check_team_research_consent
from scripts.mine_corpus import log_corpus_repo, list_corpus_repos, verify_corpus_repo


# ==============================================================================
# 1. Synthetic Team Seed Repeatability & Integrity Tests
# ==============================================================================

def test_seed_database_contract_and_idempotency():
    """Verify seed script creates complete graph and can run repeatedly without duplication."""
    db = SessionLocal()
    try:
        # First run
        team_id_1 = seed_database(db=db)
        assert team_id_1 is not None

        team = db.get(Team, team_id_1)
        assert team is not None
        assert team.name == "CS490 Capstone - Group 4"

        # Verify members
        members = db.query(TeamMember).filter_by(team_id=team_id_1).all()
        assert len(members) == 4
        assert all(m.consent_at is not None for m in members)

        # Verify score shares sum to exactly 1.00
        scores = db.query(Score).filter_by(team_id=team_id_1).all()
        assert len(scores) == 4
        assert round(sum(s.share for s in scores), 2) == 1.00

        # Verify peer survey ratings sum to 100%
        surveys = db.query(Survey).filter_by(team_id=team_id_1).all()
        assert len(surveys) == 3
        assert round(sum(s.percent for s in surveys), 1) == 100.0

                # Second run: must skip without deleting or duplicating data
        original_member_count = db.query(TeamMember).filter_by(
            team_id=team_id_1
        ).count()

        original_commit_count = db.query(Commit).filter_by(
            team_id=team_id_1
        ).count()

        team_id_2 = seed_database(db=db)

        assert team_id_2 == team_id_1

        assert db.query(TeamMember).filter_by(
            team_id=team_id_1
        ).count() == original_member_count

        assert db.query(Commit).filter_by(
            team_id=team_id_1
        ).count() == original_commit_count
    finally:
        db.close()


# ==============================================================================
# 2. Anonymized Research Export & Retention Policy Tests
# ==============================================================================

def test_research_export_excludes_unconsented_teams():
    """Teams where at least one member has not consented must be excluded from research export."""
    db = SessionLocal()
    test_team_id = f"t_unconsented_{uuid.uuid4().hex[:8]}"
    u_id = f"u_uncons_{uuid.uuid4().hex[:8]}"
    try:
        user = User(id=u_id, github_login=f"gh_{u_id}", role="student")
        team = Team(id=test_team_id, name="Unconsented Research Team", course="CS 401", repo_url="https://github.com/test/uncons")
        db.add_all([user, team])
        db.flush()

        # Member with NO consent (consent_at is None)
        member = TeamMember(id=f"tm_{uuid.uuid4().hex[:8]}", team_id=test_team_id, user_id=u_id, consent_at=None)
        db.add(member)
        db.commit()

        # Export attempt must return None
        export_result = export_anonymised_team(db, team)
        assert export_result is None
    finally:
        db.query(TeamMember).filter_by(team_id=test_team_id).delete()
        db.query(Team).filter_by(id=test_team_id).delete()
        db.query(User).filter_by(id=u_id).delete()
        db.commit()
        db.close()


def test_research_export_anonymization_and_retention():
    """Verify research export strips PII, hashes paths preserving extensions, and flags retention."""
    db = SessionLocal()
    try:
        team = db.query(Team).filter(Team.name == "CS490 Capstone - Group 4").first()
        assert team is not None

        # 1. Test with missing retention decision -> must flag instructor decision required
        payload = export_anonymised_team(db, team, retention_until=None)
        assert payload is not None
        assert payload["retention"]["retention_policy"] == "instructor_decision_required"
        assert payload["retention"]["retention_until"] is None
        assert payload["retention"]["retention_decision_status"] == "pending_instructor_decision"

        # 2. Test with explicit retention decision
        payload_with_retention = export_anonymised_team(db, team, retention_until="2027-06-30T00:00:00Z")
        assert payload_with_retention["retention"]["retention_policy"] == "specified"
        assert payload_with_retention["retention"]["retention_until"] == "2027-06-30T00:00:00Z"

        # 3. Check personal data stripped
        payload_str = str(payload)
        assert "alice@example.com" not in payload_str
        assert "bob@cs.univ.edu" not in payload_str
        assert "Implement core auth and session handling" not in payload_str  # Commit message dropped
        assert "anon_student_001" in payload_str  # Replaced with anonymised_id

        # 4. Check file path hashing preserves extension
        hashed_py = hash_path("backend/app/auth/security.py")
        assert hashed_py.endswith(".py")
        assert "security" not in hashed_py

        hashed_md = hash_path("docs/architecture.md")
        assert hashed_md.endswith(".md")
        assert "architecture" not in hashed_md
    finally:
        db.close()


# ==============================================================================
# 3. File Storage Structure & Orphan Cleanup Tests
# ==============================================================================

def test_file_storage_structure_and_orphan_cleanup(tmp_path):
    """Test file storage directories, artifact paths, and safe orphan temporary clone cleanup."""
    storage = FileStorageManager(base_data_dir=tmp_path)
    test_team_id = "t_storage_test_001"

    # Verify directory paths
    raw_dir = storage.get_raw_dir(test_team_id)
    assert raw_dir.exists()
    assert raw_dir.name == "raw"

    feat_dir = storage.get_features_dir(test_team_id)
    assert feat_dir.exists()
    assert feat_dir.name == "features"

    graphs_dir = storage.get_graphs_dir(test_team_id)
    assert graphs_dir.exists()
    assert graphs_dir.name == "graphs"

    analysis_dir = storage.get_analysis_dir(test_team_id)
    assert analysis_dir.exists()
    assert analysis_dir.name == "analysis"

    # Verify specific file paths
    feat_file = storage.get_feature_file_path(test_team_id, "abc123sha")
    assert feat_file.name == "abc123sha.npy"

    graph_file = storage.get_graph_file_path(test_team_id, 4)
    assert graph_file.name == "week_4.pt"

    # Verify dedicated research export dir
    research_dir = storage.get_research_export_dir()
    assert research_dir.exists()
    assert research_dir.name == "research_export"

    # Test orphan clone cleanup: create an expired simulated clone
    sys_temp = Path(tempfile.gettempdir())
    orphan_clone = sys_temp / f"fairshare_clone_{uuid.uuid4().hex[:8]}"
    orphan_clone.mkdir(parents=True, exist_ok=True)
    (orphan_clone / "dummy.git").write_text("git data")
    assert orphan_clone.exists()

    # Run cleanup with max_age_seconds=0 so it cleans immediately
    cleanup_report = storage.cleanup_orphaned_clones(
    max_age_seconds=0,
    target_path=orphan_clone,
    )
    assert cleanup_report["cleaned_count"] >= 1
    assert str(orphan_clone) in cleanup_report["cleaned_paths"]
    assert not orphan_clone.exists()

    # Test team storage deletion
    storage.delete_team_storage(test_team_id)
    assert not (tmp_path / test_team_id).exists()


# ==============================================================================
# 4. Corpus Repository Database & Mining Utility Tests
# ==============================================================================

def test_corpus_repo_logging_and_listing():
    """Verify corpus_repos table logging, updating, and querying."""
    db = SessionLocal()
    try:
        test_repo_name = f"test-owner/test-repo-{uuid.uuid4().hex[:6]}"

        # Log new corpus repo
        repo = log_corpus_repo(
            full_name=test_repo_name,
            licence="MIT",
            commit_count=1250,
            contributors=45,
            db=db,
        )
        assert repo.id is not None
        assert repo.full_name == test_repo_name
        assert repo.commit_count == 1250

        # Verify presence
        assert verify_corpus_repo(test_repo_name, db=db) is True

        # Update existing corpus repo
        updated_repo = log_corpus_repo(
            full_name=test_repo_name,
            licence="Apache-2.0",
            commit_count=1300,
            contributors=50,
            db=db,
        )
        assert updated_repo.id == repo.id
        assert updated_repo.licence == "Apache-2.0"
        assert updated_repo.commit_count == 1300

        # List repos
        repos = list_corpus_repos(db=db)
        names = [r["full_name"] for r in repos]
        assert test_repo_name in names
    finally:
        db.query(CorpusRepo).filter(CorpusRepo.full_name == test_repo_name).delete()
        db.commit()
        db.close()


# ==============================================================================
# 5. Cascading Delete Test with Real PostgreSQL Session
# ==============================================================================

def test_cascade_deletion_cleans_all_child_tables():
    """Verify deleting a Team cascades across all 10 child tables and clears disk files."""
    db = SessionLocal()
    team_id = f"t_cascade_{uuid.uuid4().hex[:8]}"
    u_id = f"u_casc_{uuid.uuid4().hex[:8]}"
    storage = FileStorageManager()

    from datetime import datetime, timezone

    try:
        user = User(id=u_id, github_login=f"gh_{u_id}", role="student")
        team = Team(id=team_id, name="Cascade Test Team", course="CS 401", repo_url="https://github.com/test/casc")
        db.add_all([user, team])
        db.flush()

        member = TeamMember(id=f"tm_{uuid.uuid4().hex[:8]}", team_id=team_id, user_id=u_id, consent_at=None)
        db.add(member)
        db.flush()

        ident = Identity(id=str(uuid.uuid4()), team_id=team_id, git_name="Test User", git_email="test@user.com", member_id=member.id)
        db.add(ident)
        db.flush()

        now = datetime.now(timezone.utc)
        commit = Commit(
            id=str(uuid.uuid4()),
            team_id=team_id,
            identity_id=ident.id,
            sha=f"sha_{uuid.uuid4().hex[:8]}",
            message="test commit",
            committed_at=now,
            additions=10,
            deletions=2,
        )
        db.add(commit)
        db.flush()

        fc = FileChange(id=str(uuid.uuid4()), commit_id=commit.id, path="app/test.py", language="python", additions=10, deletions=2)
        db.add(fc)

        score = Score(
            id=str(uuid.uuid4()),
            team_id=team_id,
            member_id=member.id,
            week=1,
            model_version="1.0",
            share=1.0,
            facets={"code": 1.0},
            flags=[],
        )
        db.add(score)
        db.flush()

        ev = Evidence(id=str(uuid.uuid4()), score_id=score.id, commit_sha=commit.sha, reason="test reason", rank=1)
        db.add(ev)

        alert = Alert(id=str(uuid.uuid4()), team_id=team_id, week=1, label="watch", gini=0.2)
        db.add(alert)

        db.commit()

        # Create dummy file
        raw_dir = storage.get_raw_dir(team_id)
        (raw_dir / "sample.json").write_text("{}")
        assert (raw_dir / "sample.json").exists()

        # Execute unified cascading delete
        result = delete_team_completely(db, team_id, storage=storage)
        assert result is True

        # Verify DB is clean
        assert db.get(Team, team_id) is None
        assert db.query(TeamMember).filter_by(team_id=team_id).count() == 0
        assert db.query(Identity).filter_by(team_id=team_id).count() == 0
        assert db.query(Commit).filter_by(team_id=team_id).count() == 0
        assert db.query(FileChange).filter_by(commit_id=commit.id).count() == 0
        assert db.query(Score).filter_by(team_id=team_id).count() == 0
        assert db.query(Evidence).filter_by(score_id=score.id).count() == 0
        assert db.query(Alert).filter_by(team_id=team_id).count() == 0

        # Verify disk directory was deleted
        assert not storage.get_team_root_dir(team_id).exists()
    finally:
        storage.delete_team_storage(team_id)
        db.query(User).filter_by(id=u_id).delete()
        db.commit()
        db.close()
