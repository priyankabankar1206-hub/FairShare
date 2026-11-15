from pathlib import Path

import pytest

from fairshare_ml.cleaning.read_commits import validate_repo_path, read_commits
from tests.helpers import git


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
    r = str(repo)

    git(["init"], cwd=r)

    git(["config", "user.email", "ci@test.com"], cwd=r)
    git(["config", "user.name",  "CI"],           cwd=r)

    (repo / "hello.py").write_text("line_a\nline_b\nline_c\n",
                                   encoding="utf-8")
    git(["add", "hello.py"], cwd=r)
    git(["commit",
          "--author=Alice <alice@uni.edu>",
          "-m", "Alice: create hello.py"],
         cwd=r)

    (repo / "hello.py").write_text("line_a\nline_b\nline_c\nline_d\n",
                                   encoding="utf-8")
    git(["add", "hello.py"], cwd=r)
    git(["commit",
          "--author=Alice <alice@uni.edu>",
          "-m", "Alice: append line_d"],
         cwd=r)

    (repo / "world.py").write_text("world_x\nworld_y\n",
                                   encoding="utf-8")
    git(["add", "world.py"], cwd=r)
    git(["commit",
          "--author=Bob <bob@uni.edu>",
          "-m", "Bob: create world.py"],
         cwd=r)

    return repo


class TestValidation:
    """These tests check the guard clauses before PyDriller even starts."""

    def test_missing_path_raises_file_not_found(self):
        """A path that doesn't exist on disk must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="does not exist"):
            validate_repo_path("/no/such/path/on/this/machine")

    def test_plain_folder_raises_value_error(self, tmp_path):
        """A folder with no .git sub-folder must raise ValueError."""
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


REQUIRED_KEYS = {
    "hash", "author_name", "author_email", "author_date",
    "insertions", "deletions", "files_changed", "is_merge", "message",
}


class TestDataShape:
    """Every commit dict must have exactly the 9 expected keys and sane types."""

    def test_all_nine_keys_present(self, tiny_repo):
        """Every commit dict has all 9 expected keys."""
        commits = read_commits(str(tiny_repo))
        for c in commits:
            missing = REQUIRED_KEYS - set(c.keys())
            assert not missing, f"Missing keys in commit {c['hash'][:7]}: {missing}"

    def test_no_extra_keys(self, tiny_repo):
        """No commit dict has a key beyond the 9 expected ones."""
        commits = read_commits(str(tiny_repo))
        for c in commits:
            extra = set(c.keys()) - REQUIRED_KEYS
            assert not extra, f"Unexpected keys in commit {c['hash'][:7]}: {extra}"

    def test_hash_is_40_char_string(self, tiny_repo):
        """Every hash is a 40-character string."""
        commits = read_commits(str(tiny_repo))
        for c in commits:
            assert isinstance(c["hash"], str) and len(c["hash"]) == 40

    def test_is_merge_is_bool_and_false(self, tiny_repo):
        """None of our 3 simple commits is a merge — all must be False."""
        commits = read_commits(str(tiny_repo))
        for c in commits:
            assert type(c["is_merge"]) is bool
            assert c["is_merge"] is False

    def test_message_has_no_newline(self, tiny_repo):
        """message is the subject line only — no embedded newlines."""
        commits = read_commits(str(tiny_repo))
        for c in commits:
            assert "\n" not in c["message"]