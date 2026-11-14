# features.py
# FairShare - Milestone 13
# Describe each commit with numbers Lite can score:
#   code_lines / test_lines / doc_lines   lines added, by kind of file
#   complexity_delta                      change in cyclomatic complexity (code)
#   surviving_code / _test / _doc         lines still in the final code
#   survival                              surviving lines / lines added (0 to 1)
# Generated files are left out everywhere (see hygiene.py).

import re
import subprocess
from collections import Counter
from pathlib import Path

import pandas as pd
from pydriller import Repository

from fairshare_ml.cleaning.hygiene import flag_commits, is_generated_path
from fairshare_ml.cleaning.read_commits import (
    FILE_CHANGE_COLUMNS,
    read_commits,
    read_file_changes,
    validate_repo_path,
)

KINDS = ("code", "test", "doc")

FEATURE_COLUMNS = [
    "hash", "author_email", "flag",
    "code_lines", "test_lines", "doc_lines",
    "complexity_delta",
    "surviving_code", "surviving_test", "surviving_doc",
    "survival",
]

DOC_SUFFIXES = (".md", ".rst", ".adoc")
DOC_FOLDERS = {"docs", "doc"}
TEST_FOLDERS = {"test", "tests", "__tests__", "spec", "specs"}
TEST_ENDINGS = (
    "_test.py", ".test.js", ".test.ts", ".test.jsx", ".test.tsx",
    ".spec.js", ".spec.ts", "_test.dart", "_test.go",
)

# One header line like "<40-hex commit> <line> <line>" starts each blamed line.
_BLAME_HEADER = re.compile(r"^([0-9a-f]{40}) \d+ \d+", re.MULTILINE)


# ---------------------------------------------------------------------------
# What kind of file is it? (decided from the path alone)
# ---------------------------------------------------------------------------

def is_doc_path(path: str) -> bool:
    """True for Markdown/reStructuredText/AsciiDoc files and anything in docs/."""
    parts = path.lower().replace("\\", "/").split("/")
    return parts[-1].endswith(DOC_SUFFIXES) or any(p in DOC_FOLDERS for p in parts[:-1])


def is_test_path(path: str) -> bool:
    """True for files in a tests folder or named like a test (test_x.py, x.spec.ts, XTest.java)."""
    parts = path.replace("\\", "/").split("/")
    name, folders = parts[-1], [p.lower() for p in parts[:-1]]
    return (
        any(f in TEST_FOLDERS for f in folders)
        or name.lower().startswith("test_")
        or name.lower().endswith(TEST_ENDINGS)
        or name.endswith(("Test.java", "Tests.java"))   # capital T: 'Latest.java' is not a test
    )


def file_kind(path: str) -> str:
    """'generated', 'doc', 'test' or 'code' (checked in that order)."""
    if is_generated_path(path):
        return "generated"
    if is_doc_path(path):
        return "doc"
    if is_test_path(path):
        return "test"
    return "code"


# ---------------------------------------------------------------------------
# Reading the repository
# ---------------------------------------------------------------------------

def read_complexity(repo_path: str) -> list[dict]:
    """
    One row per changed file: how much the file's cyclomatic complexity
    changed in that commit (keys: hash, path, complexity_delta).

    Complexity is the sum over all functions in the file, after the commit
    minus before it, measured by Lizard (through PyDriller) for the languages
    it understands, such as Python, Java and JavaScript/TypeScript. Other
    files give 0. Removing code gives a negative number.
    """
    validate_repo_path(repo_path)

    rows: list[dict] = []
    for commit in Repository(repo_path).traverse_commits():
        for changed in commit.modified_files:
            after = sum(m.complexity for m in changed.methods)
            before = sum(m.complexity for m in changed.methods_before)
            rows.append({
                "hash": commit.hash,
                "path": Path(changed.new_path or changed.old_path).as_posix(),
                "complexity_delta": after - before,
            })
    return rows


def _text_files(repo_path: str) -> list[str]:
    """Tracked files that are text. Binary files are skipped: blame would count fake lines."""
    out = subprocess.run(
        ["git", "-C", repo_path, "ls-files", "--eol", "-z"],
        capture_output=True, check=True,
    )
    files = []
    for record in out.stdout.decode("utf-8", "replace").split("\0"):
        info, _, path = record.partition("\t")
        if path and not info.startswith("i/-text"):
            files.append(path)
    return files


def read_survival(repo_path: str) -> pd.DataFrame:
    """
    Which commit wrote each line that is still in the final code (HEAD).

    Returns one row per (commit, kind of file) with 'surviving_lines'
    (columns: hash, kind, surviving_lines). Generated and binary files are
    skipped. Blame ignores whitespace changes (-w), so re-indenting a line
    does not move it to a new owner.
    """
    validate_repo_path(repo_path)

    counts: Counter = Counter()
    for path in _text_files(repo_path):
        if is_generated_path(path):
            continue
        blame = subprocess.run(
            ["git", "-C", repo_path, "blame", "-w", "--line-porcelain", "HEAD", "--", path],
            capture_output=True,
        )
        if blame.returncode != 0:       # e.g. a file that is not in HEAD yet
            continue
        kind = file_kind(path)
        for sha in _BLAME_HEADER.findall(blame.stdout.decode("utf-8", "replace")):
            counts[(sha, kind)] += 1

    rows = [{"hash": h, "kind": k, "surviving_lines": n} for (h, k), n in counts.items()]
    return pd.DataFrame(rows, columns=["hash", "kind", "surviving_lines"])


# ---------------------------------------------------------------------------
# Putting the numbers together
# ---------------------------------------------------------------------------

def _sum_by_kind(rows: pd.DataFrame, value: str) -> pd.DataFrame:
    """Sum `value` per commit and kind. Index = hash, one column per kind (0 if none)."""
    if rows.empty:
        return pd.DataFrame(columns=list(KINDS), dtype=int)
    summed = rows.groupby(["hash", "kind"])[value].sum()
    return summed.unstack(fill_value=0).reindex(columns=list(KINDS), fill_value=0)


def build_features(
    flagged: pd.DataFrame,
    file_changes: pd.DataFrame,
    complexity: pd.DataFrame,
    survival: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join everything into one row per commit (columns: FEATURE_COLUMNS).

    flagged      - output of flag_commits() (needs hash, author_email, flag)
    file_changes - file_changes.csv rows
    complexity   - read_complexity() rows as a table
    survival     - read_survival() table

    Only code files count towards complexity_delta. 'survival' is surviving
    lines divided by lines added (0.0 when nothing was added, never above 1.0).
    The input tables are not modified.
    """
    added = _sum_by_kind(
        file_changes.assign(kind=file_changes["path"].map(file_kind)), "lines_added"
    )
    added.columns = [f"{k}_lines" for k in KINDS]

    kept = _sum_by_kind(survival, "surviving_lines")
    kept.columns = [f"surviving_{k}" for k in KINDS]

    code_complexity = (
        complexity[complexity["path"].map(file_kind) == "code"]
        .groupby("hash")["complexity_delta"].sum()
    )

    out = (
        flagged[["hash", "author_email", "flag"]]
        .join(added, on="hash")
        .join(code_complexity, on="hash")
        .join(kept, on="hash")
    )
    numbers = [c for c in FEATURE_COLUMNS if c not in ("hash", "author_email", "flag", "survival")]
    out[numbers] = out[numbers].astype(float).fillna(0).astype(int)

    lines_added = out[[f"{k}_lines" for k in KINDS]].sum(axis=1)
    lines_kept = out[[f"surviving_{k}" for k in KINDS]].sum(axis=1)
    out["survival"] = (lines_kept / lines_added.where(lines_added > 0)).fillna(0.0).clip(upper=1.0)
    return out


def extract_features(repo_path: str) -> pd.DataFrame:
    """
    Read a repository and return one row of features per commit, oldest first
    (columns: FEATURE_COLUMNS). A repository with no commits gives an empty table.
    """
    commits = read_commits(repo_path)
    if not commits:
        return pd.DataFrame(columns=FEATURE_COLUMNS)

    file_changes = pd.DataFrame(read_file_changes(repo_path), columns=FILE_CHANGE_COLUMNS)
    flagged = flag_commits(pd.DataFrame(commits), file_changes)
    complexity = pd.DataFrame(
        read_complexity(repo_path), columns=["hash", "path", "complexity_delta"]
    )
    return build_features(flagged, file_changes, complexity, read_survival(repo_path))