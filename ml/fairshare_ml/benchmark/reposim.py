import random
import subprocess
from dataclasses import dataclass
from pathlib import Path

from fairshare_ml.benchmark.sim_config import (
    CORE_MODULES,
    EFFORT_WEIGHTS,
    N_MODULES,
    PROFILES,
    RENAMES,
    SECONDS_PER_WEEK,
    START_EPOCH,
    WEEKS,
    Profile,
)

REVIEWABLE = ("code", "test", "doc")
MESSAGES = {
    "code": "Add feature code",
    "test": "Add tests",
    "doc": "Update docs",
    "delete": "Remove unused code",
    "whitespace": "Format code",
    "comment": "Add comments",
    "rename": "Rename variables",
}


@dataclass
class Person:
    """One simulated team member."""

    index: int
    name: str
    email: str
    profile_name: str
    profile: Profile


@dataclass
class Func:
    """One function written by the simulation, with its known complexity."""

    fid: int
    kind: str
    module: int
    author: int
    complexity: int
    target: int = -1
    var: str = RENAMES[0]
    padded: bool = False
    comments: int = 0
    alive: bool = True


@dataclass
class Commit:
    """One commit: who, when, and the new full text of every file it changes."""

    author: int
    when: int
    message: str
    changes: dict


@dataclass
class Simulation:
    """Everything RepoSim produced: people, history, reviews and what was written."""

    people: list
    commits: list
    reviews: list
    functions: list
    sections: list


def render_function(func: Func) -> str:
    """Source text of a function. A code function has cyclomatic complexity func.complexity."""
    if func.kind == "test":
        return f"def test_fn_{func.fid}():\n    assert fn_{func.target}(0) >= 0\n"
    lines = [f"def fn_{func.fid}(x):" + ("  " if func.padded else "")]
    lines += [f"    # padding {i}" for i in range(func.comments)]
    lines.append(f"    {func.var} = 0")
    for k in range(func.complexity - 1):
        lines += [f"    if x > {func.fid + k}:", f"        {func.var} += {k + 1}"]
    lines.append(f"    return {func.var}")
    return "\n".join(lines) + "\n"


def file_path(kind: str, module: int) -> str:
    """Path of the file that holds functions of this kind and module."""
    if kind == "doc":
        return "docs/guide.md"
    return f"src/mod_{module}.py" if kind == "code" else f"tests/test_mod_{module}.py"


class _Project:
    """The evolving project: functions, doc sections and the text of each file."""

    def __init__(self, rng: random.Random):
        """Start with an empty project."""
        self.rng = rng
        self.functions: list[Func] = []
        self.sections: list[tuple] = []
        self.files: dict[str, str] = {}

    def _text(self, kind: str, module: int) -> str:
        """Current text of one file, built from the alive functions or sections."""
        if kind == "doc":
            if not self.sections:
                return ""
            return "# Guide\n" + "".join(
                f"## Section {sid}\nFirst line {sid}.\nSecond line {sid}.\n"
                for sid, _ in self.sections
            )
        funcs = [f for f in self.functions if f.alive and f.kind == kind and f.module == module]
        return "\n".join(render_function(f) for f in funcs)

    def _changes(self, targets) -> dict:
        """New text for each (kind, module) file that really changed; None means deleted."""
        out = {}
        for kind, module in sorted(set(targets)):
            path = file_path(kind, module)
            text = self._text(kind, module)
            if text == self.files.get(path, ""):
                continue
            out[path] = text or None
            if text:
                self.files[path] = text
            else:
                self.files.pop(path, None)
        return out

    def _new_func(self, kind, module, author, complexity, target=-1) -> Func:
        """Create a function and remember it."""
        func = Func(len(self.functions), kind, module, author, complexity, target)
        self.functions.append(func)
        return func

    def _alive(self, kind=None, author=None) -> list:
        """Alive functions, optionally of one kind and/or one author."""
        return [
            f for f in self.functions
            if f.alive and (kind is None or f.kind == kind) and (author is None or f.author == author)
        ]

    def apply(self, kind: str, person: int, profile: Profile):
        """Do one kind of commit. Returns (message, changes), or None if it is not possible now."""
        rng = self.rng
        targets = []
        if kind == "code":
            module = rng.choice(CORE_MODULES) if rng.random() < profile.core_bias else rng.randrange(N_MODULES)
            for _ in range(rng.randint(*profile.functions_per_commit)):
                self._new_func("code", module, person, rng.randint(*profile.complexity))
            targets = [("code", module)]
        elif kind == "test":
            codes = self._alive("code")
            if not codes:
                return None
            for _ in range(rng.randint(*profile.functions_per_commit)):
                code = rng.choice(codes)
                self._new_func("test", code.module, person, 1, code.fid)
                targets.append(("test", code.module))
        elif kind == "doc":
            self.sections.append((len(self.sections), person))
            targets = [("doc", 0)]
        elif kind == "delete":
            own = self._alive(author=person)
            if not own:
                return None
            victim = rng.choice(own)
            victim.alive = False
            targets = [(victim.kind, victim.module)]
        else:
            codes = self._alive("code")
            if not codes:
                return None
            func = rng.choice(codes)
            if kind == "whitespace":
                func.padded = not func.padded
            elif kind == "comment":
                func.comments += 1
            else:
                func.var = RENAMES[(RENAMES.index(func.var) + 1) % len(RENAMES)]
            targets = [("code", func.module)]
        return MESSAGES[kind], self._changes(targets)


def simulate(profile_names: list, seed: int, weeks: int = WEEKS) -> Simulation:
    """
    Simulate a team project and return its full history and what was written.

    profile_names: one profile name per person (see sim_config.PROFILES).
    The same names and seed always give exactly the same simulation.
    """
    if not profile_names:
        raise ValueError("at least one profile is needed")
    if len(profile_names) > 26:
        raise ValueError("at most 26 people are supported")
    unknown = [name for name in profile_names if name not in PROFILES]
    if unknown:
        raise ValueError(f"unknown profile(s): {unknown}")
    if weeks < 1:
        raise ValueError("weeks must be at least 1")

    rng = random.Random(seed)
    people = [
        Person(i, f"Person {chr(65 + i)}", f"person{i}@sim.test", name, PROFILES[name])
        for i, name in enumerate(profile_names)
    ]

    events = []
    for person in people:
        p = person.profile
        for week in range(p.first_week, min(p.last_week, weeks - 1) + 1):
            for _ in range(rng.randint(max(0, p.commits_per_week - 1), p.commits_per_week + 1)):
                start = START_EPOCH + week * SECONDS_PER_WEEK + rng.randrange(SECONDS_PER_WEEK)
                for b in range(p.burst):
                    events.append((start + b * rng.randint(120, 480), person.index))
    events.sort()

    project = _Project(rng)
    commits, reviews = [], []
    for when, index in events:
        profile = people[index].profile
        kinds, weights = zip(*profile.mix)
        kind = rng.choices(kinds, weights)[0]
        result = project.apply(kind, index, profile)
        if result is None:
            kind = "code"
            result = project.apply("code", index, profile)
        message, changes = result
        if not changes:
            continue
        commits.append(Commit(index, when, message, changes))
        if kind in REVIEWABLE:
            week = (when - START_EPOCH) // SECONDS_PER_WEEK
            for other in people:
                p = other.profile
                if other.index != index and p.first_week <= week <= p.last_week and rng.random() < p.review_rate:
                    reviews.append({"reviewer": other.index, "author": index,
                                    "commit": len(commits) - 1, "week": week})

    return Simulation(people, commits, reviews, project.functions, project.sections)


def write_repo(sim: Simulation, path) -> Path:
    """Write the simulated history as a real git repository at `path` (which must not exist)."""
    path = Path(path)
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)

    stream = bytearray()
    for commit in sim.commits:
        person = sim.people[commit.author]
        ident = f"{person.name} <{person.email}> {commit.when} +0000"
        message = commit.message.encode("utf-8")
        stream += f"commit refs/heads/main\nauthor {ident}\ncommitter {ident}\ndata {len(message)}\n".encode()
        stream += message + b"\n"
        for file, text in commit.changes.items():
            if text is None:
                stream += f"D {file}\n".encode()
            else:
                data = text.encode("utf-8")
                stream += f"M 100644 inline {file}\ndata {len(data)}\n".encode() + data + b"\n"
        stream += b"\n"

    subprocess.run(["git", "-C", str(path), "fast-import", "--quiet"], input=bytes(stream), check=True)
    subprocess.run(["git", "-c", "core.autocrlf=false", "-C", str(path), "reset", "-q", "--hard", "main"], check=True)
    return path


def members_for(sim: Simulation) -> list[dict]:
    """The `members` list for analyze_repository: one member per simulated person."""
    return [{"member_id": f"m_{p.index}", "emails": [p.email]} for p in sim.people]


def _shares(values: list) -> list:
    """Each value divided by the total (all 0.0 if the total is 0)."""
    total = sum(values)
    return [v / total if total > 0 else 0.0 for v in values]


def ground_truth(sim: Simulation) -> list[dict]:
    """
    The true effort of each person under the rule in sim_config.EFFORT_WEIGHTS.

    Alive functions count once, for the person who first wrote them (their
    complexity for code, a fixed weight per test); each doc section and each
    review has a fixed weight. 'git_effort' is what a git history can show
    (code + test + doc); 'total_effort' adds reviews. 'git_share' and
    'total_share' are each person's part of the team total.
    """
    weights = EFFORT_WEIGHTS
    rows = [
        {"person": p.index, "profile": p.profile_name, "commits": 0,
         "code": 0.0, "test": 0.0, "doc": 0.0, "review": 0.0}
        for p in sim.people
    ]
    for commit in sim.commits:
        rows[commit.author]["commits"] += 1
    for func in sim.functions:
        if func.alive and func.kind == "code":
            rows[func.author]["code"] += func.complexity * weights["code_per_complexity"]
        elif func.alive:
            rows[func.author]["test"] += weights["test_function"]
    for _, author in sim.sections:
        rows[author]["doc"] += weights["doc_section"]
    for review in sim.reviews:
        rows[review["reviewer"]]["review"] += weights["review"]

    for row in rows:
        row["git_effort"] = row["code"] + row["test"] + row["doc"]
        row["total_effort"] = row["git_effort"] + row["review"]
    for key, share in (("git_effort", "git_share"), ("total_effort", "total_share")):
        for row, value in zip(rows, _shares([r[key] for r in rows])):
            row[share] = value
    return rows
