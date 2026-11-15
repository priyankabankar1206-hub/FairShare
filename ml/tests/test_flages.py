from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from fairshare_ml.cleaning.features import extract_features
from fairshare_ml.cleaning.hygiene import flag_commits
from fairshare_ml.cleaning.read_commits import read_commits, read_whitespace_only_commits
from fairshare_ml.inference import analyze_repository
from fairshare_ml.scoring.flags import MAX_TINY_LINES, MIN_RUN, split_commit_members
from tests.helpers import git, init_repo

ALICE = "Alice <alice@uni.edu>"
BOB = "Bob <bob@uni.edu>"


def _commit(repo: Path, author: str, files: dict, when: str = "") -> None:
    """Write `files` ({path: text or bytes}) and commit as `author` (at `when`, if given)."""
    for name, content in files.items():
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        (repo / name).write_bytes(data)
    git(["add", "-A"], cwd=str(repo))
    date = [f"--date={when}"] if when else []
    git(["commit", f"--author={author}", *date, "-m", "change"], cwd=str(repo))


V1 = "def f(x):\n    return x\n\nprint(1)\n"
SPACED = "def f(x):   \n        return x\n\n\n\nprint(1)\n"
V3 = "def f(x):\n    return x + 1\n\nprint(1)\n"
V3_CRLF = V3.replace("\n", "\r\n")
V3_BLANKS = V3_CRLF.replace("\r\n\r\n", "\r\n\r\n\r\n\r\n")


@pytest.fixture
def whitespace_repo(tmp_path: Path) -> Path:
    """
    Six commits:
      c1 real code            c2 spaces + indentation + blank lines (whitespace only)
      c3 real change          c4 CRLF line endings only (whitespace only)
      c5 extra blank lines only (whitespace only)
      c6 whitespace edit in a.py AND a new real file b.py (NOT whitespace only)
    """
    repo = init_repo(tmp_path / "ws")
    _commit(repo, ALICE, {"a.py": V1})
    _commit(repo, BOB, {"a.py": SPACED})
    _commit(repo, ALICE, {"a.py": V3})
    _commit(repo, BOB, {"a.py": V3_CRLF})
    _commit(repo, BOB, {"a.py": V3_BLANKS})
    _commit(repo, BOB, {"a.py": V3_BLANKS + "   \n", "b.py": "new = 1\n"})
    return repo


class TestWhitespaceOnlyCommits:
    """read_whitespace_only_commits() finds commits that only change whitespace."""

    def test_finds_exactly_the_whitespace_only_commits(self, whitespace_repo):
        """c2, c4 and c5 are found; real commits and the mixed c6 are not."""
        hashes = [c["hash"] for c in read_commits(str(whitespace_repo))]
        found = read_whitespace_only_commits(str(whitespace_repo))
        assert found == {hashes[1], hashes[3], hashes[4]}

    def test_empty_repository_gives_empty_set(self, tmp_path):
        """git fails on a repo without commits; the function returns an empty set."""
        assert read_whitespace_only_commits(str(init_repo(tmp_path / "empty"))) == set()

    def test_bad_path_raises(self, tmp_path):
        """A folder that does not exist raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            read_whitespace_only_commits(str(tmp_path / "nope"))

    def test_features_flag_them_as_no_op(self, whitespace_repo):
        """extract_features() marks those commits 'no_op' and the rest 'substantive'."""
        flags = list(extract_features(str(whitespace_repo))["flag"])
        assert flags == ["substantive", "no_op", "substantive", "no_op", "no_op", "substantive"]


def _hygiene_tables(is_merge=False, name="Alice", path="a.py"):
    """One commit 'h' with one file, for testing flag precedence."""
    commits = pd.DataFrame(
        [("h", name, "alice@uni.edu", 1, 0, 1, is_merge)],
        columns=["hash", "author_name", "author_email", "insertions",
                 "deletions", "files_changed", "is_merge"],
    )
    files = pd.DataFrame(
        [("h", path, ".py", 1, 0, "MODIFY")],
        columns=["hash", "path", "extension", "lines_added", "lines_deleted", "change_type"],
    )
    return commits, files


class TestNoOpFlag:
    """flag_commits() gives whitespace-only commits the flag 'no_op'."""

    def test_whitespace_only_commit_is_no_op(self):
        """A listed hash becomes 'no_op'."""
        commits, files = _hygiene_tables()
        assert flag_commits(commits, files, frozenset({"h"})).iloc[0]["flag"] == "no_op"

    def test_default_behaviour_is_unchanged(self):
        """Without the new argument the commit stays 'substantive'."""
        commits, files = _hygiene_tables()
        assert flag_commits(commits, files).iloc[0]["flag"] == "substantive"

    @pytest.mark.parametrize("kwargs, expected", [
        ({"is_merge": True}, "merge"),
        ({"name": "dependabot[bot]"}, "bot"),
        ({"path": "package-lock.json"}, "generated"),
    ])
    def test_other_flags_win_over_no_op(self, kwargs, expected):
        """Merge, bot and generated are checked first."""
        commits, files = _hygiene_tables(**kwargs)
        assert flag_commits(commits, files, frozenset({"h"})).iloc[0]["flag"] == expected


T0 = pd.Timestamp("2026-03-01 10:00:00", tz="UTC")


def burst(member: str, lines: list[int], minutes: list[int]) -> pd.DataFrame:
    """Commits by one member: lines[i] code lines added, minutes[i] after T0."""
    return pd.DataFrame({
        "member_id": member,
        "author_date": [T0 + timedelta(minutes=m) for m in minutes],
        "code_lines": lines, "test_lines": 0, "doc_lines": 0,
    })


class TestSplitCommitMembers:
    """split_commit_members() finds runs of tiny commits close together in time."""

    def test_a_burst_is_flagged(self):
        """Five 1-line commits, 5 minutes apart."""
        assert split_commit_members(burst("m_1", [1] * MIN_RUN, [0, 5, 10, 15, 20])) == {"m_1"}

    def test_one_commit_too_few_is_not_flagged(self):
        """One fewer than MIN_RUN is not a burst."""
        n = MIN_RUN - 1
        assert split_commit_members(burst("m_1", [1] * n, [5 * i for i in range(n)])) == set()

    def test_commits_far_apart_are_not_a_burst(self):
        """Tiny commits two hours apart are just small commits."""
        assert split_commit_members(burst("m_1", [1] * MIN_RUN, [120 * i for i in range(MIN_RUN)])) == set()

    def test_a_bigger_commit_breaks_the_run(self):
        """2 tiny, 1 big, 3 tiny: no run reaches MIN_RUN."""
        lines = [1, 1, 50, 1, 1, 1]
        assert split_commit_members(burst("m_1", lines, [0, 5, 10, 15, 20, 25])) == set()

    def test_size_limit_is_inclusive(self):
        """MAX_TINY_LINES lines is still tiny; one more is not."""
        times = [0, 5, 10, 15, 20]
        assert split_commit_members(burst("m_1", [MAX_TINY_LINES] * 5, times)) == {"m_1"}
        assert split_commit_members(burst("m_1", [MAX_TINY_LINES + 1] * 5, times)) == set()

    def test_commits_with_no_added_lines_do_not_count(self):
        """Renames and binary-only commits (0 lines) are not tiny work."""
        assert split_commit_members(burst("m_1", [0] * 6, [0, 5, 10, 15, 20, 25])) == set()

    def test_input_order_does_not_matter(self):
        """Commits are sorted by time before looking for runs."""
        shuffled = burst("m_1", [1] * 5, [20, 0, 15, 5, 10])
        assert split_commit_members(shuffled) == {"m_1"}

    def test_only_the_bursting_member_is_flagged(self):
        """A second member with spread-out commits is left alone."""
        both = pd.concat([
            burst("m_1", [1] * 5, [0, 5, 10, 15, 20]),
            burst("m_2", [1] * 5, [0, 200, 400, 600, 800]),
        ])
        assert split_commit_members(both) == {"m_1"}

    def test_mixed_time_zones_compare_by_instant(self):
        """Dates written in different time zones are compared as real moments."""
        zones = ["UTC", "Asia/Kolkata", "America/New_York", "UTC", "Asia/Kolkata"]
        table = burst("m_1", [1] * 5, [0, 5, 10, 15, 20])
        table["author_date"] = [d.tz_convert(z) for d, z in zip(table["author_date"], zones)]
        assert split_commit_members(table.astype({"author_date": object})) == {"m_1"}

    def test_empty_input_gives_empty_set(self):
        """No commits, no flags."""
        assert split_commit_members(burst("m_1", [], [])) == set()


def _request(repo: Path) -> dict:
    """A request for Alice (m_1) and Bob (m_2)."""
    return {"team_id": "t_1", "repo_path": str(repo), "members": [
        {"member_id": "m_1", "emails": ["alice@uni.edu"]},
        {"member_id": "m_2", "emails": ["bob@uni.edu"]},
    ]}


def _flags(response: dict) -> dict:
    """{member_id: flags} from a response."""
    return {m["member_id"]: m["flags"] for m in response["members"]}


class TestFlagsInTheResponse:
    """analyze_repository() reports whitespace_only and split_commits."""

    def test_whitespace_only_flag(self, tmp_path):
        """Bob reformats Alice's file: Bob gets 'whitespace_only', Alice nothing."""
        repo = init_repo(tmp_path / "ws")
        _commit(repo, ALICE, {"a.py": V1})
        _commit(repo, ALICE, {"b.py": "y = 2\nz = 3\n"})
        _commit(repo, BOB, {"a.py": SPACED})
        assert _flags(analyze_repository(_request(repo))) == {"m_1": [], "m_2": ["whitespace_only"]}

    def test_split_commits_flag(self, tmp_path):
        """Bob makes six 1-line commits five minutes apart; Alice makes one big commit."""
        repo = init_repo(tmp_path / "split")
        _commit(repo, ALICE, {"a.py": "x = 1\n" * 40}, "2026-03-01 09:00:00 +0000")
        for i in range(6):
            _commit(repo, BOB, {"b.py": "y = 2\n" * (i + 1)}, f"2026-03-01 10:{5 * i:02d}:00 +0000")
        assert _flags(analyze_repository(_request(repo))) == {"m_1": [], "m_2": ["split_commits"]}

    def test_same_commits_days_apart_are_not_flagged(self, tmp_path):
        """The same six tiny commits, one per day, are ordinary work."""
        repo = init_repo(tmp_path / "slow")
        _commit(repo, ALICE, {"a.py": "x = 1\n" * 40}, "2026-03-01 09:00:00 +0000")
        for i in range(6):
            _commit(repo, BOB, {"b.py": "y = 2\n" * (i + 1)}, f"2026-03-0{i + 2} 10:00:00 +0000")
        assert _flags(analyze_repository(_request(repo)))["m_2"] == []

    def test_flags_are_sorted_and_can_combine(self, tmp_path):
        """A member with several flags gets them in alphabetical order."""
        repo = init_repo(tmp_path / "combo")
        _commit(repo, ALICE, {"a.py": "x = 1\n" * 40}, "2026-03-01 09:00:00 +0000")
        _commit(repo, BOB, {"package-lock.json": "{}\n" * 30}, "2026-03-01 09:30:00 +0000")
        for i in range(6):
            _commit(repo, BOB, {"b.py": "y = 2\n" * (i + 1)}, f"2026-03-01 10:{5 * i:02d}:00 +0000")
        assert _flags(analyze_repository(_request(repo)))["m_2"] == ["generated_files", "split_commits"]