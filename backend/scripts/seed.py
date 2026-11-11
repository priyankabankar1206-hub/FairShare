"""
Synthetic database seeder for FairShare.
Populates a complete mock team matching the exact contract in Section 6.4 of the docs:
- 1 Instructor user
- 4 Student users with consented memberships
- Realistic identities (including 1 bot identity)
- Commits & file changes with complexity and AST metrics
- Pull requests, reviews, and issues
- Valid weekly scores (shares summing to 1.0, 5 facet scores, flags, and ranked evidence)
- Imbalance alerts (Gini, label)
- Instructor notes
- Peer contribution survey (ratings summing to 100%)
- Mined open-source corpus repository entries
"""

import sys
import os
from datetime import datetime, timezone, timedelta
import uuid

# Ensure backend root is on Python path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.models.team import User, Team, TeamMember
from app.models.git_data import Identity, Commit, FileChange, PullRequest, Review, Issue
from app.models.analysis import Score, Evidence, Alert, Note, Survey
from app.models.operational import Job, AuditLog, CorpusRepo


def seed_database(db=None):
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        print("🌱 Seeding FairShare database with synthetic data...")

        # 1. Clean existing seed data if exists
        existing_team = db.query(Team).filter(Team.name == "CS490 Capstone - Group 4").first()
        if existing_team:
            print(f"Cleaning existing test team: {existing_team.id}")
            db.delete(existing_team)
            db.commit()

        # 2. Create Users (1 Instructor, 4 Students)
        now = datetime.now(timezone.utc)
        instructor = db.query(User).filter(User.github_login == "prof_alan").first()
        if not instructor:
            instructor = User(
                id=str(uuid.uuid4()),
                github_login="prof_alan",
                role="instructor",
                created_at=now - timedelta(days=90),
            )
            db.add(instructor)

        students_data = [
            ("alice_dev", "student"),
            ("bob_coder", "student"),
            ("carol_engineer", "student"),
            ("dave_builder", "student"),
        ]
        student_users = []
        for login, role in students_data:
            user = db.query(User).filter(User.github_login == login).first()
            if not user:
                user = User(
                    id=str(uuid.uuid4()),
                    github_login=login,
                    role=role,
                    created_at=now - timedelta(days=60),
                )
                db.add(user)
            student_users.append(user)

        db.flush()

        # 3. Create Team
        team = Team(
            id=str(uuid.uuid4()),
            name="CS490 Capstone - Group 4",
            course="CS490 Software Engineering",
            repo_url="https://github.com/capstone2026/team-fairshare",
            created_at=now - timedelta(days=45),
        )
        db.add(team)
        db.flush()

        # 4. Create Team Members (all consented)
        members = []
        for idx, user in enumerate(student_users):
            member = TeamMember(
                id=str(uuid.uuid4()),
                team_id=team.id,
                user_id=user.id,
                consent_at=now - timedelta(days=40),
                anonymised_id=f"anon_student_{idx + 1:03d}",
            )
            db.add(member)
            members.append(member)

        db.flush()

        # 5. Create Identities (mapped git names & emails + 1 bot)
        identities_info = [
            (members[0].id, "Alice Smith", "alice@example.com", False),
            (members[1].id, "Bob Johnson", "bob@cs.univ.edu", False),
            (members[2].id, "Carol White", "carol.w@gmail.com", False),
            (members[3].id, "Dave Miller", "dave@example.org", False),
            (None, "dependabot[bot]", "bot@github.com", True),
        ]
        identities = []
        for member_id, git_name, git_email, is_bot in identities_info:
            ident = Identity(
                id=str(uuid.uuid4()),
                team_id=team.id,
                git_name=git_name,
                git_email=git_email,
                member_id=member_id,
                is_bot=is_bot,
            )
            db.add(ident)
            identities.append(ident)

        db.flush()

        # 6. Create Commits & File Changes
        commits_data = [
            (identities[0], "3f2a9c1", "Implement core auth and session handling", 240, 15, "substantive", [
                ("backend/app/auth/router.py", "python", 140, 5, 8, 35, "substantive"),
                ("backend/app/auth/security.py", "python", 100, 10, 4, 22, "substantive"),
            ]),
            (identities[0], "8b1e4a2", "Add unit tests for JWT validation", 95, 2, "substantive", [
                ("backend/tests/test_auth.py", "python", 95, 2, 2, 18, "substantive"),
            ]),
            (identities[1], "a4c21e0", "Set up database connection pool and models", 180, 20, "substantive", [
                ("backend/app/db/session.py", "python", 80, 5, 3, 14, "substantive"),
                ("backend/app/models/user.py", "python", 100, 15, 5, 25, "substantive"),
            ]),
            (identities[2], "d91a7f3", "Add documentation and API swagger schema", 60, 4, "substantive", [
                ("docs/architecture.md", "markdown", 50, 2, 0, 0, "substantive"),
                ("backend/app/main.py", "python", 10, 2, 1, 4, "substantive"),
            ]),
            (identities[3], "5e2b09a", "Format code whitespace and indentations", 120, 115, "no-op", [
                ("backend/app/auth/router.py", "python", 60, 58, 0, 0, "whitespace-only"),
                ("backend/app/models/user.py", "python", 60, 57, 0, 0, "whitespace-only"),
            ]),
            (identities[3], "7f33d1c", "Split commit part 1: rename variable temp to buf", 1, 1, "split_commits", [
                ("backend/app/utils.py", "python", 1, 1, 0, 1, "rename-only"),
            ]),
        ]

        created_commits = []
        for ident, sha, msg, add, dele, flag, files in commits_data:
            cmt = Commit(
                id=str(uuid.uuid4()),
                team_id=team.id,
                sha=sha,
                identity_id=ident.id,
                committed_at=now - timedelta(days=20),
                message=msg,
                additions=add,
                deletions=dele,
                flag=flag,
            )
            db.add(cmt)
            db.flush()
            created_commits.append(cmt)

            for f_path, lang, f_add, f_del, comp_d, ast_sz, f_flag in files:
                fc = FileChange(
                    id=str(uuid.uuid4()),
                    commit_id=cmt.id,
                    path=f_path,
                    language=lang,
                    additions=f_add,
                    deletions=f_del,
                    complexity_delta=comp_d,
                    tree_edit_size=ast_sz,
                    flag=f_flag,
                )
                db.add(fc)

        db.flush()

        # 7. Pull Requests & Reviews
        pr1 = PullRequest(
            id=str(uuid.uuid4()),
            team_id=team.id,
            number=1,
            author_member_id=members[0].id,
            opened_at=now - timedelta(days=18),
            merged_at=now - timedelta(days=17),
            state="merged",
        )
        db.add(pr1)
        db.flush()

        rev1 = Review(
            id=str(uuid.uuid4()),
            pull_request_id=pr1.id,
            reviewer_member_id=members[1].id,
            submitted_at=now - timedelta(days=17, hours=2),
            state="APPROVED",
            comment_count=4,
        )
        db.add(rev1)

        # 8. Issues
        issue1 = Issue(
            id=str(uuid.uuid4()),
            team_id=team.id,
            number=101,
            author_member_id=members[2].id,
            labels={"category": "bug", "priority": "high"},
            opened_at=now - timedelta(days=25),
            closed_at=now - timedelta(days=17),
        )
        db.add(issue1)
        db.flush()

        # 9. Scores, Facets, Flags, and Evidence (Matching Section 6.4 contract exactly)
        # Week 3 Scores: Alice 41%, Bob 30%, Carol 19%, Dave 10% (sum = 1.00)
        scores_payload = [
            (
                members[0].id,
                0.41,
                {"code": 0.52, "review": 0.30, "testing": 0.25, "docs": 0.10, "coordination": 0.20},
                ["split_commits"],
                [
                    ("3f2a9c1", "Added 3 functions, complexity +9, 85% of lines survive, 4 files depend on it", 1),
                    ("8b1e4a2", "Added test suite with 12 assertions covering auth flows", 2),
                ],
            ),
            (
                members[1].id,
                0.30,
                {"code": 0.32, "review": 0.45, "testing": 0.20, "docs": 0.15, "coordination": 0.25},
                [],
                [
                    ("a4c21e0", "Configured async db connection pool and session generator", 1),
                ],
            ),
            (
                members[2].id,
                0.19,
                {"code": 0.10, "review": 0.15, "testing": 0.10, "docs": 0.65, "coordination": 0.35},
                [],
                [
                    ("d91a7f3", "Authored comprehensive project architecture documentation", 1),
                ],
            ),
            (
                members[3].id,
                0.10,
                {"code": 0.06, "review": 0.10, "testing": 0.45, "docs": 0.10, "coordination": 0.20},
                ["whitespace_churn", "split_commits"],
                [
                    ("5e2b09a", "Formatting-only commit filtered out as no-op by tree-sitter", 1),
                ],
            ),
        ]

        for member_id, share, facets, flags, evidences in scores_payload:
            score = Score(
                id=str(uuid.uuid4()),
                team_id=team.id,
                member_id=member_id,
                week=3,
                model_version="lite-0.1",
                share=share,
                facets=facets,
                flags=flags,
            )
            db.add(score)
            db.flush()

            for c_sha, reason, rank in evidences:
                ev = Evidence(
                    id=str(uuid.uuid4()),
                    score_id=score.id,
                    commit_sha=c_sha,
                    reason=reason,
                    rank=rank,
                )
                db.add(ev)

        # 10. Imbalance Alert (Section 6.4: Gini 0.34, label "watch")
        alert = Alert(
            id=str(uuid.uuid4()),
            team_id=team.id,
            week=3,
            label="watch",
            gini=0.34,
            details={
                "message": "Work is concentrated in two members (Alice, Bob).",
                "recommended_action": "Review task distribution for upcoming milestone.",
            },
        )
        db.add(alert)

        # 11. Instructor Note / Dispute Flag
        note = Note(
            id=str(uuid.uuid4()),
            team_id=team.id,
            author_id=instructor.id,
            member_id=members[3].id,
            kind="instructor_note",
            body="Dave had reported network hardware issues in week 2, which delayed his initial commit timeline.",
        )
        db.add(note)

        # 12. Peer Survey (Alice ratings for teammates summing to 100%)
        # Rater Alice rates Bob (40%), Carol (35%), Dave (25%) -> sum = 100%
        survey_ratings = [
            (members[0].id, members[1].id, 40.0),
            (members[0].id, members[2].id, 35.0),
            (members[0].id, members[3].id, 25.0),
        ]
        for rater_id, ratee_id, pct in survey_ratings:
            srv = Survey(
                id=str(uuid.uuid4()),
                team_id=team.id,
                rater_member_id=rater_id,
                ratee_member_id=ratee_id,
                percent=pct,
            )
            db.add(srv)

        # 13. Sync & Scoring Job Record
        job = Job(
            id=str(uuid.uuid4()),
            team_id=team.id,
            kind="sync",
            status="completed",
            progress=100,
            started_at=now - timedelta(minutes=15),
            finished_at=now - timedelta(minutes=12),
        )
        db.add(job)

        # 14. Audit Log Entry
        audit = AuditLog(
            id=str(uuid.uuid4()),
            actor_id=instructor.id,
            action="view_team_report",
            target=f"team:{team.id}:week:3",
        )
        db.add(audit)

        # 15. Corpus Repo Record (Mined open-source dataset for offline training)
        corpus = db.query(CorpusRepo).filter(CorpusRepo.full_name == "psf/requests").first()
        if not corpus:
            corpus = CorpusRepo(
                id=str(uuid.uuid4()),
                full_name="psf/requests",
                licence="Apache-2.0",
                commit_count=6540,
                contributors=620,
            )
            db.add(corpus)

        db.commit()
        print(f"✅ Seeding complete! Team '{team.name}' (ID: {team.id}) successfully created with full graph data.")
        return team.id

    except Exception as e:
        db.rollback()
        print(f"❌ Seeding failed: {e}")
        raise
    finally:
        if close_session:
            db.close()


if __name__ == "__main__":
    seed_database()

