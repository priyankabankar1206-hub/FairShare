# inference.py
# FairShare - Milestone 12 (the stub)
# The one function the backend calls: analyze_repository(request) -> dict.
#
# This is a STUB. The output has the exact shape of the contract, and the
# shares are real but simple: lines added, after the hygiene filter. Later,
# FairShare-Lite replaces the scoring inside; the shape never changes.

from datetime import date

import pandas as pd

from fairshare_ml.cleaning.hygiene import flag_commits
from fairshare_ml.cleaning.read_commits import (
    FILE_CHANGE_COLUMNS,
    read_commits,
    read_file_changes,
)

MODEL_VERSION = "stub-0.1"     # backend stores this with every score
MAX_EVIDENCE = 5               # evidence items per member
FACETS = ("code", "review", "testing", "docs", "coordination")


def gini_coefficient(shares: list[float]) -> float:
    """
    How unevenly work is spread: 0.0 = perfectly even, higher = more
    concentrated in few people. Teams of one, or all-zero shares, give 0.0.

    Example: [0.5, 0.5] -> 0.0;  [1.0, 0.0] -> 0.5.
    """
    total = sum(shares)
    if len(shares) < 2 or total == 0:
        return 0.0
    spread = sum(abs(a - b) for a in shares for b in shares)
    return spread / (2 * len(shares) * total)


def imbalance_label(gini: float) -> str:
    """
    Turn a Gini value into 'balanced', 'watch' or 'at risk'.
    The cut-offs (0.25 and 0.40) are the placeholders from the project
    documentation and still need calibrating on real teams.
    """
    if gini < 0.25:
        return "balanced"
    if gini <= 0.40:
        return "watch"
    return "at risk"


def _normalise(email: object) -> str:
    """Make an email comparable: text, no spaces, lower-case."""
    return str(email).strip().lower()


def _check_request(request: dict) -> None:
    """Raise ValueError with a clear message if the request is malformed."""
    if not isinstance(request, dict):
        raise ValueError("request must be a dict")
    for key in ("team_id", "repo_path"):
        if not isinstance(request.get(key), str) or not request[key].strip():
            raise ValueError(f"request needs a non-empty text field '{key}'")

    members = request.get("members")
    if not isinstance(members, list) or not members:
        raise ValueError("request needs a non-empty list 'members'")

    seen_ids: set[str] = set()
    seen_emails: set[str] = set()
    for member in members:
        if (
            not isinstance(member, dict)
            or not isinstance(member.get("member_id"), str)
            or not isinstance(member.get("emails"), list)
        ):
            raise ValueError("each member needs a 'member_id' and a list 'emails'")
        if member["member_id"] in seen_ids:
            raise ValueError(f"duplicate member_id: {member['member_id']}")
        seen_ids.add(member["member_id"])
        for email in member["emails"]:
            # The error does not repeat the email: it is personal data.
            if _normalise(email) in seen_emails:
                raise ValueError("an email is listed for more than one member")
            seen_emails.add(_normalise(email))


def _counted_commits(
    commits: list[dict], file_changes: list[dict], email_to_member: dict
) -> tuple[pd.DataFrame, bool]:
    """
    Pick the commits that count as work: flagged 'substantive' and written by
    a listed member. Also report whether any real person (not a bot, not a
    merge) was missing from the member list.
    """
    if not commits:
        return pd.DataFrame(columns=["hash", "member_id", "clean_insertions",
                                     "clean_files"]), False

    flagged = flag_commits(
        pd.DataFrame(commits),
        pd.DataFrame(file_changes, columns=FILE_CHANGE_COLUMNS),
    )
    flagged["member_id"] = flagged["author_email"].map(_normalise).map(email_to_member)

    real_people = ~flagged["flag"].isin(["bot", "merge"])
    has_unmapped = bool((real_people & flagged["member_id"].isna()).any())
    counted = flagged[(flagged["flag"] == "substantive") & flagged["member_id"].notna()]
    return counted, has_unmapped


def _count(n: int, word: str) -> str:
    """'1 line', '3 lines'."""
    return f"{int(n)} {word}" + ("" if n == 1 else "s")


def _evidence(rows: pd.DataFrame) -> list[dict]:
    """The member's biggest commits (by lines added), each with a plain reason."""
    top = rows.sort_values("clean_insertions", ascending=False, kind="stable")
    top = top.head(MAX_EVIDENCE)
    return [
        {
            "commit": sha[:7],
            "reason": f"Added {_count(lines, 'line')} in {_count(files, 'file')}",
        }
        for sha, lines, files in zip(top["hash"], top["clean_insertions"], top["clean_files"])
    ]


def analyze_repository(request: dict) -> dict:
    """
    Score every team member's contribution in a local git repository.

    request (a dict matching the backend's AIMLAnalysisRequest):
      team_id    - text, copied into the response
      repo_path  - folder of the cloned repository
      members    - [{"member_id": "m_1", "emails": ["a@uni.edu", ...]}, ...]
                   every email a member has committed with, bots left out
    Other fields (repo_url, head_commit_sha, week_number, extra_parameters)
    are accepted and ignored for now.

    Returns a dict matching the backend's AIMLAnalysisResponse. Members come
    back in the order they were sent. Shares add up to 1.0, except when there
    is not enough data (fewer than 2 counted commits): then every share is
    0.0 and 'warnings' contains 'insufficient_data'. 'unmapped_authors' is
    added when a commit author is not in the member list.

    Raises ValueError for a malformed request, and the errors of
    read_commits() (FileNotFoundError, NotADirectoryError, ValueError) for a
    bad repo_path.
    """
    _check_request(request)
    members = request["members"]
    email_to_member = {
        _normalise(email): member["member_id"]
        for member in members
        for email in member["emails"]
    }

    commits = read_commits(request["repo_path"])
    file_changes = read_file_changes(request["repo_path"])
    counted, has_unmapped = _counted_commits(commits, file_changes, email_to_member)

    # Stub score: lines added (generated files excluded) per member.
    score_by_member = counted.groupby("member_id")["clean_insertions"].sum()
    total = int(score_by_member.sum())
    insufficient = len(counted) < 2 or total == 0

    reports = []
    for member in members:
        member_id = member["member_id"]
        score = int(score_by_member.get(member_id, 0))
        share = 0.0 if insufficient else score / total
        reports.append({
            "member_id": member_id,
            "share": share,
            # Stub: only the code facet is filled, and it equals the share.
            "facets": {**dict.fromkeys(FACETS, 0.0), "code": share},
            "flags": [],
            "evidence": _evidence(counted[counted["member_id"] == member_id]),
        })

    gini = gini_coefficient([report["share"] for report in reports])
    warnings = []
    if insufficient:
        warnings.append("insufficient_data")
    if has_unmapped:
        warnings.append("unmapped_authors")

    # as_of is the newest commit's date, so the same input gives the same output.
    as_of = (
        max(c["author_date"] for c in commits).date().isoformat()
        if commits else date.today().isoformat()
    )

    return {
        "team_id": request["team_id"],
        "model_version": MODEL_VERSION,
        "as_of": as_of,
        "members": reports,
        "imbalance": {"gini": gini, "label": imbalance_label(gini)},
        "warnings": warnings,
    }