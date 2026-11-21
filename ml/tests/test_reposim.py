import subprocess

import pandas as pd
import pytest

from fairshare_ml.benchmark.reposim import (
    Commit,
    Func,
    Person,
    Simulation,
    file_path,
    ground_truth,
    members_for,
    render_function,
    simulate,
    write_repo,
)
from fairshare_ml.benchmark.sim_config import (
    PROFILES,
    SECONDS_PER_WEEK,
    START_EPOCH,
    WEEKS,
)
from fairshare_ml.cleaning.features import extract_features, read_complexity
from fairshare_ml.cleaning.read_commits import read_commits
from fairshare_ml.inference import analyze_repository

ALL = list(PROFILES)
SEEDS = [0, 1, 2, 3, 4]


def week_of(commit: Commit) -> int:
    """Project week (0-based) in which a commit was made."""
    return (commit.when - START_EPOCH) // SECONDS_PER_WEEK


def final_files(sim: Simulation) -> dict:
    """The files that should exist at the end, built by replaying every commit."""
    state = {}
    for commit in sim.commits:
        for path, text in commit.changes.items():
            if text is None:
                state.pop(path, None)
            else:
                state[path] = text
    return state


def by_profile(sim: Simulation) -> dict:
    """Ground-truth rows keyed by profile name (use teams with distinct profiles)."""
    return {row["profile"]: row for row in ground_truth(sim)}


def spearman(a: list, b: list) -> float:
    """Rank correlation between two lists of numbers."""
    return pd.Series(a).rank().corr(pd.Series(b).rank())


class TestRenderFunction:
    """render_function() writes code whose complexity is known by construction."""

    def test_code_function(self):
        """Complexity 3 means two 'if' branches."""
        text = render_function(Func(7, "code", 0, 0, 3))
        assert text == (
            "def fn_7(x):\n    total = 0\n    if x > 7:\n        total += 1\n"
            "    if x > 8:\n        total += 2\n    return total\n"
        )

    def test_complexity_one_has_no_branch(self):
        """Complexity 1 is a straight-line function."""
        assert render_function(Func(0, "code", 0, 0, 1)) == "def fn_0(x):\n    total = 0\n    return total\n"

    def test_gaming_changes_alter_text_but_not_branches(self):
        """Trailing spaces, comment lines and a renamed variable change the text only."""
        base = Func(2, "code", 0, 0, 2)
        padded = Func(2, "code", 0, 0, 2, padded=True)
        commented = Func(2, "code", 0, 0, 2, comments=2)
        renamed = Func(2, "code", 0, 0, 2, var="acc")
        assert render_function(padded).splitlines()[0] == "def fn_2(x):  "
        assert render_function(commented).count("# padding") == 2
        assert "acc" in render_function(renamed) and "total" not in render_function(renamed)
        for variant in (padded, commented, renamed):
            assert render_function(variant).count("if x >") == render_function(base).count("if x >")

    def test_test_function_calls_its_target(self):
        """A test function asserts on the function it targets."""
        text = render_function(Func(5, "test", 0, 0, 1, target=3))
        assert text == "def test_fn_5():\n    assert fn_3(0) >= 0\n"

    def test_file_paths(self):
        """Code, test and doc files live in src/, tests/ and docs/."""
        assert file_path("code", 2) == "src/mod_2.py"
        assert file_path("test", 2) == "tests/test_mod_2.py"
        assert file_path("doc", 0) == "docs/guide.md"


class TestSimulate:
    """simulate() builds a reproducible team history."""

    def test_same_seed_gives_the_same_simulation(self):
        """The same profiles and seed always give identical results."""
        assert simulate(ALL, 7) == simulate(ALL, 7)

    def test_different_seeds_differ(self):
        """A different seed gives a different history."""
        assert simulate(ALL, 7).commits != simulate(ALL, 8).commits

    def test_people_have_distinct_names_and_emails(self):
        """Each person gets their own name and email."""
        people = simulate(ALL, 1).people
        assert [p.email for p in people] == [f"person{i}@sim.test" for i in range(len(ALL))]
        assert len({p.name for p in people}) == len(ALL)

    def test_commits_are_in_time_order_inside_the_project(self):
        """Commit times never go backwards and stay inside the 12 project weeks."""
        whens = [c.when for c in simulate(ALL, 2).commits]
        assert whens == sorted(whens)
        assert START_EPOCH <= whens[0] and whens[-1] < START_EPOCH + WEEKS * SECONDS_PER_WEEK

    def test_fewer_weeks(self):
        """With weeks=4 nothing happens after week 3."""
        sim = simulate(ALL, 2, weeks=4)
        assert all(week_of(c) < 4 for c in sim.commits)

    def test_every_commit_changes_a_file(self):
        """No commit is empty."""
        assert all(c.changes for c in simulate(ALL, 3).commits)

    @pytest.mark.parametrize("names, kwargs, message", [
        ([], {}, "at least one"),
        (["nobody"], {}, "unknown profile"),
        (["steady"], {"weeks": 0}, "weeks"),
        (["steady"] * 27, {}, "at most 26"),
    ])
    def test_bad_input_raises(self, names, kwargs, message):
        """Bad profile lists or week counts give a clear ValueError."""
        with pytest.raises(ValueError, match=message):
            simulate(names, 1, **kwargs)


class TestProfiles:
    """Each profile behaves as described in the project plan."""

    @pytest.mark.parametrize("seed", SEEDS)
    def test_late_profiles_stay_quiet_early(self, seed):
        """Free-rider starts in week 8, late starter in week 7, tester in week 1."""
        sim = simulate(ALL, seed)
        first_week = {"free_rider": 8, "late_starter": 7, "tester": 1}
        for commit in sim.commits:
            name = sim.people[commit.author].profile_name
            assert week_of(commit) >= first_week.get(name, 0)

    @pytest.mark.parametrize("seed", SEEDS)
    def test_gamer_commits_a_lot_for_little_effort(self, seed):
        """The gamer makes over twice the commits of a steady member for less real effort."""
        rows = by_profile(simulate(["steady", "gamer"], seed))
        assert rows["gamer"]["commits"] > 2 * rows["steady"]["commits"]
        assert rows["gamer"]["git_effort"] < rows["steady"]["git_effort"]

    @pytest.mark.parametrize("seed", SEEDS)
    def test_heavy_lifter_does_more_than_steady(self, seed):
        """The heavy lifter's effort exceeds a steady member's."""
        rows = by_profile(simulate(["steady", "heavy_lifter"], seed))
        assert rows["heavy_lifter"]["git_effort"] > rows["steady"]["git_effort"]

    @pytest.mark.parametrize("seed", SEEDS)
    def test_tester_mostly_writes_tests(self, seed):
        """The tester's effort is mostly tests."""
        row = by_profile(simulate(["steady", "tester"], seed))["tester"]
        assert row["test"] > row["code"]

    @pytest.mark.parametrize("seed", SEEDS)
    def test_reviewer_reviews_the_most(self, seed):
        """The reviewer has more reviews than anyone else and little git effort."""
        rows = by_profile(simulate(["steady", "reviewer", "tester", "heavy_lifter"], seed))
        assert all(rows["reviewer"]["review"] > row["review"] for name, row in rows.items() if name != "reviewer")
        assert rows["reviewer"]["git_effort"] < rows["heavy_lifter"]["git_effort"]

    @pytest.mark.parametrize("seed", SEEDS)
    def test_reviews_are_consistent(self, seed):
        """Nobody reviews themselves, reviews point at real commits, reviewers were active."""
        sim = simulate(ALL, seed)
        for review in sim.reviews:
            commit = sim.commits[review["commit"]]
            reviewer = sim.people[review["reviewer"]].profile
            assert review["reviewer"] != review["author"] == commit.author
            assert reviewer.first_week <= review["week"] == week_of(commit) <= reviewer.last_week


@pytest.fixture
def written(tmp_path):
    """A simulated team written as a real git repository: (simulation, repo path)."""
    sim = simulate(ALL, 3)
    return sim, write_repo(sim, tmp_path / "repo")


def git_output(repo, *args) -> str:
    """Text printed by a git command run in `repo`."""
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout.decode("utf-8")


class TestWriteRepo:
    """write_repo() produces a real repository that matches the simulation exactly."""

    def test_history_matches(self, written):
        """Same number of commits, same authors, same times."""
        sim, repo = written
        commits = read_commits(str(repo))
        assert len(commits) == len(sim.commits)
        assert [c["author_email"] for c in commits] == [sim.people[c.author].email for c in sim.commits]
        assert [int(c["author_date"].timestamp()) for c in commits] == [c.when for c in sim.commits]

    def test_final_files_match(self, written):
        """The files at HEAD are exactly the simulated final state."""
        sim, repo = written
        expected = final_files(sim)
        assert set(git_output(repo, "ls-tree", "-r", "--name-only", "HEAD").split()) == set(expected)
        for path, text in expected.items():
            assert git_output(repo, "show", f"HEAD:{path}") == text

    def test_declared_complexity_matches_what_lizard_measures(self, written):
        """For every file, the complexity changes add up to the declared complexity of its alive functions."""
        sim, repo = written
        expected = {}
        for func in sim.functions:
            path = file_path(func.kind, func.module)
            expected.setdefault(path, 0)
            expected[path] += func.complexity if func.alive else 0
        measured = {}
        for row in read_complexity(str(repo)):
            measured[row["path"]] = measured.get(row["path"], 0) + row["complexity_delta"]
        for path, total in measured.items():
            if path.endswith(".py"):
                assert total == expected.get(path, 0), path

    def test_formatting_commits_are_found_as_whitespace_only(self, written):
        """Every 'Format code' commit is flagged no_op by the hygiene filter, and no other is."""
        sim, repo = written
        flags = extract_features(str(repo))["flag"]
        assert int((flags == "no_op").sum()) == sum(c.message == "Format code" for c in sim.commits)


class TestGroundTruth:
    """ground_truth() applies the effort rule from sim_config."""

    @staticmethod
    def tiny() -> Simulation:
        """Two people with a hand-built history and known effort."""
        profile = PROFILES["steady"]
        people = [Person(0, "Person A", "a@x", "steady", profile), Person(1, "Person B", "b@x", "steady", profile)]
        functions = [
            Func(0, "code", 0, 0, 3),
            Func(1, "code", 0, 1, 2),
            Func(2, "code", 0, 0, 5, alive=False),
            Func(3, "test", 0, 1, 1, target=0),
        ]
        commits = [Commit(0, 1, "m", {"a": "x"}), Commit(0, 2, "m", {"a": "y"}), Commit(1, 3, "m", {"b": "z"})]
        return Simulation(people, commits, [{"reviewer": 1, "author": 0, "commit": 0, "week": 0}], functions, [(0, 0)])

    def test_effort_per_person(self):
        """Dead functions earn nothing; code counts complexity, tests 1, a doc section 0.5, a review 1."""
        a, b = ground_truth(self.tiny())
        assert (a["code"], a["test"], a["doc"], a["review"]) == (3.0, 0.0, 0.5, 0.0)
        assert (b["code"], b["test"], b["doc"], b["review"]) == (2.0, 1.0, 0.0, 1.0)
        assert (a["commits"], b["commits"]) == (2, 1)

    def test_shares(self):
        """git_share ignores reviews; total_share includes them."""
        a, b = ground_truth(self.tiny())
        assert a["git_share"] == pytest.approx(3.5 / 6.5)
        assert b["git_share"] == pytest.approx(3.0 / 6.5)
        assert a["total_share"] == pytest.approx(3.5 / 7.5)
        assert b["total_share"] == pytest.approx(4.0 / 7.5)

    def test_no_work_gives_zero_shares(self):
        """With no work at all every share is 0.0, not NaN."""
        sim = self.tiny()
        sim.functions, sim.sections, sim.reviews = [], [], []
        assert all(row["git_share"] == 0.0 and row["total_share"] == 0.0 for row in ground_truth(sim))

    @pytest.mark.parametrize("seed", SEEDS)
    def test_shares_add_up_to_one(self, seed):
        """Both kinds of share add up to 1.0 on a simulated team."""
        rows = ground_truth(simulate(ALL, seed))
        assert sum(r["git_share"] for r in rows) == pytest.approx(1.0)
        assert sum(r["total_share"] for r in rows) == pytest.approx(1.0)

    def test_members_for_matches_the_request_format(self):
        """One member per person, with the person's email."""
        sim = simulate(["steady", "gamer"], 1)
        assert members_for(sim) == [
            {"member_id": "m_0", "emails": ["person0@sim.test"]},
            {"member_id": "m_1", "emails": ["person1@sim.test"]},
        ]


class TestAgainstLite:
    """A first look at how FairShare-Lite compares with the ground truth."""

    @pytest.mark.parametrize("seed", [1, 2, 3])
    def test_lite_tracks_the_truth_when_nobody_games(self, tmp_path, seed):
        """Without gamers, Lite ranks everyone correctly and is within 0.1 of the true share."""
        sim = simulate(["steady", "heavy_lifter", "free_rider", "tester", "late_starter"], seed)
        repo = write_repo(sim, tmp_path / "repo")
        response = analyze_repository({"team_id": "t", "repo_path": str(repo), "members": members_for(sim)})
        lite = [m["share"] for m in response["members"]]
        truth = [row["git_share"] for row in ground_truth(sim)]
        assert spearman(lite, truth) >= 0.9
        assert max(abs(a - b) for a, b in zip(lite, truth)) <= 0.1
