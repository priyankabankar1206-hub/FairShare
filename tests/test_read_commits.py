# tests/test_read_commits.py
# FairShare – Milestone 4
# Tests for read_commits.py using a real (but temporary) git repo.
#
# Run all tests:        pytest tests/
# Run with details:     pytest tests/test_read_commits.py -v

import os
import subprocess
from pathlib import Path

import pytest

from read_commits import validate_repo_path, read_commits


# ===========================================================================
# WHAT IS A FIXTURE?
# ===========================================================================
# A fixture is a function marked with @pytest.fixture that *sets something up*
# before a test runs — like creating a file, a database row, or in our case
# a tiny git repo.
#
# How it works:
#   1. You write a function and decorate it with @pytest.fixture.
#   2. Any test that lists the fixture's name as a parameter will
#      automatically receive whatever the fixture returns.
#   3. pytest handles calling the fixture and passing the value in — you
#      never call the fixture yourself.
#
# Example:
#   @pytest.fixture
#   def my_number():
#       return 42
#
#   def test_something(my_number):   # pytest sees "my_number", calls the fixture
#       assert my_number == 42       # gets 42 injected automatically
#
# The built-in `tmp_path` fixture (provided by pytest itself) gives each test
# its own fresh temporary folder on disk that is deleted after the test.
# ===========================================================================


# ---------------------------------------------------------------------------
# Helper: run a git command inside a directory
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: str) -> None:
    """
    Run  git <args>  inside the folder at cwd.
    capture_output=True  hides git's messages from the test output.
    check=True           raises an error automatically if git fails.
    """
    subprocess.run(
        ["git"] + args,
        cwd=cwd,
        check=True,
        capture_output=True,
        # Pass the current process environment so git can find itself,
        # but disable Windows line-ending conversion so counts are predictable.
        env={**os.environ, "GIT_CONFIG_COUNT": "1",
             "GIT_CONFIG_KEY_0": "core.autocrlf",
             "GIT_CONFIG_VALUE_0": "false"},
    )


# ---------------------------------------------------------------------------
# Fixture: tiny_repo
# ---------------------------------------------------------------------------

@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    """
    Build a small but real git repo in a temporary folder.

    Commit history (oldest → newest):
      1. Alice   creates hello.py   with 3 lines  → insertions=3, deletions=0
      2. Alice   appends 1 line     to hello.py   → insertions=1, deletions=0
      3. Bob     creates world.py   with 2 lines  → insertions=2, deletions=0

    Returns the Path to the repo root so tests can pass it to read_commits().

    Why subprocess instead of a library?
      subprocess calls the real `git` binary — the same tool PyDriller reads.
      That means the test repo is indistinguishable from any real project repo.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    r = str(repo)   # subprocess wants a plain string, not a Path object

    # Initialise an empty git repo
    _git(["init"], cwd=r)

    # Set a local committer identity so git commit doesn't complain.
    # (The author identity is set per-commit below with --author.)
    _git(["config", "user.email", "ci@test.com"], cwd=r)
    _git(["config", "user.name",  "CI"],           cwd=r)

    # ── Commit 1: Alice creates hello.py (3 lines) ──────────────────────────
    (repo / "hello.py").write_text("line_a\nline_b\nline_c\n",
                                   encoding="utf-8")
    _git(["add", "hello.py"], cwd=r)
    _git(["commit",
          "--author=Alice <alice@uni.edu>",
          "-m", "Alice: create hello.py"],
         cwd=r)

    # ── Commit 2: Alice appends one line to hello.py (1 insertion) ──────────
    (repo / "hello.py").write_text("line_a\nline_b\nline_c\nline_d\n",
                                   encoding="utf-8")
    _git(["add", "hello.py"], cwd=r)
    _git(["commit",
          "--author=Alice <alice@uni.edu>",
          "-m", "Alice: append line_d"],
         cwd=r)

    # ── Commit 3: Bob creates world.py (2 lines) ────────────────────────────
    (repo / "world.py").write_text("world_x\nworld_y\n",
                                   encoding="utf-8")
    _git(["add", "world.py"], cwd=r)
    _git(["commit",
          "--author=Bob <bob@uni.edu>",
          "-m", "Bob: create world.py"],
         cwd=r)

    return repo   # hand the path to any test that requests this fixture


# ===========================================================================
# Test class 1 – validation (no real repo needed)
# ===========================================================================

class TestValidation:
    """These tests check the guard clauses before PyDriller even starts."""

    def test_missing_path_raises_file_not_found(self):
        """A path that doesn't exist on disk must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="does not exist"):
            validate_repo_path("/no/such/path/on/this/machine")

    def test_plain_folder_raises_value_error(self, tmp_path):
        """A folder with no .git sub-folder must raise ValueError."""
        # tmp_path is a real, empty directory — not a git repo
        with pytest.raises(ValueError, match="Not a git repository"):
            validate_repo_path(str(tmp_path))

    def test_read_commits_bad_path_raises_file_not_found(self):
        """read_commits() must surface the same FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            read_commits("/totally/missing/path")

    def test_read_commits_non_git_folder_raises_value_error(self, tmp_path):
        """read_commits() must surface the same ValueError."""
        with pytest.raises(ValueError):
            read_commits(str(tmp_path))


# ===========================================================================
# Test class 2 – commit count and authors
# ===========================================================================

class TestCommitCountAndAuthors:
    """Check the number of commits and who made them."""

    def test_exactly_three_commits(self, tiny_repo):
        """The tiny repo was set up with exactly 3 commits."""
        commits = read_commits(str(tiny_repo))
        assert len(commits) == 3

    def test_alice_is_present(self, tiny_repo):
        """Alice made 2 commits so her name must appear."""
        commits = read_commits(str(tiny_repo))
        names = [c["author_name"] for c in commits]
        assert "Alice" in names

    def test_bob_is_present(self, tiny_repo):
        """Bob made 1 commit so his name must appear."""
        commits = read_commits(str(tiny_repo))
        names = [c["author_name"] for c in commits]
        assert "Bob" in names

    def test_alice_has_two_commits(self, tiny_repo):
        """Alice committed twice (commits 1 and 2)."""
        commits = read_commits(str(tiny_repo))
        alice_count = sum(1 for c in commits if c["author_name"] == "Alice")
        assert alice_count == 2

    def test_bob_has_one_commit(self, tiny_repo):
        """Bob committed once (commit 3)."""
        commits = read_commits(str(tiny_repo))
        bob_count = sum(1 for c in commits if c["author_name"] == "Bob")
        assert bob_count == 1


# ===========================================================================
# Test class 3 – line counts per commit
# ===========================================================================

class TestLineCounts:
    """
    Check insertions and deletions for each commit.

    traverse_commits() returns commits oldest-first, so:
      commits[0] = Alice's first commit  (create hello.py, 3 lines)
      commits[1] = Alice's second commit (append 1 line)
      commits[2] = Bob's commit          (create world.py, 2 lines)
    """

    def test_commit1_insertions(self, tiny_repo):
        """Commit 1: new file with 3 lines → 3 insertions."""
        commits = read_commits(str(tiny_repo))
        assert commits[0]["insertions"] == 3

    def test_commit1_deletions(self, tiny_repo):
        """Commit 1: new file, nothing removed → 0 deletions."""
        commits = read_commits(str(tiny_repo))
        assert commits[0]["deletions"] == 0

    def test_commit2_insertions(self, tiny_repo):
        """Commit 2: one line appended → 1 insertion."""
        commits = read_commits(str(tiny_repo))
        assert commits[1]["insertions"] == 1

    def test_commit2_deletions(self, tiny_repo):
        """Commit 2: nothing removed → 0 deletions."""
        commits = read_commits(str(tiny_repo))
        assert commits[1]["deletions"] == 0

    def test_commit3_insertions(self, tiny_repo):
        """Commit 3: new file with 2 lines → 2 insertions."""
        commits = read_commits(str(tiny_repo))
        assert commits[2]["insertions"] == 2

    def test_commit3_deletions(self, tiny_repo):
        """Commit 3: new file, nothing removed → 0 deletions."""
        commits = read_commits(str(tiny_repo))
        assert commits[2]["deletions"] == 0


# ===========================================================================
# Test class 4 – data shape (all 9 keys, correct types)
# ===========================================================================

REQUIRED_KEYS = {
    "hash", "author_name", "author_email", "author_date",
    "insertions", "deletions", "files_changed", "is_merge", "message",
}

class TestDataShape:
    """Every commit dict must have exactly the 9 expected keys and sane types."""

    def test_all_nine_keys_present(self, tiny_repo):
        commits = read_commits(str(tiny_repo))
        for c in commits:
            missing = REQUIRED_KEYS - set(c.keys())
            assert not missing, f"Missing keys in commit {c['hash'][:7]}: {missing}"

    def test_no_extra_keys(self, tiny_repo):
        commits = read_commits(str(tiny_repo))
        for c in commits:
            extra = set(c.keys()) - REQUIRED_KEYS
            assert not extra, f"Unexpected keys in commit {c['hash'][:7]}: {extra}"

    def test_hash_is_40_char_string(self, tiny_repo):
        commits = read_commits(str(tiny_repo))
        for c in commits:
            assert isinstance(c["hash"], str) and len(c["hash"]) == 40

    def test_is_merge_is_bool_and_false(self, tiny_repo):
        """None of our 3 simple commits is a merge — all must be False."""
        commits = read_commits(str(tiny_repo))
        for c in commits:
            assert type(c["is_merge"]) is bool   # must be bool, not int
            assert c["is_merge"] is False

    def test_message_has_no_newline(self, tiny_repo):
        """message is the subject line only — no embedded newlines."""
        commits = read_commits(str(tiny_repo))
        for c in commits:
            assert "\n" not in c["message"]
