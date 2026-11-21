from dataclasses import dataclass
from datetime import datetime, timezone

WEEKS = 12
SECONDS_PER_WEEK = 7 * 24 * 3600
START_EPOCH = int(datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc).timestamp())

N_MODULES = 5
CORE_MODULES = (0, 1)
RENAMES = ("total", "acc", "res", "out", "val")

EFFORT_WEIGHTS = {
    "code_per_complexity": 1.0,
    "test_function": 1.0,
    "doc_section": 0.5,
    "review": 1.0,
}


@dataclass(frozen=True)
class Profile:
    """How one kind of team member behaves over the project."""

    first_week: int
    last_week: int
    commits_per_week: int
    burst: int
    complexity: tuple
    functions_per_commit: tuple
    mix: tuple
    review_rate: float
    core_bias: float


PROFILES = {
    "steady": Profile(0, 11, 3, 1, (1, 4), (1, 2),
                      (("code", 70), ("test", 15), ("doc", 10), ("delete", 5)), 0.25, 0.4),
    "heavy_lifter": Profile(0, 11, 4, 1, (2, 5), (1, 3),
                            (("code", 90), ("test", 5), ("delete", 5)), 0.15, 0.85),
    "free_rider": Profile(8, 11, 1, 1, (1, 2), (1, 1),
                          (("code", 55), ("doc", 45)), 0.0, 0.2),
    "gamer": Profile(0, 11, 3, 4, (1, 2), (1, 1),
                     (("code", 10), ("whitespace", 30), ("comment", 30), ("rename", 30)), 0.0, 0.4),
    "reviewer": Profile(0, 11, 1, 1, (1, 3), (1, 1),
                        (("code", 60), ("doc", 40)), 0.85, 0.4),
    "tester": Profile(1, 11, 3, 1, (1, 2), (1, 2),
                      (("test", 80), ("code", 10), ("doc", 10)), 0.25, 0.4),
    "late_starter": Profile(7, 11, 6, 1, (2, 5), (1, 3),
                            (("code", 75), ("test", 15), ("doc", 10)), 0.2, 0.4),
}
