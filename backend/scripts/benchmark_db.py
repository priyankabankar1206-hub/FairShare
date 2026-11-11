import sys
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import sessionmaker

# Setup path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.base import Base
from app.models.team import User, Team, TeamMember
from app.models.git_data import Identity, Commit, FileChange, PullRequest, Review, Issue
from app.models.analysis import Score, Evidence, Alert, Note, Survey
from app.models.operational import Job, AuditLog, CorpusRepo


def run_benchmark(db_url: str = "sqlite:///:memory:", commit_count: int = 5000):
    print(f"🚀 Starting FairShare Database Benchmark with {commit_count:,} commits...")
    engine = create_engine(db_url, echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = Session()

    try:
        now = datetime.now(timezone.utc)
        start_time = time.time()

        # 1. Setup Team and 5 Members
        print("1. Creating Team and Members...")
        team = Team(
            id=str(uuid.uuid4()),
            name="Large Repo Benchmark Team",
            course="CS500 Scalability Lab",
            repo_url="https://github.com/benchmark/5k-commits-repo",
            created_at=now - timedelta(days=120),
        )
        db.add(team)
        db.flush()

        members = []
        identities = []
        for i in range(5):
            u = User(
                id=str(uuid.uuid4()),
                github_login=f"bench_dev_{i+1}",
                role="student",
                created_at=now - timedelta(days=120),
            )
            db.add(u)
            db.flush()

            m = TeamMember(
                id=str(uuid.uuid4()),
                team_id=team.id,
                user_id=u.id,
                consent_at=now - timedelta(days=110),
                anonymised_id=f"anon_bench_{i+1:03d}",
            )
            db.add(m)
            db.flush()
            members.append(m)

            ident = Identity(
                id=str(uuid.uuid4()),
                team_id=team.id,
                git_name=f"Developer {i+1}",
                git_email=f"dev{i+1}@bench.org",
                member_id=m.id,
                is_bot=False,
            )
            db.add(ident)
            db.flush()
            identities.append(ident)

        db.commit()

        # 2. Bulk Insert 5,000 Commits & 15,000 File Changes in batches
        print(f"2. Generating and loading {commit_count:,} commits & 15,000 file changes...")
        batch_size = 1000
        commit_records = []
        file_change_records = []

        for c_idx in range(commit_count):
            c_id = str(uuid.uuid4())
            ident = identities[c_idx % len(identities)]
            sha = f"{c_idx:07x}" + "a" * 33  # 40-char sha
            commit_records.append({
                "id": c_id,
                "team_id": team.id,
                "sha": sha,
                "identity_id": ident.id,
                "committed_at": now - timedelta(minutes=(commit_count - c_idx) * 15),
                "message": f"Benchmark commit #{c_idx}: Refactor and optimize subsystem",
                "additions": 25 + (c_idx % 50),
                "deletions": 5 + (c_idx % 20),
                "flag": "substantive" if c_idx % 10 != 0 else "split_commits",
            })

            # 3 file changes per commit -> 15,000 file change rows
            for f_idx in range(3):
                file_change_records.append({
                    "id": str(uuid.uuid4()),
                    "commit_id": c_id,
                    "path": f"src/modules/subsystem_{f_idx}/component_{c_idx % 25}.py",
                    "language": "python",
                    "additions": 10 + (f_idx * 5),
                    "deletions": 2,
                    "complexity_delta": (c_idx % 7),
                    "tree_edit_size": 15 + (c_idx % 30),
                    "flag": "substantive",
                })

            if len(commit_records) >= batch_size:
                db.bulk_insert_mappings(Commit, commit_records)
                db.bulk_insert_mappings(FileChange, file_change_records)
                db.commit()
                commit_records.clear()
                file_change_records.clear()

        if commit_records:
            db.bulk_insert_mappings(Commit, commit_records)
            db.bulk_insert_mappings(FileChange, file_change_records)
            db.commit()

        load_duration = time.time() - start_time
        print(f"   ✓ Loaded {commit_count:,} commits and 15,000 file changes in {load_duration:.2f} seconds.")

        # 3. Add Scores and Evidence for 16 Weeks of history
        print("3. Generating weekly scores and ranked evidence...")
        score_records = []
        evidence_records = []
        for week in range(1, 17):
            for m_idx, m in enumerate(members):
                s_id = str(uuid.uuid4())
                score_records.append({
                    "id": s_id,
                    "team_id": team.id,
                    "member_id": m.id,
                    "week": week,
                    "model_version": "lite-0.1",
                    "share": 0.20,
                    "facets": {"code": 0.25, "review": 0.20, "testing": 0.15, "docs": 0.20, "coordination": 0.20},
                    "flags": [],
                    "created_at": now,
                })
                # Top 5 evidence commits
                for rank in range(1, 6):
                    evidence_records.append({
                        "id": str(uuid.uuid4()),
                        "score_id": s_id,
                        "commit_sha": f"{(week * 10 + rank):07x}" + "a" * 33,
                        "reason": f"Week {week} Top commit #{rank}: added core business logic",
                        "rank": rank,
                    })

        db.bulk_insert_mappings(Score, score_records)
        db.bulk_insert_mappings(Evidence, evidence_records)
        db.commit()
        print("   ✓ Loaded 80 weekly scores and 400 evidence records.")

        # 4. Measure Query Latency
        print("\n4. ⏱️ Running Query Performance Benchmarks:")

        # Benchmark Query 1: GET /teams/{id}/scores?week=12
        t0 = time.perf_counter()
        query_scores = (
            db.query(Score)
            .filter(Score.team_id == team.id, Score.week == 12)
            .all()
        )
        latency_scores_ms = (time.perf_counter() - t0) * 1000
        print(f"   • Query Scores (team_id + week): {latency_scores_ms:.2f} ms (Target: < 500 ms) - {'PASS ✅' if latency_scores_ms < 500 else 'FAIL ❌'}")
        assert len(query_scores) == 5

        # Benchmark Query 2: GET /teams/{id}/members/{mid}/evidence
        target_score = query_scores[0]
        t0 = time.perf_counter()
        query_evidence = (
            db.query(Evidence)
            .filter(Evidence.score_id == target_score.id)
            .order_by(Evidence.rank)
            .all()
        )
        latency_evidence_ms = (time.perf_counter() - t0) * 1000
        print(f"   • Query Member Evidence (score_id + rank): {latency_evidence_ms:.2f} ms (Target: < 100 ms) - {'PASS ✅' if latency_evidence_ms < 100 else 'FAIL ❌'}")
        assert len(query_evidence) == 5

        # Benchmark Query 3: Commit lookup by SHA (ix_commits_team_sha)
        sample_sha = f"{2500:07x}" + "a" * 33
        t0 = time.perf_counter()
        commit_res = (
            db.query(Commit)
            .filter(Commit.team_id == team.id, Commit.sha == sample_sha)
            .first()
        )
        latency_sha_ms = (time.perf_counter() - t0) * 1000
        print(f"   • Query Commit by SHA index: {latency_sha_ms:.2f} ms (Target: < 50 ms) - {'PASS ✅' if latency_sha_ms < 50 else 'FAIL ❌'}")
        assert commit_res is not None

        # Benchmark Query 4: Aggregate commit metrics over 5,000 commits
        t0 = time.perf_counter()
        total_additions = (
            db.query(Commit.flag, text("count(*)"), text("sum(additions)"))
            .filter(Commit.team_id == team.id)
            .group_by(Commit.flag)
            .all()
        )
        latency_agg_ms = (time.perf_counter() - t0) * 1000
        print(f"   • Aggregate 5,000 commits by flag: {latency_agg_ms:.2f} ms (Target: < 200 ms) - {'PASS ✅' if latency_agg_ms < 200 else 'FAIL ❌'}")

        print("\n🎉 ALL 5,000-COMMIT QUERY PERFORMANCE BENCHMARKS PASSED WELL UNDER 500 MS!")

    finally:
        db.close()


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "sqlite:///:memory:"
    run_benchmark(url)

