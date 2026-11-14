# tests/test_inference.py
# FairShare - Milestone 12
# Tests for analyze_repository(), the one function the backend calls.
#
# Run:  python -m pytest tests/test_inference.py -v

import copy
import os
import subprocess
from pathlib import Path

import pytest

from fairshare_ml.cleaning.read_commits import read_commits
from fairshare_ml.inference import (
    analyze_repository,
    gini_coefficient,
    imbalance_label,
)

ALICE = "Alice <alice@uni.edu>"
ALICE_HOME = "Alice <alice.home@gmail.com>"
BOB = "Bob <bob@uni.edu>"
BOT = "dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>"


def _git(args: list[str], cwd: str) -> None:
    """Run  git <args>  inside cwd. Line-ending conversion is switched off."""
    subprocess.run(
        ["git"] + args,
        cwd=cwd,
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_COUNT": "1",
             "GIT_CONFIG_KEY_0": "core.autocrlf",
             "GIT_CONFIG_VALUE_0": "false"},
    )


def _init_repo(path: Path) -> Path:
    """Create an empty git repository at `path`."""
    path.mkdir()
    _git(["init"], cwd=str(path))
    _git(["config", "user.email", "ci@test.com"], cwd=str(path))
    _git(["config", "user.name", "CI"], cwd=str(path))
    return path


def _commit(repo: Path, filename: str, add_lines: int, author: str, text: str = "line") -> None:
    """Append `add_lines` lines to `filename` and commit it as `author`."""
    with open(repo / filename, "a", encoding="utf-8", newline="\n") as f:
        f.write(f"{text}\n" * add_lines)
    _git(["add", "-A"], cwd=str(repo))
    _git(["commit", f"--author={author}", "-m", f"edit {filename}"], cwd=str(repo))


@pytest.fixture
def team_repo(tmp_path: Path) -> Path:
    """
    A small team repo.

      1. Alice adds a.py (6 lines)
      2. Bob   adds b.py (2 lines)
      3. Alice adds package-lock.json (500 lines)  -> generated, not counted
      4. A bot adds c.py (3 lines)                 -> bot, not counted
      5. Alice (second email) adds 2 lines to a.py

    Counted work: Alice 6 + 2 = 8 lines, Bob 2 lines -> shares 0.8 / 0.2.
    """
    repo = _init_repo(tmp_path / "team_repo")
    _commit(repo, "a.py", 6, ALICE)
    _commit(repo, "b.py", 2, BOB)
    _commit(repo, "package-lock.json", 500, ALICE, text="{}")
    _commit(repo, "c.py", 3, BOT)
    _commit(repo, "a.py", 2, ALICE_HOME)
    return repo


def make_request(repo: Path, **changes) -> dict:
    """Build a request for team_repo's three members (Carol has no commits)."""
    request = {
        "team_id": "t_001",
        "repo_path": str(repo),
        "members": [
            {"member_id": "m_1", "emails": ["alice@uni.edu", "alice.home@gmail.com"]},
            {"member_id": "m_2", "emails": ["bob@uni.edu"]},
            {"member_id": "m_3", "emails": ["carol@uni.edu"]},
        ],
    }
    request.update(changes)
    return request


def share_of(response: dict, member_id: str) -> float:
    """Pick one member's share from a response."""
    return next(m["share"] for m in response["members"] if m["member_id"] == member_id)


# ---------------------------------------------------------------------------
# Shape of the response (the contract)
# ---------------------------------------------------------------------------

class TestResponseShape:
    """The response has exactly the shape the backend's schema expects."""

    def test_top_level_keys(self, team_repo):
        """The six top-level keys are present."""
        response = analyze_repository(make_request(team_repo))
        assert set(response) == {"team_id", "model_version", "as_of",
                                 "members", "imbalance", "warnings"}
        assert response["team_id"] == "t_001"

    def test_member_keys_and_facets(self, team_repo):
        """Each member has the five keys, and facets has the five facet names."""
        response = analyze_repository(make_request(team_repo))
        for member in response["members"]:
            assert set(member) == {"member_id", "share", "facets", "flags", "evidence"}
            assert set(member["facets"]) == {"code", "review", "testing",
                                             "docs", "coordination"}
        assert set(response["imbalance"]) == {"gini", "label"}

    def test_model_version_says_stub(self, team_repo):
        """The stub labels itself, so nobody mistakes it for FairShare-Lite."""
        assert analyze_repository(make_request(team_repo))["model_version"] == "stub-0.1"

    def test_members_keep_the_request_order(self, team_repo):
        """Members come back in the order they were sent."""
        response = analyze_repository(make_request(team_repo))
        assert [m["member_id"] for m in response["members"]] == ["m_1", "m_2", "m_3"]


# ---------------------------------------------------------------------------
# The numbers
# ---------------------------------------------------------------------------

class TestScores:
    """Shares, evidence, imbalance and dates are correct on a known repo."""

    def test_shares_ignore_lock_file_and_bot_commits(self, team_repo):
        """Alice 8 lines, Bob 2, Carol 0 -> 0.8 / 0.2 / 0.0 (500-line lock file ignored)."""
        response = analyze_repository(make_request(team_repo))
        assert share_of(response, "m_1") == pytest.approx(0.8)
        assert share_of(response, "m_2") == pytest.approx(0.2)
        assert share_of(response, "m_3") == 0.0
        assert sum(m["share"] for m in response["members"]) == pytest.approx(1.0)

    def test_code_facet_equals_the_share_in_the_stub(self, team_repo):
        """In the stub only the code facet is filled."""
        alice = analyze_repository(make_request(team_repo))["members"][0]
        assert alice["facets"]["code"] == pytest.approx(0.8)
        assert alice["facets"]["review"] == 0.0

    def test_a_members_second_email_is_counted(self, team_repo):
        """Commit 5 used alice.home@gmail.com, yet counts for Alice (m_1)."""
        evidence = analyze_repository(make_request(team_repo))["members"][0]["evidence"]
        assert len(evidence) == 2

    def test_email_matching_ignores_case_and_spaces(self, team_repo):
        """'  ALICE@UNI.EDU ' matches 'alice@uni.edu'."""
        request = make_request(team_repo)
        request["members"][0]["emails"] = ["  ALICE@UNI.EDU ", "alice.home@gmail.com"]
        assert share_of(analyze_repository(request), "m_1") == pytest.approx(0.8)

    def test_evidence_lists_the_biggest_commits_first(self, team_repo):
        """Alice's evidence: the 6-line commit, then the 2-line commit."""
        evidence = analyze_repository(make_request(team_repo))["members"][0]["evidence"]
        assert [e["reason"] for e in evidence] == [
            "Added 6 lines in 1 file",
            "Added 2 lines in 1 file",
        ]
        assert all(len(e["commit"]) == 7 for e in evidence)

    def test_member_without_commits_has_empty_evidence(self, team_repo):
        """Carol never committed: share 0.0 and no evidence."""
        carol = analyze_repository(make_request(team_repo))["members"][2]
        assert carol["share"] == 0.0
        assert carol["evidence"] == []

    def test_imbalance_uses_all_members(self, team_repo):
        """Shares 0.8 / 0.2 / 0.0 give a Gini of about 0.533, which is 'at risk'."""
        imbalance = analyze_repository(make_request(team_repo))["imbalance"]
        assert imbalance["gini"] == pytest.approx(0.5333, abs=1e-3)
        assert imbalance["label"] == "at risk"

    def test_as_of_is_the_newest_commit_date(self, team_repo):
        """as_of is the date of the newest commit, not today's date."""
        newest = max(c["author_date"] for c in read_commits(str(team_repo)))
        response = analyze_repository(make_request(team_repo))
        assert response["as_of"] == newest.date().isoformat()

    def test_no_warnings_on_a_healthy_repo(self, team_repo):
        """Bots are not 'unmapped authors', so warnings stay empty."""
        assert analyze_repository(make_request(team_repo))["warnings"] == []

    def test_same_input_twice_gives_identical_output(self, team_repo):
        """Running twice on the same input gives exactly the same response."""
        request = make_request(team_repo)
        assert analyze_repository(request) == analyze_repository(request)

    def test_request_is_not_modified_and_extra_fields_are_ignored(self, team_repo):
        """Unused fields are accepted, and the caller's dict is left untouched."""
        request = make_request(
            team_repo, repo_url="https://github.com/x/y", head_commit_sha="abc",
            week_number=3, extra_parameters={"k": 1},
        )
        before = copy.deepcopy(request)
        analyze_repository(request)
        assert request == before


# ---------------------------------------------------------------------------
# Warnings and edge cases
# ---------------------------------------------------------------------------

class TestWarningsAndEdges:
    """Unusual repos never crash and say what is wrong."""

    def test_unlisted_author_gives_unmapped_warning(self, team_repo):
        """Bob's email is not in any member, so his commit is ignored and flagged."""
        request = make_request(team_repo)
        request["members"][1]["emails"] = ["bob.other@elsewhere.com"]
        response = analyze_repository(request)
        assert "unmapped_authors" in response["warnings"]
        assert share_of(response, "m_1") == pytest.approx(1.0)
        assert share_of(response, "m_2") == 0.0

    def test_single_commit_is_insufficient_data(self, tmp_path):
        """One commit is not enough: warning, and all shares are 0.0."""
        repo = _init_repo(tmp_path / "one")
        _commit(repo, "a.py", 5, ALICE)
        response = analyze_repository(make_request(repo))
        assert "insufficient_data" in response["warnings"]
        assert all(m["share"] == 0.0 for m in response["members"])

    def test_empty_repository_does_not_crash(self, tmp_path):
        """A repo with no commits gives insufficient_data and a valid response."""
        repo = _init_repo(tmp_path / "empty")
        response = analyze_repository(make_request(repo))
        assert "insufficient_data" in response["warnings"]
        assert len(response["members"]) == 3
        assert isinstance(response["as_of"], str)

    def test_team_of_one_gets_the_whole_share(self, tmp_path):
        """A one-person team has a share of exactly 1 and a balanced label."""
        repo = _init_repo(tmp_path / "solo")
        _commit(repo, "a.py", 3, ALICE)
        _commit(repo, "a.py", 4, ALICE)
        request = {"team_id": "t_9", "repo_path": str(repo),
                   "members": [{"member_id": "m_1", "emails": ["alice@uni.edu"]}]}
        response = analyze_repository(request)
        assert response["members"][0]["share"] == 1.0
        assert response["imbalance"] == {"gini": 0.0, "label": "balanced"}

    def test_bad_repo_path_raises(self, tmp_path):
        """A repo_path that does not exist raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            analyze_repository(make_request(tmp_path / "nope"))


class TestRequestChecks:
    """Malformed requests raise a clear ValueError."""

    @pytest.mark.parametrize("key", ["team_id", "repo_path", "members"])
    def test_missing_required_field(self, team_repo, key):
        """team_id, repo_path and members are all required."""
        request = make_request(team_repo)
        del request[key]
        with pytest.raises(ValueError, match=key):
            analyze_repository(request)

    def test_empty_member_list(self, team_repo):
        """At least one member is needed."""
        with pytest.raises(ValueError, match="members"):
            analyze_repository(make_request(team_repo, members=[]))

    def test_member_without_emails_list(self, team_repo):
        """Each member needs a list of emails."""
        with pytest.raises(ValueError, match="emails"):
            analyze_repository(make_request(team_repo, members=[{"member_id": "m_1"}]))

    def test_duplicate_member_id(self, team_repo):
        """Two members cannot share a member_id."""
        members = [{"member_id": "m_1", "emails": ["a@x.com"]},
                   {"member_id": "m_1", "emails": ["b@x.com"]}]
        with pytest.raises(ValueError, match="duplicate member_id"):
            analyze_repository(make_request(team_repo, members=members))

    def test_email_shared_by_two_members(self, team_repo):
        """One email cannot belong to two members, and the error hides the email."""
        members = [{"member_id": "m_1", "emails": ["same@x.com"]},
                   {"member_id": "m_2", "emails": ["SAME@x.com "]}]
        with pytest.raises(ValueError, match="more than one member") as error:
            analyze_repository(make_request(team_repo, members=members))
        assert "same@x.com" not in str(error.value).lower()

    def test_request_must_be_a_dict(self):
        """Anything but a dict is rejected."""
        with pytest.raises(ValueError, match="dict"):
            analyze_repository("not a dict")


# ---------------------------------------------------------------------------
# The two small helpers
# ---------------------------------------------------------------------------

class TestGiniAndLabel:
    """gini_coefficient() and imbalance_label() on hand-checkable numbers."""

    @pytest.mark.parametrize("shares, expected", [
        ([0.5, 0.5], 0.0),
        ([1.0, 0.0], 0.5),
        ([1.0], 0.0),
        ([0.0, 0.0], 0.0),
        ([0.8, 0.2, 0.0], 0.5333),
    ])
    def test_gini_values(self, shares, expected):
        """Even split -> 0, one person has everything -> 0.5 for two people."""
        assert gini_coefficient(shares) == pytest.approx(expected, abs=1e-3)

    @pytest.mark.parametrize("gini, label", [
        (0.0, "balanced"), (0.24, "balanced"),
        (0.25, "watch"), (0.40, "watch"),
        (0.41, "at risk"), (0.9, "at risk"),
    ])
    def test_label_cut_offs(self, gini, label):
        """The label changes at 0.25 and just above 0.40."""
        assert imbalance_label(gini) == label