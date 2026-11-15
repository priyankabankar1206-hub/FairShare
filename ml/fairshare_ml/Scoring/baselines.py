from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

REQUIRED_COLUMNS = {"author_name", "author_email", "insertions", "files_changed"}

MAX_AUTHORS = 8

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


def compute_baseline_shares(commits: pd.DataFrame) -> pd.DataFrame:
    """
    Compute B1 and B2 shares per author.

    Input : the commits DataFrame from read_commits.py. It needs the columns
            'author_name', 'author_email', 'insertions' and 'files_changed'.
            Emails are compared ignoring case and spaces; a missing email
            becomes '(unknown)' so those commits are not dropped.
    Output: one row per author, sorted by email so the order is stable
            (columns are listed in OUTPUT_COLUMNS). An empty input gives an
            empty table. The input DataFrame is never modified.
    """
    _require_columns(commits, REQUIRED_COLUMNS, "commits table")

    per_author = (
        commits.assign(author_email=commits["author_email"].fillna("(unknown)").str.strip().str.lower())
        .groupby("author_email")
        .agg(
            author_name=("author_name", "first"),
            commits=("insertions", "size"),
            lines_added=("insertions", "sum"),
            files_touched=("files_changed", "sum")
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
    for bars in ax.containers:
        ax.bar_label(bars, fmt="%.1f%%", padding=2, fontsize=8)
    ax.margins(y=0.2)
    ax.legend(loc="upper center", ncol=2)
    plt.setp(ax.get_xticklabels(), ha="right")

    out = Path(output_path)
    ax.figure.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(ax.figure)
    return out