# lite.py
# FairShare - Milestone 14
# FairShare-Lite: the Tier 1 score. No learning, just rules anyone can check.
#
# Every commit that counts as real work earns "points":
#
#   code points = surviving code lines x (1 + 5 x complexity per line)
#   test points = surviving test lines x 0.5
#   doc points  = surviving doc lines  x 0.25
#
# "Surviving" means the line is still in the final code (see features.py), so
# work that is later deleted or overwritten earns nothing, and so does a
# whitespace-only edit. A member's share is their points divided by the
# team's points. Each facet is the member's share of the team's points in
# that facet. Review and coordination need GitHub review and issue data,
# which Tier 1 does not receive yet, so they stay 0.0.
#
# The four numbers below are starting values to calibrate with the team.

import pandas as pd

MODEL_VERSION = "lite-0.1"

COMPLEXITY_WEIGHT = 5.0        # one complexity point per line counts as 5x extra
MAX_COMPLEXITY_DENSITY = 0.3   # cap, so one-line "if" commits cannot be farmed
TEST_WEIGHT = 0.5              # a surviving test line is worth half a code line
DOC_WEIGHT = 0.25              # a surviving doc line is worth a quarter


def commit_points(features: pd.DataFrame) -> pd.DataFrame:
    """
    Add points to the feature table (one row per commit).

    New columns: code_points, test_points, doc_points, points (their sum).
    Only commits flagged 'substantive' earn points; merges, bots, empty and
    generated-only commits get 0. The input table is not modified.
    """
    code_lines = features["code_lines"].astype(float)
    complexity = features["complexity_delta"].astype(float).clip(lower=0)

    # Complexity added per line of code, capped; 0 when no code lines were added.
    density = (complexity / code_lines.where(code_lines > 0)).fillna(0.0)
    density = density.clip(upper=MAX_COMPLEXITY_DENSITY)

    code = features["surviving_code"].astype(float) * (1 + COMPLEXITY_WEIGHT * density)
    test = features["surviving_test"].astype(float) * TEST_WEIGHT
    doc = features["surviving_doc"].astype(float) * DOC_WEIGHT

    counts = features["flag"] == "substantive"
    out = features.assign(
        code_points=code.where(counts, 0.0),
        test_points=test.where(counts, 0.0),
        doc_points=doc.where(counts, 0.0),
    )
    out["points"] = out["code_points"] + out["test_points"] + out["doc_points"]
    return out


def _share(values: pd.Series) -> pd.Series:
    """Each value divided by the total; all 0.0 if the total is 0."""
    total = values.sum()
    return values / total if total > 0 else values * 0.0


def score_members(points: pd.DataFrame) -> pd.DataFrame:
    """
    Turn each member's points into shares.

    Input : one row per member (index = member_id) with the columns
            code_points, test_points and doc_points.
    Output: the same rows with share, code, review, testing, docs and
            coordination. 'share' is the member's part of all points; each
            facet is their part of that facet's points. review and
            coordination are always 0.0 in Tier 1.
    """
    scores = pd.DataFrame(index=points.index)
    scores["share"] = _share(points[["code_points", "test_points", "doc_points"]].sum(axis=1))
    scores["code"] = _share(points["code_points"])
    scores["review"] = 0.0
    scores["testing"] = _share(points["test_points"])
    scores["docs"] = _share(points["doc_points"])
    scores["coordination"] = 0.0
    return scores


def _count(n: int, word: str) -> str:
    """'1 code line', '3 code lines'."""
    return f"{int(n)} {word}" + ("" if n == 1 else "s")


def evidence_reason(row: pd.Series) -> str:
    """
    A plain-language reason for one commit, built only from its numbers.

    Example: 'Added 12 code lines (complexity +4), 3 test lines; 83% of
    added lines survive'.
    """
    parts = []
    if row["code_lines"] > 0:
        parts.append(f"{_count(row['code_lines'], 'code line')} (complexity {int(row['complexity_delta']):+d})")
    if row["test_lines"] > 0:
        parts.append(_count(row["test_lines"], "test line"))
    if row["doc_lines"] > 0:
        parts.append(_count(row["doc_lines"], "doc line"))
    percent = int(row["survival"] * 100 + 0.5)
    return f"Added {', '.join(parts)}; {percent}% of added lines survive"