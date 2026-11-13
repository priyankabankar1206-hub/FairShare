# hygiene.py
# FairShare - Milestone 11
# Hygiene filter v1: flag commits that are not real work, so scoring can
# ignore them. Nothing is deleted - every commit keeps a flag.
#
# Flags (first match wins):
#   merge       - a merge commit
#   bot         - written by an automated account (dependabot, ...)
#   empty       - changes no files at all
#   generated   - every changed file is generated or vendored
#   substantive - everything else: counts as real work
#
# Mixed commits (real code plus a lock file) stay "substantive", but the
# generated files are left out of the clean_* line and file counts.

import re

import pandas as pd

# Exact file names that are always generated (lock files).
GENERATED_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "pipfile.lock", "cargo.lock", "composer.lock", "gemfile.lock",
    "go.sum", "pubspec.lock",
}

# A file inside any of these folders is generated or vendored.
GENERATED_DIRS = {
    "node_modules", "dist", "build", "vendor", "target", "out",
    "__pycache__", ".venv", ".dart_tool", "pods", ".gradle",
}

# File endings that mark generated or compiled output.
GENERATED_SUFFIXES = (
    ".min.js", ".min.css", ".map", ".pyc", ".class", ".o", ".dll", ".exe",
    ".g.dart", ".freezed.dart",
)

# Bot accounts: GitHub's "[bot]" tag, a name ending in "bot" as its own word,
# or a few well-known bot names.
_BOT_PATTERN = re.compile(
    r"\[bot\]|\bbot$|^(dependabot|renovate|github-actions|pre-commit-ci)"
)


def is_bot(author_name: str, author_email: str) -> bool:
    """True if the author name or email looks like an automated account."""
    return any(
        _BOT_PATTERN.search(str(text).strip().lower())
        for text in (author_name, author_email)
    )


def is_generated_path(path: str) -> bool:
    """
    True if a file path points to a generated or vendored file.

    Examples: 'package-lock.json', 'node_modules/x/index.js', 'app.min.js'.
    Matching ignores upper/lower case and accepts '/' or '\\' separators.
    Real files like 'build.gradle' or 'src/build_tools.py' do not match.
    """
    parts = path.lower().replace("\\", "/").split("/")
    filename, folders = parts[-1], parts[:-1]
    return (
        filename in GENERATED_FILES
        or any(folder in GENERATED_DIRS for folder in folders)
        or filename.endswith(GENERATED_SUFFIXES)
    )


def flag_file_changes(file_changes: pd.DataFrame) -> pd.DataFrame:
    """
    Return a copy of the file_changes table with an extra True/False column,
    'is_generated'. The input table is not modified.
    """
    is_generated = file_changes["path"].map(is_generated_path).astype(bool)
    return file_changes.assign(is_generated=is_generated)


def flag_commits(commits: pd.DataFrame, file_changes: pd.DataFrame) -> pd.DataFrame:
    """
    Add hygiene columns to the commits table (one row in, one row out).

    Input : commits (commits.csv) and file_changes (file_changes.csv).
    Output: the commits table plus
              clean_insertions - lines added, generated files left out
              clean_deletions  - lines deleted, generated files left out
              clean_files      - files changed, generated files left out
              flag             - merge, bot, empty, generated or substantive
    The input tables are not modified.
    """
    files = flag_file_changes(file_changes)

    # Totals per commit, counting only files that are NOT generated.
    clean = (
        files[~files["is_generated"]]
        .groupby("hash")
        .agg(
            clean_insertions=("lines_added", "sum"),
            clean_deletions=("lines_deleted", "sum"),
            clean_files=("path", "size"),
        )
    )
    total_files = files.groupby("hash").size().rename("total_files")

    # Commits with no matching rows get 0 (no files, or only generated ones).
    out = commits.join(clean, on="hash").join(total_files, on="hash")
    counts = ["clean_insertions", "clean_deletions", "clean_files", "total_files"]
    out[counts] = out[counts].astype(float).fillna(0).astype(int)

    def flag_for(row: pd.Series) -> str:
        """Pick the flag for one commit (the first rule that matches)."""
        if row["is_merge"]:
            return "merge"
        if is_bot(row["author_name"], row["author_email"]):
            return "bot"
        if row["total_files"] == 0:
            return "empty"
        if row["clean_files"] == 0:
            return "generated"
        return "substantive"

    # apply() on an empty table would not return a column, so skip it then.
    out["flag"] = out.apply(flag_for, axis=1) if len(out) else pd.Series(dtype=str)
    return out.drop(columns="total_files")