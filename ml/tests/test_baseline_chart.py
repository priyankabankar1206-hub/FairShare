# tests/test_baselines_chart.py
# FairShare - Milestone 7
# Tests for the chart code in baselines.py.
#
# Run:  pytest tests/test_baselines_chart.py -v

import matplotlib

matplotlib.use("Agg")   # draw into files only, never open a window

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from baselines import (
    MAX_AUTHORS,
    compute_baseline_shares,
    group_small_authors,
    plot_baseline_shares,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"   # the first 8 bytes of every PNG file


def make_shares(n_authors: int) -> pd.DataFrame:
    """
    Build a shares table for n authors. Author i makes i commits of
    10 lines each, so bigger numbers mean bigger shares.
    """
    rows = []
    for i in range(1, n_authors + 1):
        rows += [(f"Person {i:02d}", f"p{i:02d}@uni.edu", 10)] * i
    commits = pd.DataFrame(rows, columns=["author_name", "author_email", "insertions"])
    return compute_baseline_shares(commits)


# ---------------------------------------------------------------------------
# Grouping into "Others"
# ---------------------------------------------------------------------------

class TestGrouping:

    def test_eight_or_fewer_authors_are_unchanged(self):
        """Up to MAX_AUTHORS authors need no grouping."""
        shares = make_shares(MAX_AUTHORS)
        grouped = group_small_authors(shares)
        pd.testing.assert_frame_equal(grouped, shares)

    def test_more_than_eight_gives_eight_plus_others(self):
        """Nine or more authors become the top eight plus one 'Others' row, listed last."""
        grouped = group_small_authors(make_shares(12))
        assert len(grouped) == MAX_AUTHORS + 1
        assert grouped["author_email"].iloc[-1] == "(others)"   # Others is last

    def test_keeps_the_biggest_authors(self):
        """The biggest contributors are kept; the smallest go into 'Others'."""
        # Person 12 has the most commits, Person 01 the fewest
        grouped = group_small_authors(make_shares(12))
        kept = set(grouped["author_email"])
        assert "p12@uni.edu" in kept
        assert "p01@uni.edu" not in kept

    def test_others_holds_the_summed_shares(self):
        """The 'Others' row holds the summed commits and shares of the merged authors."""
        shares = make_shares(12)
        grouped = group_small_authors(shares)
        others = grouped.iloc[-1]
        # Persons 01-04 are merged: 1+2+3+4 = 10 commits out of 78
        assert others["commits"] == 10
        assert others["b1_share"] == pytest.approx(10 / 78)
        assert others["author_name"] == "Others (4)"

    def test_share_columns_still_sum_to_one(self):
        """Grouping does not change the total of either share column."""
        grouped = group_small_authors(make_shares(12))
        assert grouped["b1_share"].sum() == pytest.approx(1.0)
        assert grouped["b2_share"].sum() == pytest.approx(1.0)

    def test_kept_authors_are_alphabetical_not_ranked(self):
        """Kept authors are listed alphabetically so the chart does not read as a ranking."""
        grouped = group_small_authors(make_shares(12))
        kept_emails = list(grouped["author_email"].iloc[:-1])   # without Others
        assert kept_emails == sorted(kept_emails)

    def test_input_table_is_not_modified(self):
        """The caller's DataFrame is left untouched."""
        shares = make_shares(12)
        before = shares.copy()
        group_small_authors(shares)
        pd.testing.assert_frame_equal(shares, before)


# ---------------------------------------------------------------------------
# Saving the chart
# ---------------------------------------------------------------------------

class TestPlot:

    def test_saves_a_real_png_file(self, tmp_path):
        """The function saves a valid PNG file and returns its path."""
        out = tmp_path / "baselines.png"
        returned = plot_baseline_shares(make_shares(3), str(out))
        assert returned == out
        assert out.exists()
        assert out.read_bytes()[:8] == PNG_SIGNATURE

    def test_works_with_more_than_eight_authors(self, tmp_path):
        """A chart with an 'Others' group is saved without errors."""
        out = tmp_path / "many.png"
        plot_baseline_shares(make_shares(12), str(out))
        assert out.stat().st_size > 0

    def test_works_with_a_single_author(self, tmp_path):
        """A one-author chart is saved without errors."""
        out = tmp_path / "one.png"
        plot_baseline_shares(make_shares(1), str(out))
        assert out.exists()

    def test_works_when_all_shares_are_zero(self, tmp_path):
        """An all-zero B2 column still produces a chart."""
        # Nobody added lines: B2 is all zeros. The chart must still draw.
        commits = pd.DataFrame({
            "author_name": ["Alice", "Bob"],
            "author_email": ["a@uni.edu", "b@uni.edu"],
            "insertions": [0, 0],
        })
        out = tmp_path / "zero.png"
        plot_baseline_shares(compute_baseline_shares(commits), str(out))
        assert out.exists()

    def test_never_calls_show_and_closes_the_figure(self, tmp_path, monkeypatch):
        """plt.show() is never called and no figure is left open in memory."""
        def fail_if_called(*args, **kwargs):
            """Stand-in for plt.show() that fails the test if it is ever called."""
            pytest.fail("plt.show() must not be called")

        monkeypatch.setattr(plt, "show", fail_if_called)
        plot_baseline_shares(make_shares(3), str(tmp_path / "x.png"))
        assert plt.get_fignums() == []   # no figure left open in memory

    def test_empty_table_raises(self, tmp_path):
        """An empty shares table gives a clear ValueError."""
        empty = compute_baseline_shares(
            pd.DataFrame(columns=["author_name", "author_email", "insertions"])
        )
        with pytest.raises(ValueError, match="empty"):
            plot_baseline_shares(empty, str(tmp_path / "e.png"))

    def test_missing_column_raises(self, tmp_path):
        """A shares table with a missing column gives a clear ValueError."""
        bad = make_shares(3).drop(columns=["b2_share"])
        with pytest.raises(ValueError, match="b2_share"):
            plot_baseline_shares(bad, str(tmp_path / "b.png"))