import argparse
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
from pydriller import Repository

FILE_CHANGE_COLUMNS = [
    "hash",
    "path",
    "extension",
    "lines_added",
    "lines_deleted",
    "change_type",
]


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

    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {repo_path}")

    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {repo_path}")

    if not (path / ".git").exists():
        raise ValueError(
            f"Not a git repository (no .git folder found): {repo_path}"
        )


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
    validate_repo_path(repo_path)
    return [
        {
            "hash": commit.hash,
            "author_name": commit.author.name,
            "author_email": commit.author.email,
            "author_date": commit.author_date,
            "insertions": commit.insertions,
            "deletions": commit.deletions,
            "files_changed": commit.files,
            "is_merge": commit.merge,
            "message": commit.msg.splitlines()[0].strip() if commit.msg else "",
        }
        for commit in Repository(repo_path).traverse_commits()
    ]


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
    if result.returncode != 0:
        return {}

    totals: dict[str, int] = {}
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        if re.fullmatch(r"[0-9a-f]{40}", line):
            current = line
            totals[current] = 0
        elif "\t" in line:
            added, deleted, _ = line.split("\t", 2)
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
    Usage:  python -m fairshare_ml.cleaning.read_commits <path-to-git-repo>

    Reads every commit and every changed file, saves them to data/commits.csv
    and data/file_changes.csv, and prints how many rows were saved. A bad path
    prints an error and exits with code 1; a repository with no commits prints
    a message and exits with code 0.
    """

    parser = argparse.ArgumentParser(
        description="FairShare: read commits from a local git repo and save to CSV."
    )
    parser.add_argument(
        "repo_path",
        help="Path to the local git repository you want to analyse.",
    )
    args = parser.parse_args()

    try:
        commits = read_commits(args.repo_path)
    except (FileNotFoundError, NotADirectoryError, ValueError) as err:
        print(f"Error: {err}")
        sys.exit(1)

    if not commits:
        print("No commits found — nothing to save.")
        sys.exit(0)

    df = pd.DataFrame(commits)

    output_path = Path("data") / "commits.csv"
    output_path.parent.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False)

    file_changes = pd.DataFrame(read_file_changes(args.repo_path), columns=FILE_CHANGE_COLUMNS)
    file_changes_path = output_path.with_name("file_changes.csv")
    file_changes.to_csv(file_changes_path, index=False)

    print(f"\nSaved {len(df)} commit(s) to {output_path}")
    print(f"Saved {len(file_changes)} file change(s) to {file_changes_path}")


if __name__ == "__main__":
    main()