"""Performance & Scalability Benchmark Test (5,000 Commits).

Validates query execution time and index utilization against fairshare_test_db.
Ensures point queries execute in < 50 ms and aggregations in < 500 ms.
"""

import pytest
from scripts.benchmark_db import run_benchmark, get_test_db_url


def test_5000_commits_query_performance():
    """Verify query performance on an isolated 5,000-commit repository dataset."""
    test_url = get_test_db_url()
    # Safety assertion
    assert "fairshare_test_db" in test_url
    assert "fairshare_db" not in test_url.replace("fairshare_test_db", "")

    results = run_benchmark(db_url=test_url, commit_count=5000)

    assert results["success"] is True
    assert results["commit_count"] == 5000

    # Validate specific query latencies
    queries = results["queries"]

    # Q1: Scores by Team & Week
    assert queries["scores_by_team_week"]["latency_ms"] < 500
    assert queries["scores_by_team_week"]["index_verified"] is True

    # Q2: Evidence by Score ID
    assert queries["evidence_by_score_id"]["latency_ms"] < 100
    assert queries["evidence_by_score_id"]["index_verified"] is True

    # Q3: Commit lookup by SHA
    assert queries["commit_by_sha"]["latency_ms"] < 50
    assert queries["commit_by_sha"]["index_verified"] is True

    # Q4: Commits in Weekly Window
    assert queries["commits_in_window"]["latency_ms"] < 200

    # Q5: Aggregation over 5,000 commits
    assert queries["aggregate_5k_commits"]["latency_ms"] < 300
