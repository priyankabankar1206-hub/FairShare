# baselines.py
# FairShare - Milestones 6 and 7
# Simple "baseline" contribution shares computed from the commits table.
#
#   B1 = each author's share of the total number of commits
#   B2 = each author's share of the total lines added
#   B4 = each author's share of the total files changed
#
# These are deliberately naive. They are the yardstick FairShare must beat.
# Nothing is filtered out here: merge commits, bots and whitespace-only
# commits all count. Cleaning comes later (the "hygiene filter" step).

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# Columns the commits table must have (read_commits.py writes all of them).
REQUIRED_COLUMNS = {"author_name", "author_email", "insertions", "files_changed"}

# The chart shows at most this many authors; everyone else becomes "Others".
MAX_AUTHORS = 8

# Column order of the table compute_baseline_shares() returns.
OUTPUT_COLUMNS = [
    "author_email",
    "author_name",
    "commits",
    "lines_added",
    "files_touched",
    "b1_share",
    "b2_share",
    "b4_share",
]


def _require_columns(table: pd.DataFrame, required: set[str], name: str) -> None:
    """Raise a clear error if `table` is missing any of the `required` columns."""
    missing = required - set(table.columns)
    if missing:
        raise ValueError(
            f"{name} is missing column(s): {sorted(missing)}. "
            f"Found: {list(table.columns)}"
        )


def _to_shares(counts: pd.Series) -> pd.Series:
    """
    Turn raw counts into shares that add up to 1.0.

    Example: counts [3, 1] -> shares [0.75, 0.25].

    If the total is zero (for example, nobody added a single line), dividing
    would give NaN. In that case every share is 0.0 instead, so the shares
    add up to 0.0, which honestly says "no data".
    """
    total = counts.sum()
    if total == 0:
        return pd.Series(0.0, index=counts.index)
    return counts / total


def _clean_email(emails: pd.Series) -> pd.Series:
    """
    Make emails comparable: fill gaps, strip spaces, lower-case.

    'Alice@Uni.edu ' and 'alice@uni.edu' are the same mailbox, so they count
    as one author. A missing email becomes '(unknown)' so those commits are
    not silently dropped by groupby.
    """
    return emails.fillna("(unknown)").str.strip().str.lower()


def compute_baseline_shares(commits: pd.DataFrame) -> pd.DataFrame:
    """
    Compute B1 and B2 shares per author.

    Input : the commits DataFrame from read_commits.py. It needs the columns
            'author_name', 'author_email', 'insertions' and 'files_changed'.
    Output: one row per author, sorted by email so the order is stable
            (columns are listed in OUTPUT_COLUMNS). An empty input gives an
            empty table. The input DataFrame is never modified.
    """
    _require_columns(commits, REQUIRED_COLUMNS, "commits table")

    # assign() builds a new table, so the caller's table stays untouched.
    per_author = (
        commits.assign(author_email=_clean_email(commits["author_email"]))
        .groupby("author_email")
        .agg(
            author_name=("author_name", "first"),   # first name seen
            commits=("insertions", "size"),         # rows = commits
            lines_added=("insertions", "sum"),      # total lines added
            files_touched=("files_changed", "sum")   # total files changed
        )
        .reset_index()
    )

    per_author["b1_share"] = _to_shares(per_author["commits"])
    per_author["b2_share"] = _to_shares(per_author["lines_added"])
    per_author["b4_share"] = _to_shares(per_author["files_touched"])
    return per_author


def group_small_authors(
    shares: pd.DataFrame, max_authors: int = MAX_AUTHORS
) -> pd.DataFrame:
    """
    Keep the top `max_authors` authors and merge everyone else into one
    "Others" row, so the chart stays readable.

    "Top" means the biggest B1 + B2 shares added together. The kept authors
    are then listed alphabetically by email (so the chart does not look like
    a ranking) and "Others" goes last. "Others" holds the summed shares, so
    each share column still adds up to the same total.

    With `max_authors` or fewer authors, the table is returned unchanged.
    """
    if len(shares) <= max_authors:
        return shares.copy()

    # Rank 1 = biggest combined share; ties go to whoever comes first.
    score = shares["b1_share"] + shares["b2_share"]
    is_top = score.rank(method="first", ascending=False) <= max_authors

    top = shares[is_top].sort_values("author_email")
    rest = shares[~is_top]

    others = pd.DataFrame([{
        "author_email": "(others)",
        "author_name":  f"Others ({len(rest)})",
        "commits":      rest["commits"].sum(),
        "lines_added":  rest["lines_added"].sum(),
        "files_touched": rest["files_touched"].sum(),
        "b1_share":     rest["b1_share"].sum(),
        "b2_share":     rest["b2_share"].sum(),
        "b4_share":     rest["b4_share"].sum(),
    }])

    # ignore_index gives a fresh 0..n index (otherwise two rows could share one).
    return pd.concat([top, others], ignore_index=True)


def plot_baseline_shares(
    shares: pd.DataFrame, output_path: str = "baselines.png"
) -> Path:
    """
    Draw one grouped bar chart and save it as a PNG.

    One group per author, two bars each: B1 (share of commits) and
    B2 (share of lines added), with the percentage written on every bar.
    More than MAX_AUTHORS authors are reduced to the top ones plus "Others".

    `shares` is the table returned by compute_baseline_shares().
    Returns the path of the saved file. Never opens a window.
    """
    if shares.empty:
        raise ValueError("Nothing to plot: the shares table is empty.")
    _require_columns(shares, set(OUTPUT_COLUMNS), "shares table")

    data = group_small_authors(shares)

    # One row per author (labelled by name, or email if the name is missing),
    # one column per baseline, in percent. pandas draws these as grouped bars.
    chart = (
        data.set_index(data["author_name"].fillna(data["author_email"]))
        [["b1_share", "b2_share"]]
        .mul(100)
        .rename(columns={
            "b1_share": "B1: share of commits",
            "b2_share": "B2: share of lines added",
        })
    )

    ax = chart.plot.bar(
        figsize=(max(6, 1.3 * len(chart) + 2), 5),
        width=0.8,
        rot=30,
        title="Baseline contribution shares per author",
        xlabel="Author",
        ylabel="Share of team total (%)",
    )
    for bars in ax.containers:                       # one container per baseline
        ax.bar_label(bars, fmt="%.1f%%", padding=2, fontsize=8)
    ax.margins(y=0.2)                                # head-room for labels + legend
    ax.legend(loc="upper center", ncol=2)            # fixed spot, never over a bar
    plt.setp(ax.get_xticklabels(), ha="right")       # tilted names end at their bar

    out = Path(output_path)
    ax.figure.savefig(out, dpi=150, bbox_inches="tight")   # file only, no window
    plt.close(ax.figure)                                   # free the memory
    return out