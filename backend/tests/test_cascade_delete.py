"""
Cascade Deletion Verification Test for FairShare.
Proves that deleting a Team cascades and completely cleans all rows across child tables:
- team_members
- identities
- commits -> file_changes (nested cascade)
- pull_requests -> reviews (nested cascade)
- issues
- scores -> evidence (nested cascade)
- alerts
- notes
- surveys
- jobs
"""

import sys
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Setup path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.base import Base
from app.models.team import User, Team, TeamMember
from app.models.git_data import Identity, Commit, FileChange, PullRequest, Review, Issue
from app.models.analysis import Score, Evidence, Alert, Note, Survey
from app.models.operational import Job, AuditLog, CorpusRepo
from scripts.seed import seed_database


def get_test_engine():
    """Create in-memory SQLite database with foreign keys enabled."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return engine


def run_cascade_test():
    engine = get_test_engine()
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()

    print("🧪 1. Testing seed script data integrity...")
    team_id = seed_database(db=session)
    assert team_id is not None

    team = session.get(Team, team_id)
    assert team is not None
    assert team.name == "CS490 Capstone - Group 4"

    # Verify counts
    assert session.query(TeamMember).filter_by(team_id=team_id).count() == 4
    assert session.query(Identity).filter_by(team_id=team_id).count() == 5  # 4 members + 1 bot
    assert session.query(Commit).filter_by(team_id=team_id).count() == 6
    assert session.query(FileChange).join(Commit).filter(Commit.team_id == team_id).count() > 0
    assert session.query(Score).filter_by(team_id=team_id).count() == 4

    # Verify score shares sum to 1.0
    shares_sum = sum(s.share for s in session.query(Score).filter_by(team_id=team_id).all())
    assert round(shares_sum, 2) == 1.00
    print(f"  ✓ Score shares sum to {shares_sum:.2f}")

    assert session.query(Evidence).join(Score).filter(Score.team_id == team_id).count() == 5
    assert session.query(Alert).filter_by(team_id=team_id).count() == 1
    assert session.query(Survey).filter_by(team_id=team_id).count() == 3

    # Verify survey percentages sum to 100
    survey_sum = sum(s.percent for s in session.query(Survey).filter_by(team_id=team_id).all())
    assert round(survey_sum, 1) == 100.0
    print(f"  ✓ Peer survey percentages sum to {survey_sum:.1f}%")

    print("\n🧪 2. Testing foreign keys with cascading deletes...")
    commit_ids = [c.id for c in session.query(Commit).filter_by(team_id=team_id).all()]
    score_ids = [s.id for s in session.query(Score).filter_by(team_id=team_id).all()]
    pr_ids = [p.id for p in session.query(PullRequest).filter_by(team_id=team_id).all()]

    # Delete team
    session.delete(team)
    session.commit()

    # 1. Team itself is deleted
    assert session.get(Team, team_id) is None
    print("  ✓ Team record deleted")

    # 2. Direct child tables
    assert session.query(TeamMember).filter_by(team_id=team_id).count() == 0
    assert session.query(Identity).filter_by(team_id=team_id).count() == 0
    assert session.query(Commit).filter_by(team_id=team_id).count() == 0
    assert session.query(PullRequest).filter_by(team_id=team_id).count() == 0
    assert session.query(Issue).filter_by(team_id=team_id).count() == 0
    assert session.query(Score).filter_by(team_id=team_id).count() == 0
    assert session.query(Alert).filter_by(team_id=team_id).count() == 0
    assert session.query(Note).filter_by(team_id=team_id).count() == 0
    assert session.query(Survey).filter_by(team_id=team_id).count() == 0
    assert session.query(Job).filter_by(team_id=team_id).count() == 0
    print("  ✓ Direct child tables completely cleared (10 tables)")

    # 3. Grandchild tables (nested cascades)
    assert session.query(FileChange).filter(FileChange.commit_id.in_(commit_ids)).count() == 0
    assert session.query(Evidence).filter(Evidence.score_id.in_(score_ids)).count() == 0
    assert session.query(Review).filter(Review.pull_request_id.in_(pr_ids)).count() == 0
    print("  ✓ Nested cascades completely cleared (file_changes, evidence, reviews)")

    # 4. Independent global entities must remain intact
    assert session.query(User).count() >= 5
    assert session.query(CorpusRepo).count() >= 1
    print("  ✓ Global isolated entities intact (users, corpus_repos)")

    session.close()
    print("\n🎉 ALL CASCADE DELETE TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_cascade_test()

