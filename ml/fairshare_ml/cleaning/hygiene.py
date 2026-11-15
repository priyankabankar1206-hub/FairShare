import re

import pandas as pd

GENERATED_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "pipfile.lock", "cargo.lock", "composer.lock", "gemfile.lock",
    "go.sum", "pubspec.lock",
}

GENERATED_DIRS = {
    "node_modules", "dist", "build", "vendor", "target", "out",
    "__pycache__", ".venv", ".dart_tool", "pods", ".gradle",
}

GENERATED_SUFFIXES = (
    ".min.js", ".min.css", ".map", ".pyc", ".class", ".o", ".dll", ".exe",
    ".g.dart", ".freezed.dart",
)

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


def flag_commits(
    commits: pd.DataFrame,
    file_changes: pd.DataFrame,
    whitespace_only: frozenset = frozenset(),
) -> pd.DataFrame:
    """
    Add hygiene columns to the commits table (one row in, one row out).

    Input : commits (commits.csv) and file_changes (file_changes.csv), plus
            optionally the hashes of whitespace-only commits (these get 'no_op').
    Output: the commits table plus
              clean_insertions - lines added, generated files left out
              clean_deletions  - lines deleted, generated files left out
              clean_files      - files changed, generated files left out
              flag             - merge, bot, empty, generated, no_op or substantive
    The input tables are not modified.
    """
    files = flag_file_changes(file_changes)

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
        if row["hash"] in whitespace_only:
            return "no_op"
        return "substantive"

    out["flag"] = out.apply(flag_for, axis=1) if len(out) else pd.Series(dtype=str)
    return out.drop(columns="total_files")