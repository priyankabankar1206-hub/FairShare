# read_commits.py
# FairShare – Milestone 3
# Reads every commit from a local git repo, saves to CSV, and prints a summary.

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
from pydriller import Repository
# Columns of data/file_changes.csv, in order (one row per changed file).
FILE_CHANGE_COLUMNS = [
    "hash",
    "path",
    "extension",
    "lines_added",
    "lines_deleted",
    "change_type",
]
# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_repo_path(repo_path: str) -> None:
    """
    Confirm that repo_path is a valid local git repository.

    Three checks are run in order:
      1. The path exists on disk.
      2. It is a directory (not a plain file).
      3. It contains a .git folder (the marker of a git repo).

    Returns nothing on success; raises a descriptive error otherwise so the
    caller always knows exactly what went wrong.
    """
    path = Path(repo_path)

    # Check 1 – does the path exist at all?
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {repo_path}")

    # Check 2 – is it a directory, not a file?
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {repo_path}")

    # Check 3 – every git repo has a .git sub-folder at its root
    if not (path / ".git").exists():
        raise ValueError(
            f"Not a git repository (no .git folder found): {repo_path}"
        )


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def read_commits(repo_path: str) -> list[dict]:
    """
    Walk every commit in the git repo at repo_path using PyDriller.

    Returns a list of dicts, oldest commit first.  Each dict has these keys:

      hash          – 40-character SHA that uniquely identifies the commit
      author_name   – display name of the person who wrote the code
      author_email  – their email address (stored internally, not displayed)
      author_date   – timezone-aware datetime of when they made the commit
      insertions    – lines of code added across all files in this commit
      deletions     – lines of code removed across all files in this commit
      files_changed – number of files touched in this commit
      is_merge      – True if this commit merges two or more branches
      message       – first line of the commit message (the "subject line")

    No commits are filtered out.  Merge commits are intentionally kept so
    the data is a faithful record of everything that happened in the repo.

    How PyDriller walks the repo
    ────────────────────────────
    PyDriller.Repository() opens the local .git database (no network needed).
    .traverse_commits() is a *generator*: it asks git for one commit at a
    time (oldest first, same order as `git log --reverse`), so only one
    Commit object lives in memory at once — important for large repos.
    For each commit it runs a `git diff` against the commit's parent(s) to
    count insertions, deletions, and the number of files changed.
    """
    # Always validate first so errors are caught before PyDriller starts
    validate_repo_path(repo_path)

    commits: list[dict] = []

    # Repository() wraps the local git repo; traverse_commits() is the generator
    for commit in Repository(repo_path).traverse_commits():

        # Take only the first line of the message (the subject).
        # Long commit messages have extra paragraphs after the first blank line;
        # we don't need those for scoring.
        subject: str = commit.msg.splitlines()[0].strip() if commit.msg else ""

        commits.append({
            "hash":          commit.hash,           # full 40-char hex SHA
            "author_name":   commit.author.name,
            "author_email":  commit.author.email,
            "author_date":   commit.author_date,    # timezone-aware datetime
            "insertions":    commit.insertions,     # summed over all files
            "deletions":     commit.deletions,      # summed over all files
            "files_changed": commit.files,          # len(modified_files)
            "is_merge":      commit.merge,          # True if >1 parent
            "message":       subject,
        })

    return commits

def read_file_changes(repo_path: str) -> list[dict]:
    """
    Walk every commit and return one row per changed file, oldest commit first.

    Each dict has these keys (see FILE_CHANGE_COLUMNS):

      hash          - the commit this change belongs to
      path          - the file's path inside the repo (the old path if the
                      file was deleted, the new path if it was renamed)
      extension     - lower-case ending such as '.py'; '' for names like
                      'Makefile' or '.gitignore'
      lines_added   - lines added to this file in this commit
      lines_deleted - lines removed from this file in this commit
      change_type   - ADD, MODIFY, DELETE or RENAME (PyDriller's names)

    Nothing is filtered out. Spotting generated files, bots and no-op
    changes is the hygiene filter's job.
    """
    validate_repo_path(repo_path)

    rows: list[dict] = []
    for commit in Repository(repo_path).traverse_commits():
        for changed in commit.modified_files:
            # A deleted file has no new path, so fall back to the old one.
            # Git paths always use '/', but PyDriller returns '\' on Windows.
            path = Path(changed.new_path or changed.old_path).as_posix()
            rows.append({
                "hash":          commit.hash,
                "path":          path,
                "extension":     Path(path).suffix.lower(),
                "lines_added":   changed.added_lines,
                "lines_deleted": changed.deleted_lines,
                "change_type":   changed.change_type.name,
            })

    return rows

# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------
def _changed_lines_per_commit(repo_path: str, diff_options: list[str]) -> dict[str, int]:
    """
    Total lines added + deleted by each non-merge commit, from `git log --numstat`.
    `diff_options` are extra git diff options (for example ["-w"]).
    A repository with no commits gives an empty dict.
    """
    result = subprocess.run(
        ["git", "-C", repo_path, "log", "--no-merges", "--numstat", "--format=%H", *diff_options],
        capture_output=True,
    )
    if result.returncode != 0:          # git fails on a repo without commits
        return {}

    totals: dict[str, int] = {}
    current = ""
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        if re.fullmatch(r"[0-9a-f]{40}", line):
            current = line
            totals[current] = 0
        elif "\t" in line:
            added, deleted, _ = line.split("\t", 2)
            # Binary files show '-' instead of numbers and count as 0.
            totals[current] += sum(int(n) for n in (added, deleted) if n.isdigit())
    return totals


def read_whitespace_only_commits(repo_path: str) -> set[str]:
    """
    Hashes of commits that change lines, but only whitespace.

    A commit qualifies when git sees changed lines normally, yet none once
    spaces, tabs, line endings and blank lines are ignored. Re-wrapping lines
    (what Black or Prettier often do) is not caught: that needs a syntax tree.
    """
    validate_repo_path(repo_path)
    plain = _changed_lines_per_commit(repo_path, [])
    ignoring_whitespace = _changed_lines_per_commit(repo_path, ["-w", "--ignore-blank-lines"])
    return {
        sha for sha, total in plain.items()
        if total > 0 and ignoring_whitespace.get(sha, 0) == 0
    }

def main() -> None:
    """
    Usage:  python read_commits.py <path-to-git-repo>

    Steps:
      1. Parse the repo path from the command line with argparse.
      2. Call read_commits() to collect all commit data.
            3. Save every commit to  data/commits.csv  and every changed file
         to  data/file_changes.csv  with pandas.
      4. Print the total commit count and the commits per author.
    """

    # --- Step 1: parse arguments ---
    # argparse handles --help, missing args, and usage messages automatically.
    parser = argparse.ArgumentParser(
        description="FairShare: read commits from a local git repo and save to CSV."
    )
    parser.add_argument(
        "repo_path",
        help="Path to the local git repository you want to analyse.",
    )
    args = parser.parse_args()   # args.repo_path holds the value the user typed

    # --- Step 2: read commits ---
    try:
        commits = read_commits(args.repo_path)
    except (FileNotFoundError, NotADirectoryError, ValueError) as err:
        print(f"Error: {err}")
        sys.exit(1)

    if not commits:
        print("No commits found — nothing to save.")
        sys.exit(0)

    # --- Step 3: save to data/commits.csv ---
    # Build a DataFrame (a table) from the list of commit dicts.
    df = pd.DataFrame(commits)

    output_path = Path("data") / "commits.csv"
    output_path.parent.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False)

    # One row per changed file; columns= keeps the header even if there are no rows.
    file_changes = pd.DataFrame(read_file_changes(args.repo_path), columns=FILE_CHANGE_COLUMNS)
    file_changes_path = output_path.with_name("file_changes.csv")
    file_changes.to_csv(file_changes_path, index=False)

    # --- Step 4: print summary ---
    print(f"\nSaved {len(df)} commit(s) to {output_path}")
    print(f"Saved {len(file_changes)} file change(s) to {file_changes_path}")


if __name__ == "__main__":
    main()