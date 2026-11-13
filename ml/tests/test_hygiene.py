# tests/test_hygiene.py
# FairShare - Milestone 11
# Tests for the hygiene filter, using small hand-made tables (no git needed).
#
# Run:  python -m pytest tests/test_hygiene.py -v

import pandas as pd
import pytest

from fairshare_ml.cleaning.hygiene import (
    flag_commits,
    flag_file_changes,
    is_bot,
    is_generated_path,
)

COMMIT_COLUMNS = [
    "hash", "author_name", "author_email", "insertions",
    "deletions", "files_changed", "is_merge",
]
FILE_COLUMNS = ["hash", "path", "extension", "lines_added",
                "lines_deleted", "change_type"]


def make_commit(hash_, name="Alice", email="alice@uni.edu", merge=False):
    """Build one commit row (the numbers don't matter for hygiene)."""
    return (hash_, name, email, 0, 0, 0, merge)


def make_file(hash_, path, added=1, deleted=0):
    """Build one file-change row."""
    return (hash_, path, "", added, deleted, "MODIFY")


def flags_of(commits: list[tuple], files: list[tuple]) -> dict:
    """Run flag_commits and return {hash: flag}."""
    result = flag_commits(
        pd.DataFrame(commits, columns=COMMIT_COLUMNS),
        pd.DataFrame(files, columns=FILE_COLUMNS),
    )
    return dict(zip(result["hash"], result["flag"]))


# ---------------------------------------------------------------------------
# Bots
# ---------------------------------------------------------------------------

class TestIsBot:
    """is_bot() spots automated accounts without catching real people."""

    @pytest.mark.parametrize("name, email", [
        ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com"),
        ("github-actions[bot]", "x@users.noreply.github.com"),
        ("release-bot", "rb@uni.edu"),
        ("Renovate", "renovate@whitesourcesoftware.com"),
        ("Someone", "build[bot]@example.com"),
    ])
    def test_bots_are_detected(self, name, email):
        """Typical bot names and emails are detected."""
        assert is_bot(name, email)

    @pytest.mark.parametrize("name, email", [
        ("Alice", "alice@uni.edu"),
        ("Ben Abbot", "ben.abbot@uni.edu"),
        ("Robot Fan", "robotfan@uni.edu"),
    ])
    def test_people_are_not_bots(self, name, email):
        """Real people, even with 'bot' inside a name, are not flagged."""
        assert not is_bot(name, email)

    def test_missing_name_or_email_does_not_crash(self):
        """A missing name or email (NaN from a CSV) is handled."""
        assert not is_bot(float("nan"), "alice@uni.edu")


# ---------------------------------------------------------------------------
# Generated files
# ---------------------------------------------------------------------------

class TestIsGeneratedPath:
    """is_generated_path() recognises lock files, build output and vendored code."""

    @pytest.mark.parametrize("path", [
        "package-lock.json",
        "frontend/yarn.lock",
        "app/pubspec.lock",
        "Pipfile.lock",
        "node_modules/left-pad/index.js",
        "web/dist/app.min.js",
        "build/output.txt",
        "lib/models/user.g.dart",
        "static/app.js.map",
    ])
    def test_generated_paths(self, path):
        """Lock files, vendored folders, minified and generated code match."""
        assert is_generated_path(path)

    @pytest.mark.parametrize("path", [
        "src/app.py",
        "build.gradle",
        "src/build_tools.py",
        "docs/lock.md",
        "builds/notes.txt",
        "README.md",
    ])
    def test_real_files_are_not_generated(self, path):
        """Real source files with similar names do not match."""
        assert not is_generated_path(path)

    def test_case_is_ignored(self):
        """'Package-Lock.JSON' matches the same as 'package-lock.json'."""
        assert is_generated_path("Package-Lock.JSON")

    def test_windows_separators_are_accepted(self):
        """Paths with backslashes (older CSVs from Windows) still match."""
        assert is_generated_path("node_modules\\x\\index.js")


class TestFlagFileChanges:
    """flag_file_changes() adds an is_generated column."""

    def test_adds_column_and_keeps_input(self):
        """The new column is correct and the caller's table is unchanged."""
        files = pd.DataFrame(
            [make_file("h1", "src/app.py"), make_file("h1", "yarn.lock")],
            columns=FILE_COLUMNS,
        )
        before = files.copy()
        result = flag_file_changes(files)
        assert list(result["is_generated"]) == [False, True]
        pd.testing.assert_frame_equal(files, before)


# ---------------------------------------------------------------------------
# Commit flags
# ---------------------------------------------------------------------------

class TestFlagCommits:
    """flag_commits() gives every commit exactly one flag."""

    def test_each_kind_of_commit_gets_its_flag(self):
        """Normal, merge, bot, lock-file-only, mixed and empty commits."""
        commits = [
            make_commit("normal"),
            make_commit("merge", merge=True),
            make_commit("bot", "dependabot[bot]", "d@users.noreply.github.com"),
            make_commit("lockonly"),
            make_commit("mixed"),
            make_commit("nofiles"),
        ]
        files = [
            make_file("normal", "src/app.py"),
            make_file("merge", "src/app.py"),
            make_file("bot", "package-lock.json"),
            make_file("lockonly", "package-lock.json"),
            make_file("mixed", "src/app.py", added=10),
            make_file("mixed", "package-lock.json", added=500),
        ]
        assert flags_of(commits, files) == {
            "normal": "substantive",
            "merge": "merge",
            "bot": "bot",
            "lockonly": "generated",
            "mixed": "substantive",
            "nofiles": "empty",
        }

    def test_merge_beats_bot(self):
        """A merge commit made by a bot is flagged 'merge' (first rule wins)."""
        commits = [make_commit("x", "dependabot[bot]", "d@x.com", merge=True)]
        assert flags_of(commits, [make_file("x", "a.py")]) == {"x": "merge"}

    def test_clean_counts_leave_out_generated_files(self):
        """A mixed commit keeps only its real file in the clean_* columns."""
        commits = pd.DataFrame([make_commit("mixed")], columns=COMMIT_COLUMNS)
        files = pd.DataFrame(
            [make_file("mixed", "src/app.py", added=10, deleted=2),
             make_file("mixed", "package-lock.json", added=500, deleted=300)],
            columns=FILE_COLUMNS,
        )
        row = flag_commits(commits, files).iloc[0]
        assert row["clean_insertions"] == 10
        assert row["clean_deletions"] == 2
        assert row["clean_files"] == 1

    def test_lock_file_only_commit_has_zero_clean_counts(self):
        """A commit of only generated files has clean counts of 0."""
        commits = pd.DataFrame([make_commit("lock")], columns=COMMIT_COLUMNS)
        files = pd.DataFrame([make_file("lock", "yarn.lock", added=900)],
                             columns=FILE_COLUMNS)
        row = flag_commits(commits, files).iloc[0]
        assert row["clean_insertions"] == 0
        assert row["clean_files"] == 0

    def test_one_row_out_per_commit_and_columns_added(self):
        """Same number of rows, original columns kept, four columns added."""
        commits = pd.DataFrame(
            [make_commit("a"), make_commit("b")], columns=COMMIT_COLUMNS
        )
        files = pd.DataFrame([make_file("a", "x.py")], columns=FILE_COLUMNS)
        result = flag_commits(commits, files)
        assert len(result) == 2
        assert list(result.columns) == COMMIT_COLUMNS + [
            "clean_insertions", "clean_deletions", "clean_files", "flag",
        ]

    def test_inputs_are_not_modified(self):
        """The caller's two tables are left untouched."""
        commits = pd.DataFrame([make_commit("a")], columns=COMMIT_COLUMNS)
        files = pd.DataFrame([make_file("a", "x.py")], columns=FILE_COLUMNS)
        commits_before, files_before = commits.copy(), files.copy()
        flag_commits(commits, files)
        pd.testing.assert_frame_equal(commits, commits_before)
        pd.testing.assert_frame_equal(files, files_before)

    def test_empty_tables_give_an_empty_result(self):
        """No commits in, no commits out, and no crash."""
        result = flag_commits(
            pd.DataFrame(columns=COMMIT_COLUMNS),
            pd.DataFrame(columns=FILE_COLUMNS),
        )
        assert result.empty
        assert "flag" in result.columns

    def test_commits_with_no_file_rows_are_empty(self):
        """If file_changes has no rows at all, every normal commit is 'empty'."""
        commits = pd.DataFrame([make_commit("a")], columns=COMMIT_COLUMNS)
        files = pd.DataFrame(columns=FILE_COLUMNS)
        assert flag_commits(commits, files).iloc[0]["flag"] == "empty"