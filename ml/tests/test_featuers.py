# tests/test_features.py
# FairShare - Milestone 13
# Tests for the feature extractor. Path rules and build_features() use small
# hand-made tables; the rest use a real git repo with hand-checkable numbers.
#
# Run:  python -m pytest tests/test_features.py -v

import os
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from fairshare_ml.cleaning.features import (
    FEATURE_COLUMNS,
    build_features,
    extract_features,
    file_kind,
    is_doc_path,
    is_test_path,
    read_complexity,
    read_survival,
)

ALICE = "Alice <alice@uni.edu>"
BOB = "Bob <bob@uni.edu>"
CARA = "Cara <cara@uni.edu>"
DAN = "Dan <dan@uni.edu>"


# ---------------------------------------------------------------------------
# Path rules
# ---------------------------------------------------------------------------

class TestPathKinds:
    """The kind of a file is decided from its path alone."""

    @pytest.mark.parametrize("path", [
        "tests/test_app.py", "src/test/java/AppTest.java", "test_app.py",
        "app_test.py", "web/app.spec.ts", "web/app.test.js", "lib/a_test.dart",
        "__tests__/a.js", "tests\\test_app.py",
    ])
    def test_test_paths(self, path):
        """Files in test folders or named like tests are test files."""
        assert is_test_path(path)

    @pytest.mark.parametrize("path", [
        "src/app.py", "src/Latest.java", "src/contest.py", "protest/a.py", "README.md",
    ])
    def test_non_test_paths(self, path):
        """Look-alike names ('Latest.java', 'contest.py') are not tests."""
        assert not is_test_path(path)

    @pytest.mark.parametrize("path", ["README.md", "docs/guide.txt", "doc/a.png", "notes/ideas.RST"])
    def test_doc_paths(self, path):
        """Markdown, reStructuredText and anything under docs/ are docs."""
        assert is_doc_path(path)

    @pytest.mark.parametrize("path", ["requirements.txt", "src/app.py", "docsify/app.js"])
    def test_non_doc_paths(self, path):
        """requirements.txt and folders merely starting with 'docs' are not docs."""
        assert not is_doc_path(path)

    @pytest.mark.parametrize("path, kind", [
        ("package-lock.json", "generated"),
        ("src/app.py", "code"),
        ("tests/test_app.py", "test"),
        ("README.md", "doc"),
        ("tests/README.md", "doc"),       # docs win over tests
        ("node_modules/x/tests/a.js", "generated"),   # generated wins over everything
    ])
    def test_file_kind(self, path, kind):
        """file_kind() picks generated, then doc, then test, then code."""
        assert file_kind(path) == kind


# ---------------------------------------------------------------------------
# build_features on hand-made tables
# ---------------------------------------------------------------------------

def _tables():
    """Two commits: h1 adds code+test+a lock file, h2 adds docs only."""
    flagged = pd.DataFrame({
        "hash": ["h1", "h2"],
        "author_email": ["a@x.com", "b@x.com"],
        "flag": ["substantive", "substantive"],
    })
    file_changes = pd.DataFrame([
        ("h1", "src/app.py", 10), ("h1", "tests/test_app.py", 5),
        ("h1", "package-lock.json", 999), ("h2", "README.md", 4),
    ], columns=["hash", "path", "lines_added"])
    complexity = pd.DataFrame([
        ("h1", "src/app.py", 3), ("h1", "tests/test_app.py", 7),
    ], columns=["hash", "path", "complexity_delta"])
    survival = pd.DataFrame([
        ("h1", "code", 5), ("h1", "test", 5), ("h2", "doc", 4),
    ], columns=["hash", "kind", "surviving_lines"])
    return flagged, file_changes, complexity, survival


class TestBuildFeatures:
    """build_features() joins lines, complexity and survival per commit."""

    def test_lines_by_kind_leave_out_generated_files(self):
        """The 999-line lock file is not counted anywhere."""
        result = build_features(*_tables()).set_index("hash")
        assert result.loc["h1", ["code_lines", "test_lines", "doc_lines"]].tolist() == [10, 5, 0]
        assert result.loc["h2", ["code_lines", "test_lines", "doc_lines"]].tolist() == [0, 0, 4]

    def test_only_code_files_count_for_complexity(self):
        """The test file's complexity (7) is ignored; the code file's (3) is kept."""
        result = build_features(*_tables()).set_index("hash")
        assert result.loc["h1", "complexity_delta"] == 3
        assert result.loc["h2", "complexity_delta"] == 0

    def test_survival_is_surviving_over_added(self):
        """h1: 10 of 15 lines survive. h2: 4 of 4."""
        result = build_features(*_tables()).set_index("hash")
        assert result.loc["h1", "survival"] == pytest.approx(10 / 15)
        assert result.loc["h2", "survival"] == 1.0

    def test_survival_is_zero_when_nothing_was_added(self):
        """A commit that added no lines has survival 0.0, not NaN."""
        flagged, files, complexity, survival = _tables()
        result = build_features(flagged, files.iloc[0:0], complexity, survival.iloc[0:0])
        assert (result["survival"] == 0.0).all()

    def test_survival_never_exceeds_one(self):
        """Even if blame credits more lines than were added, survival is capped at 1."""
        flagged, files, complexity, survival = _tables()
        survival.loc[survival["hash"] == "h2", "surviving_lines"] = 40
        assert build_features(flagged, files, complexity, survival).set_index("hash").loc["h2", "survival"] == 1.0

    def test_columns_and_row_count(self):
        """One row per commit, columns in FEATURE_COLUMNS order."""
        result = build_features(*_tables())
        assert list(result.columns) == FEATURE_COLUMNS
        assert len(result) == 2

    def test_inputs_are_not_modified(self):
        """The caller's four tables are left untouched."""
        tables = _tables()
        copies = [t.copy() for t in tables]
        build_features(*tables)
        for table, copy_ in zip(tables, copies):
            pd.testing.assert_frame_equal(table, copy_)


# ---------------------------------------------------------------------------
# Real git repositories
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: str) -> None:
    """Run  git <args>  inside cwd. Line-ending conversion is switched off."""
    subprocess.run(
        ["git"] + args, cwd=cwd, check=True, capture_output=True,
        env={**os.environ, "GIT_CONFIG_COUNT": "1",
             "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "false"},
    )


def _init_repo(path: Path) -> Path:
    """Create an empty git repository at `path`."""
    path.mkdir()
    for args in (["init"], ["config", "user.email", "ci@test.com"], ["config", "user.name", "CI"]):
        _git(args, cwd=str(path))
    return path


def _commit(repo: Path, author: str, message: str, files: dict) -> None:
    """Write `files` ({path: text or bytes}) and commit them as `author`."""
    for name, content in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8", newline="\n")
    _git(["add", "-A"], cwd=str(repo))
    _git(["commit", f"--author={author}", "-m", message], cwd=str(repo))


F_V1 = "def f(x):\n    return x\n"
CALC_V2 = F_V1 + "\ndef g(items):\n    for i in items:\n        print(i)\n"
CALC_V3 = CALC_V2.replace("    return x\n", "    return x + 1\n")
CALC_V4 = CALC_V3.replace("def f(x):\n", "def f(x):   \n")      # trailing spaces only


@pytest.fixture
def history_repo(tmp_path: Path) -> Path:
    """
    A repo whose features can be worked out by hand.

      c1 Alice  calc.py: f() with 2 lines                       complexity +1
      c2 Bob    appends a blank line and g() with a loop (4 lines)  complexity +2
      c3 Cara   rewrites the 'return x' line (1 line replaced)  complexity 0
      c4 Dan    adds trailing spaces to line 1 (whitespace only)
      c5 Alice  adds tests/test_calc.py (3 lines)
      c6 Alice  adds README.md (2 lines), package-lock.json (50 lines), a binary logo
    """
    repo = _init_repo(tmp_path / "history")
    _commit(repo, ALICE, "c1", {"calc.py": F_V1})
    _commit(repo, BOB, "c2", {"calc.py": CALC_V2})
    _commit(repo, CARA, "c3", {"calc.py": CALC_V3})
    _commit(repo, DAN, "c4", {"calc.py": CALC_V4})
    _commit(repo, ALICE, "c5", {"tests/test_calc.py": "from calc import f\ndef test_f():\n    assert f(1) == 2\n"})
    _commit(repo, ALICE, "c6", {
        "README.md": "# Calc\nA tiny calculator.\n",
        "package-lock.json": "{}\n" * 50,
        "logo.png": b"\x89PNG\r\n\x1a\n\x00\x00\x01\n\x00\x02\n",
    })
    return repo


@pytest.fixture
def features(history_repo) -> pd.DataFrame:
    """The extracted features of history_repo, one row per commit c1..c6."""
    return extract_features(str(history_repo)).reset_index(drop=True)


class TestExtractFeatures:
    """extract_features() on a repo with known numbers."""

    def test_one_row_per_commit_in_order(self, features):
        """Six commits, oldest first, with the expected columns."""
        assert len(features) == 6
        assert list(features.columns) == FEATURE_COLUMNS
        assert list(features["author_email"]) == [
            "alice@uni.edu", "bob@uni.edu", "cara@uni.edu",
            "dan@uni.edu", "alice@uni.edu", "alice@uni.edu",
        ]

    def test_lines_added_by_kind(self, features):
        """c1 2 code lines, c2 4, c3 1, c4 1; c5 3 test lines; c6 2 doc lines."""
        assert list(features["code_lines"]) == [2, 4, 1, 1, 0, 0]
        assert list(features["test_lines"]) == [0, 0, 0, 0, 3, 0]
        assert list(features["doc_lines"]) == [0, 0, 0, 0, 0, 2]

    def test_complexity_delta(self, features):
        """f() adds 1; g() with a loop adds 2; edits and tests add 0 (code files only)."""
        assert list(features["complexity_delta"]) == [1, 2, 0, 0, 0, 0]

    def test_surviving_lines(self, features):
        """c1 keeps 1 of its 2 lines; c2 keeps all 4; c3 keeps its 1; c4 keeps 0."""
        assert list(features["surviving_code"]) == [1, 4, 1, 0, 0, 0]
        assert list(features["surviving_test"]) == [0, 0, 0, 0, 3, 0]
        assert list(features["surviving_doc"]) == [0, 0, 0, 0, 0, 2]

    def test_survival_values(self, features):
        """Half of c1 survives, a whitespace-only edit (c4) survives 0%, the rest 100%."""
        assert list(features["survival"]) == pytest.approx([0.5, 1.0, 1.0, 0.0, 1.0, 1.0])

    def test_whitespace_edit_does_not_take_over_the_line(self, features):
        """Dan's trailing spaces leave line 1 owned by Alice's c1, not by c4."""
        assert features.loc[0, "surviving_code"] == 1
        assert features.loc[3, "surviving_code"] == 0

    def test_generated_and_binary_files_are_ignored(self, features):
        """c6 counts only its 2 README lines: the 50-line lock file and the binary add nothing."""
        row = features.loc[5]
        assert row["code_lines"] + row["test_lines"] + row["doc_lines"] == 2
        assert row["surviving_code"] + row["surviving_test"] + row["surviving_doc"] == 2

    def test_empty_repository_gives_empty_table(self, tmp_path):
        """No commits: an empty table with the right columns, and no crash."""
        result = extract_features(str(_init_repo(tmp_path / "empty")))
        assert result.empty
        assert list(result.columns) == FEATURE_COLUMNS


class TestReaders:
    """read_complexity() and read_survival() on their own."""

    def test_removing_code_gives_negative_complexity(self, tmp_path):
        """Deleting a function with complexity 1 gives a delta of -1."""
        repo = _init_repo(tmp_path / "gone")
        _commit(repo, ALICE, "add", {"calc.py": F_V1})
        _git(["rm", "calc.py"], cwd=str(repo))
        _git(["commit", f"--author={BOB}", "-m", "remove"], cwd=str(repo))
        assert [r["complexity_delta"] for r in read_complexity(str(repo))] == [1, -1]

    def test_complexity_rows_use_forward_slashes(self, history_repo):
        """Paths use '/' on every operating system."""
        paths = {r["path"] for r in read_complexity(str(history_repo))}
        assert "tests/test_calc.py" in paths

    def test_survival_table_columns(self, history_repo):
        """read_survival() returns hash, kind and surviving_lines."""
        table = read_survival(str(history_repo))
        assert list(table.columns) == ["hash", "kind", "surviving_lines"]
        assert set(table["kind"]) == {"code", "test", "doc"}

    def test_bad_paths_raise(self, tmp_path):
        """A missing folder raises FileNotFoundError; a non-repo raises ValueError."""
        with pytest.raises(FileNotFoundError):
            read_complexity(str(tmp_path / "nope"))
        with pytest.raises(FileNotFoundError):
            read_survival(str(tmp_path / "nope"))
        with pytest.raises(ValueError, match="Not a git repository"):
            read_survival(str(tmp_path))