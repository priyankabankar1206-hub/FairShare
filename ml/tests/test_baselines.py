# tests/test_baselines.py
# FairShare - Milestone 6
# Tests for baselines.py using small hand-made tables.
# Every expected number can be worked out with a calculator.
#
# Run:  pytest tests/test_baselines.py -v

import pandas as pd
import pytest

from baselines import OUTPUT_COLUMNS, compute_baseline_shares


def make_commits(rows: list[tuple]) -> pd.DataFrame:
    """
    Build a tiny commits table from (name, email, insertions) tuples.
    Only the columns the baselines need are included.
    """
    return pd.DataFrame(rows, columns=["author_name", "author_email", "insertions"])


def share_of(result: pd.DataFrame, email: str, column: str) -> float:
    """Pick one author's value from one column of the result."""
    return float(result.loc[result["author_email"] == email, column].iloc[0])


# ---------------------------------------------------------------------------
# Correct numbers
# ---------------------------------------------------------------------------

class TestShareValues:

    def test_b1_is_share_of_commit_count(self):
        """B1 is each author's share of the commit count."""
        # Alice 2 commits, Bob 1 commit -> 2/3 and 1/3
        commits = make_commits([
            ("Alice", "alice@uni.edu", 5),
            ("Alice", "alice@uni.edu", 5),
            ("Bob",   "bob@uni.edu",   5),
        ])
        result = compute_baseline_shares(commits)
        assert share_of(result, "alice@uni.edu", "b1_share") == pytest.approx(2 / 3)
        assert share_of(result, "bob@uni.edu", "b1_share") == pytest.approx(1 / 3)

    def test_b2_is_share_of_lines_added(self):
        """B2 is each author's share of the lines added."""
        # Alice adds 10 + 30 = 40 lines, Bob adds 60 -> 0.4 and 0.6
        commits = make_commits([
            ("Alice", "alice@uni.edu", 10),
            ("Alice", "alice@uni.edu", 30),
            ("Bob",   "bob@uni.edu",   60),
        ])
        result = compute_baseline_shares(commits)
        assert share_of(result, "alice@uni.edu", "b2_share") == pytest.approx(0.4)
        assert share_of(result, "bob@uni.edu", "b2_share") == pytest.approx(0.6)

    def test_b1_and_b2_can_disagree(self):
        """Many small commits raise B1 but not B2; one big commit does the opposite."""
        # The whole point of FairShare in one table:
        # Alice: 3 small commits (10 lines each) -> B1 = 0.75, B2 = 0.30
        # Bob:   1 big commit (70 lines)         -> B1 = 0.25, B2 = 0.70
        commits = make_commits([
            ("Alice", "alice@uni.edu", 10),
            ("Alice", "alice@uni.edu", 10),
            ("Alice", "alice@uni.edu", 10),
            ("Bob",   "bob@uni.edu",   70),
        ])
        result = compute_baseline_shares(commits)
        assert share_of(result, "alice@uni.edu", "b1_share") == pytest.approx(0.75)
        assert share_of(result, "alice@uni.edu", "b2_share") == pytest.approx(0.30)
        assert share_of(result, "bob@uni.edu", "b1_share") == pytest.approx(0.25)
        assert share_of(result, "bob@uni.edu", "b2_share") == pytest.approx(0.70)

    def test_counts_columns(self):
        """The commits and lines_added columns hold the raw totals."""
        commits = make_commits([
            ("Alice", "alice@uni.edu", 10),
            ("Alice", "alice@uni.edu", 30),
            ("Bob",   "bob@uni.edu",   60),
        ])
        result = compute_baseline_shares(commits)
        assert share_of(result, "alice@uni.edu", "commits") == 2
        assert share_of(result, "alice@uni.edu", "lines_added") == 40

    def test_each_share_column_sums_to_one(self):
        """Both share columns add up to 1.0."""
        commits = make_commits([
            ("Alice", "a@uni.edu", 7),
            ("Bob",   "b@uni.edu", 13),
            ("Cara",  "c@uni.edu", 22),
            ("Cara",  "c@uni.edu", 1),
        ])
        result = compute_baseline_shares(commits)
        assert result["b1_share"].sum() == pytest.approx(1.0)
        assert result["b2_share"].sum() == pytest.approx(1.0)

    def test_single_author_gets_everything(self):
        """A one-person team has a 100% share in both baselines."""
        commits = make_commits([("Alice", "alice@uni.edu", 4)])
        result = compute_baseline_shares(commits)
        assert share_of(result, "alice@uni.edu", "b1_share") == pytest.approx(1.0)
        assert share_of(result, "alice@uni.edu", "b2_share") == pytest.approx(1.0)

    def test_output_columns_and_stable_order(self):
        """Columns follow OUTPUT_COLUMNS and rows are sorted by email."""
        commits = make_commits([
            ("Bob",   "bob@uni.edu",   1),
            ("Alice", "alice@uni.edu", 1),
        ])
        result = compute_baseline_shares(commits)
        assert list(result.columns) == OUTPUT_COLUMNS
        # Sorted by email, not by who appeared first
        assert list(result["author_email"]) == ["alice@uni.edu", "bob@uni.edu"]


# ---------------------------------------------------------------------------
# Zero totals and empty input (no division by zero)
# ---------------------------------------------------------------------------

class TestZeroAndEmpty:

    def test_zero_lines_total_gives_zero_b2_not_nan(self):
        """A zero lines-added total gives B2 shares of 0.0, not NaN or a crash."""
        # Nobody added a line: B2 total is 0. Must not crash or give NaN.
        commits = make_commits([
            ("Alice", "alice@uni.edu", 0),
            ("Bob",   "bob@uni.edu",   0),
        ])
        result = compute_baseline_shares(commits)
        assert (result["b2_share"] == 0.0).all()
        assert not result["b2_share"].isna().any()

    def test_zero_lines_does_not_break_b1(self):
        """B1 still works when nobody added a line."""
        commits = make_commits([
            ("Alice", "alice@uni.edu", 0),
            ("Bob",   "bob@uni.edu",   0),
        ])
        result = compute_baseline_shares(commits)
        assert result["b1_share"].sum() == pytest.approx(1.0)

    def test_empty_table_returns_empty_result_with_columns(self):
        """An empty commits table gives an empty result with the right columns."""
        empty = pd.DataFrame(columns=["author_name", "author_email", "insertions"])
        result = compute_baseline_shares(empty)
        assert result.empty
        assert list(result.columns) == OUTPUT_COLUMNS


# ---------------------------------------------------------------------------
# Input checking
# ---------------------------------------------------------------------------

class TestInputChecks:

    def test_missing_insertions_column_raises(self):
        """A missing 'insertions' column gives a clear ValueError."""
        bad = pd.DataFrame({"author_email": ["a@uni.edu"]})
        with pytest.raises(ValueError, match="insertions"):
            compute_baseline_shares(bad)

    def test_missing_email_column_raises(self):
        """A missing 'author_email' column gives a clear ValueError."""
        bad = pd.DataFrame({"insertions": [3]})
        with pytest.raises(ValueError, match="author_email"):
            compute_baseline_shares(bad)

    def test_input_table_is_not_modified(self):
        """The caller's DataFrame is left untouched."""
        commits = make_commits([("Alice", "Alice@Uni.edu", 5)])
        before = commits.copy()
        compute_baseline_shares(commits)
        pd.testing.assert_frame_equal(commits, before)

    def test_missing_author_name_column_raises(self):
        """A missing 'author_name' column gives a clear ValueError."""
        bad = pd.DataFrame({"author_email": ["a@uni.edu"], "insertions": [3]})
        with pytest.raises(ValueError, match="author_name"):
            compute_baseline_shares(bad)


# ---------------------------------------------------------------------------
# Email handling (and its known limit)
# ---------------------------------------------------------------------------

class TestEmailHandling:

    def test_case_and_spaces_in_email_are_ignored(self):
        """The same mailbox written two ways counts as one author."""
        # Same mailbox written two ways -> one author with 2 commits
        commits = make_commits([
            ("Alice", "Alice@Uni.edu ", 5),
            ("Alice", "alice@uni.edu",  5),
        ])
        result = compute_baseline_shares(commits)
        assert len(result) == 1
        assert share_of(result, "alice@uni.edu", "commits") == 2

    def test_missing_email_is_kept_as_unknown(self):
        """A commit with no email is kept under '(unknown)', not dropped."""
        # A commit with no email must not vanish from the totals
        commits = make_commits([
            ("Alice", "alice@uni.edu", 5),
            ("Ghost", None,            5),
        ])
        result = compute_baseline_shares(commits)
        assert share_of(result, "(unknown)", "commits") == 1
        assert result["b1_share"].sum() == pytest.approx(1.0)

    def test_one_person_with_two_emails_is_split_in_two(self):
        """Known limit: one person with two emails shows up as two authors."""
        # KNOWN LIMIT: this test documents the weakness of grouping by
        # email. Alice used her university and her personal address, so
        # she shows up as two "authors", each with half her real share.
        # Fixing this is the job of identity mapping (backend Identity
        # module), not of this function.
        commits = make_commits([
            ("Alice", "alice@uni.edu",      10),
            ("Alice", "alice.home@mail.com", 10),
            ("Bob",   "bob@uni.edu",         20),
        ])
        result = compute_baseline_shares(commits)
        assert len(result) == 3
        assert share_of(result, "alice@uni.edu", "b1_share") == pytest.approx(1 / 3)
        assert share_of(result, "alice.home@mail.com", "b1_share") == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# No filtering yet
# ---------------------------------------------------------------------------

class TestNoFiltering:

    def test_merge_commits_still_count(self):
        """Merge commits are not filtered out at this stage."""
        # Milestone 6 counts everything. Dropping merges, bots and
        # whitespace-only commits is the hygiene filter's job (later).
        commits = pd.DataFrame({
            "author_name":  ["Alice", "Alice"],
            "author_email": ["alice@uni.edu", "alice@uni.edu"],
            "insertions":   [10, 0],
            "is_merge":     [False, True],
        })
        result = compute_baseline_shares(commits)
        assert share_of(result, "alice@uni.edu", "commits") == 2