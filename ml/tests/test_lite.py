import pandas as pd
import pytest

from fairshare_ml.cleaning.features import FEATURE_COLUMNS
from fairshare_ml.scoring.lite import (
    COMPLEXITY_WEIGHT,
    MAX_COMPLEXITY_DENSITY,
    TEST_WEIGHT,
    commit_points,
    evidence_reason,
    score_members,
)


def make_features(rows: list[dict]) -> pd.DataFrame:
    """Build a feature table; any column a row leaves out is 0 (flag: 'substantive')."""
    defaults = {"hash": "h", "author_email": "a@x.com", "flag": "substantive",
                "code_lines": 0, "test_lines": 0, "doc_lines": 0,
                "complexity_delta": 0, "surviving_code": 0, "surviving_test": 0,
                "surviving_doc": 0, "survival": 0.0}
    return pd.DataFrame([{**defaults, **row} for row in rows], columns=FEATURE_COLUMNS)


def points_of(row: dict, column: str = "points") -> float:
    """Score one commit and return one of its point columns."""
    return float(commit_points(make_features([row]))[column].iloc[0])


class TestCommitPoints:
    """commit_points() turns surviving lines and complexity into points."""

    def test_plain_code_earns_one_point_per_surviving_line(self):
        """No complexity added: 10 surviving lines = 10 points."""
        assert points_of({"code_lines": 10, "surviving_code": 10}) == 10.0

    def test_complexity_raises_the_value_of_surviving_code(self):
        """2 complexity over 10 lines = 0.2 per line, so each line counts 1 + 5 x 0.2 = 2."""
        row = {"code_lines": 10, "surviving_code": 10, "complexity_delta": 2}
        assert points_of(row, "code_points") == pytest.approx(20.0)

    def test_only_surviving_lines_earn_points(self):
        """Half the lines survive: half the points."""
        row = {"code_lines": 10, "surviving_code": 5, "complexity_delta": 2}
        assert points_of(row, "code_points") == pytest.approx(5 * 2.0)

    def test_complexity_bonus_is_capped(self):
        """A one-line commit with +1 complexity is capped at 1 + 5 x 0.3 = 2.5, not 6."""
        row = {"code_lines": 1, "surviving_code": 1, "complexity_delta": 1}
        assert points_of(row, "code_points") == pytest.approx(
            1 + COMPLEXITY_WEIGHT * MAX_COMPLEXITY_DENSITY
        )

    def test_removing_complexity_gives_no_bonus_and_no_penalty(self):
        """A negative complexity change counts as 0, so lines earn exactly 1 point each."""
        row = {"code_lines": 10, "surviving_code": 10, "complexity_delta": -4}
        assert points_of(row, "code_points") == 10.0

    def test_test_and_doc_lines_are_worth_less(self):
        """4 test lines = 2.0 points, 4 doc lines = 1.0 point."""
        row = {"surviving_test": 4, "surviving_doc": 4}
        assert points_of(row, "test_points") == pytest.approx(4 * TEST_WEIGHT)
        assert points_of(row, "doc_points") == pytest.approx(1.0)

    def test_points_add_up(self):
        """points = code + test + doc points."""
        row = {"code_lines": 10, "surviving_code": 10, "surviving_test": 4, "surviving_doc": 4}
        assert points_of(row) == pytest.approx(10 + 2 + 1)

    @pytest.mark.parametrize("flag", ["merge", "bot", "empty", "generated"])
    def test_flagged_commits_earn_nothing(self, flag):
        """Only 'substantive' commits earn points, even if lines survive."""
        row = {"flag": flag, "code_lines": 10, "surviving_code": 10, "surviving_test": 5}
        assert points_of(row) == 0.0

    def test_no_code_lines_does_not_divide_by_zero(self):
        """A test-only commit (0 code lines) still scores, with no NaN."""
        result = commit_points(make_features([{"test_lines": 6, "surviving_test": 6}]))
        assert result["points"].iloc[0] == pytest.approx(3.0)
        assert not result[["code_points", "points"]].isna().any().any()

    def test_empty_table_works(self):
        """No commits in, no commits out."""
        result = commit_points(pd.DataFrame(columns=FEATURE_COLUMNS))
        assert result.empty
        assert "points" in result.columns

    def test_input_is_not_modified(self):
        """The caller's table is left untouched."""
        features = make_features([{"code_lines": 3, "surviving_code": 3}])
        before = features.copy()
        commit_points(features)
        pd.testing.assert_frame_equal(features, before)


def make_points(rows: dict) -> pd.DataFrame:
    """Build a member table from {member_id: (code, test, doc)} points."""
    return pd.DataFrame(
        rows, index=["code_points", "test_points", "doc_points"]
    ).T


class TestScoreMembers:
    """score_members() turns points into shares and facets."""

    def test_share_is_each_members_part_of_all_points(self):
        """m_1 has 8 points, m_2 has 2 + 4 = 6: shares 8/14 and 6/14."""
        scores = score_members(make_points({"m_1": (8, 0, 0), "m_2": (2, 4, 0)}))
        assert scores.loc["m_1", "share"] == pytest.approx(8 / 14)
        assert scores.loc["m_2", "share"] == pytest.approx(6 / 14)
        assert scores["share"].sum() == pytest.approx(1.0)

    def test_each_facet_is_a_share_of_that_facets_points(self):
        """Code 8:2, testing 0:4 (so m_2 has all of it)."""
        scores = score_members(make_points({"m_1": (8, 0, 0), "m_2": (2, 4, 0)}))
        assert scores["code"].tolist() == pytest.approx([0.8, 0.2])
        assert scores["testing"].tolist() == pytest.approx([0.0, 1.0])

    def test_a_facet_nobody_worked_on_is_zero_for_everyone(self):
        """Nobody wrote docs: the docs facet is 0.0 for all, not NaN."""
        scores = score_members(make_points({"m_1": (8, 0, 0), "m_2": (2, 4, 0)}))
        assert (scores["docs"] == 0.0).all()

    def test_review_and_coordination_are_zero_in_tier_1(self):
        """No review or issue data yet, so those facets are always 0.0."""
        scores = score_members(make_points({"m_1": (5, 5, 5)}))
        assert scores.loc["m_1", "review"] == 0.0
        assert scores.loc["m_1", "coordination"] == 0.0

    def test_all_zero_points_give_all_zero_shares(self):
        """Nobody earned anything: every value is 0.0, no NaN."""
        scores = score_members(make_points({"m_1": (0, 0, 0), "m_2": (0, 0, 0)}))
        assert (scores == 0.0).all().all()

    def test_a_single_member_gets_everything(self):
        """A team of one has share 1.0 and a code facet of 1.0."""
        scores = score_members(make_points({"m_1": (3, 0, 0)}))
        assert scores.loc["m_1", "share"] == 1.0
        assert scores.loc["m_1", "code"] == 1.0

    def test_columns(self):
        """The output has the six score columns, in order."""
        scores = score_members(make_points({"m_1": (1, 0, 0)}))
        assert list(scores.columns) == ["share", "code", "review", "testing", "docs", "coordination"]


class TestEvidenceReason:
    """evidence_reason() builds a sentence only from the commit's numbers."""

    def test_code_and_test_commit(self):
        """Both parts appear, with complexity written with its sign."""
        row = pd.Series({"code_lines": 12, "test_lines": 3, "doc_lines": 0,
                         "complexity_delta": 4, "survival": 0.83})
        assert evidence_reason(row) == (
            "Added 12 code lines (complexity +4), 3 test lines; 83% of added lines survive"
        )

    def test_singular_and_negative_complexity(self):
        """'1 code line' is singular, and a drop in complexity shows a minus."""
        row = pd.Series({"code_lines": 1, "test_lines": 0, "doc_lines": 0,
                         "complexity_delta": -2, "survival": 1.0})
        assert evidence_reason(row) == "Added 1 code line (complexity -2); 100% of added lines survive"

    def test_docs_only_commit(self):
        """A docs-only commit mentions no code and no complexity."""
        row = pd.Series({"code_lines": 0, "test_lines": 0, "doc_lines": 2,
                         "complexity_delta": 0, "survival": 0.5})
        assert evidence_reason(row) == "Added 2 doc lines; 50% of added lines survive"
