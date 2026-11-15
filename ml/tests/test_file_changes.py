import sys
from pathlib import Path

import pandas as pd
import pytest

from fairshare_ml.cleaning.read_commits import (
    FILE_CHANGE_COLUMNS,
    main,
    read_commits,
    read_file_changes,
)
from tests.helpers import git


@pytest.fixture
def files_repo(tmp_path: Path) -> Path:
    """
    Build a repo that shows every kind of file change.

    Commit history (oldest -> newest):
      1. Alice adds a.py (3 lines) and b.py (2 lines)
      2. Bob   edits a.py (1 line replaced), adds docs/NOTES.TXT (1 line)
               and Makefile (1 line)
      3. Alice deletes b.py
      4. Bob   renames a.py to c.py (content unchanged)
    """
    repo = tmp_path / "files_repo"
    repo.mkdir()
    r = str(repo)

    git(["init"], cwd=r)
    git(["config", "user.email", "ci@test.com"], cwd=r)
    git(["config", "user.name", "CI"], cwd=r)

    def commit(author: str, message: str) -> None:
        """Stage everything (including deletions) and commit as `author`."""
        git(["add", "-A"], cwd=r)
        git(["commit", f"--author={author}", "-m", message], cwd=r)

    (repo / "a.py").write_text("a1\na2\na3\n", encoding="utf-8")
    (repo / "b.py").write_text("b1\nb2\n", encoding="utf-8")
    commit("Alice <alice@uni.edu>", "add a.py and b.py")

    (repo / "a.py").write_text("a1\nCHANGED\na3\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "NOTES.TXT").write_text("note\n", encoding="utf-8")
    (repo / "Makefile").write_text("all:\n", encoding="utf-8")
    commit("Bob <bob@uni.edu>", "edit a.py, add notes and Makefile")

    (repo / "b.py").unlink()
    commit("Alice <alice@uni.edu>", "delete b.py")

    git(["mv", "a.py", "c.py"], cwd=r)
    commit("Bob <bob@uni.edu>", "rename a.py to c.py")

    return repo


def _changes_per_commit(repo: Path) -> list[dict]:
    """For each commit (oldest first), return its rows keyed by file path."""
    hashes = [c["hash"] for c in read_commits(str(repo))]
    rows = read_file_changes(str(repo))
    return [{r["path"]: r for r in rows if r["hash"] == h} for h in hashes]


class TestReadFileChanges:
    """read_file_changes() returns one row per file changed in each commit."""

    def test_one_row_per_changed_file(self, files_repo):
        """Commits touch 2, 3, 1 and 1 files, so there are four groups of rows."""
        per_commit = _changes_per_commit(files_repo)
        assert [len(rows) for rows in per_commit] == [2, 3, 1, 1]

    def test_each_row_has_the_six_keys(self, files_repo):
        """Every row has exactly the six expected keys."""
        expected = {"hash", "path", "extension", "lines_added",
                    "lines_deleted", "change_type"}
        for row in read_file_changes(str(files_repo)):
            assert set(row) == expected

    def test_added_files(self, files_repo):
        """New files are ADD rows with all their lines counted as added."""
        first = _changes_per_commit(files_repo)[0]
        assert first["a.py"]["change_type"] == "ADD"
        assert first["a.py"]["lines_added"] == 3
        assert first["a.py"]["lines_deleted"] == 0
        assert first["b.py"]["lines_added"] == 2

    def test_modified_file(self, files_repo):
        """Replacing one line counts as 1 added and 1 deleted."""
        edit = _changes_per_commit(files_repo)[1]["a.py"]
        assert edit["change_type"] == "MODIFY"
        assert edit["lines_added"] == 1
        assert edit["lines_deleted"] == 1

    def test_extension_is_lower_case_and_may_be_empty(self, files_repo):
        """'NOTES.TXT' gives '.txt'; 'Makefile' has no extension."""
        second = _changes_per_commit(files_repo)[1]
        assert second["docs/NOTES.TXT"]["extension"] == ".txt"
        assert second["Makefile"]["extension"] == ""

    def test_nested_path_is_kept(self, files_repo):
        """The path includes its folders, not just the file name."""
        assert "docs/NOTES.TXT" in _changes_per_commit(files_repo)[1]

    def test_deleted_file_keeps_its_old_path(self, files_repo):
        """A deleted file has no new path, so its old path is used."""
        deleted = _changes_per_commit(files_repo)[2]["b.py"]
        assert deleted["change_type"] == "DELETE"
        assert deleted["lines_added"] == 0
        assert deleted["lines_deleted"] == 2

    def test_renamed_file_uses_its_new_path(self, files_repo):
        """A rename is listed once, under the new name, with no line changes."""
        last = _changes_per_commit(files_repo)[3]
        assert list(last) == ["c.py"]
        assert last["c.py"]["change_type"] == "RENAME"
        assert last["c.py"]["lines_added"] == 0

    def test_line_counts_match_commit_totals(self, files_repo):
        """Per-file lines add up to each commit's insertions and deletions."""
        rows = read_file_changes(str(files_repo))
        for commit in read_commits(str(files_repo)):
            mine = [r for r in rows if r["hash"] == commit["hash"]]
            assert sum(r["lines_added"] for r in mine) == commit["insertions"]
            assert sum(r["lines_deleted"] for r in mine) == commit["deletions"]

    def test_missing_path_raises_file_not_found(self):
        """A path that doesn't exist raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="does not exist"):
            read_file_changes("/no/such/path/on/this/machine")

    def test_non_git_folder_raises_value_error(self, tmp_path):
        """A folder without .git raises ValueError."""
        with pytest.raises(ValueError, match="Not a git repository"):
            read_file_changes(str(tmp_path))


class TestMain:
    """main() writes both CSV files."""

    def test_main_saves_both_csv_files(self, files_repo, tmp_path, monkeypatch):
        """commits.csv keeps its 9 columns and file_changes.csv has 7 rows."""
        work = tmp_path / "work"
        work.mkdir()
        monkeypatch.chdir(work)
        monkeypatch.setattr(sys, "argv", ["read_commits", str(files_repo)])

        main()

        commits = pd.read_csv(work / "data" / "commits.csv")
        file_changes = pd.read_csv(work / "data" / "file_changes.csv")
        assert list(commits.columns) == [
            "hash", "author_name", "author_email", "author_date",
            "insertions", "deletions", "files_changed", "is_merge", "message",
        ]
        assert len(commits) == 4
        assert list(file_changes.columns) == FILE_CHANGE_COLUMNS
        assert len(file_changes) == 7
