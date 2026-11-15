# inference.py
# FairShare - Milestones 12 and 14
# The one function the backend calls: analyze_repository(request) -> dict.
# The scoring itself lives in scoring/lite.py (FairShare-Lite).

from datetime import date

import pandas as pd

from fairshare_ml.cleaning.features import extract_features
from fairshare_ml.cleaning.read_commits import read_commits
from fairshare_ml.scoring.flags import split_commit_members
from fairshare_ml.scoring.lite import (
    MODEL_VERSION,
    commit_points,
    evidence_reason,
    score_members,
)

MAX_EVIDENCE = 5               # evidence items per member
FACETS = ("code", "review", "testing", "docs", "coordination")
POINT_COLUMNS = ["code_points", "test_points", "doc_points"]


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


def _evidence(rows: pd.DataFrame) -> list[dict]:
    """The member's biggest commits (by points), each with a plain reason."""
    top = rows[rows["points"] > 0].sort_values("points", ascending=False, kind="stable")
    return [
        {"commit": row["hash"][:7], "reason": evidence_reason(row)}
        for _, row in top.head(MAX_EVIDENCE).iterrows()
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
    is not enough data (fewer than 2 counted commits): then every share and
    facet is 0.0 and 'warnings' contains 'insufficient_data'.
    'unmapped_authors' is added when a commit author is not in the member
    list. Member flags (shown openly, they do not change the score):
    'generated_files' (committed lock files or build output), 'whitespace_only'
    (a commit that only changed whitespace) and 'split_commits' (a burst of
    tiny commits).

    Raises ValueError for a malformed request, and the errors of
    read_commits() (FileNotFoundError, NotADirectoryError, ValueError) for a
    bad repo_path.
    """
    _check_request(request)
    members = request["members"]
    member_ids = [member["member_id"] for member in members]
    email_to_member = {
        _normalise(email): member["member_id"]
        for member in members
        for email in member["emails"]
    }

    commits = read_commits(request["repo_path"])
    scored = commit_points(extract_features(request["repo_path"]))
    scored["member_id"] = scored["author_email"].map(_normalise).map(email_to_member)

    # Which commits count, and did anyone real appear who is not a member?
    real_people = ~scored["flag"].isin(["bot", "merge"])
    has_unmapped = bool((real_people & scored["member_id"].isna()).any())
    counted = scored[(scored["flag"] == "substantive") & scored["member_id"].notna()]
    dates = {c["hash"]: c["author_date"] for c in commits}
    flagged_by = {
        "generated_files": set(scored.loc[scored["flag"] == "generated", "member_id"].dropna()),
        "whitespace_only": set(scored.loc[scored["flag"] == "no_op", "member_id"].dropna()),
        "split_commits": split_commit_members(
            counted.assign(author_date=counted["hash"].map(dates))
        ),
    }
    points = counted.groupby("member_id")[POINT_COLUMNS].sum().reindex(member_ids, fill_value=0.0)
    scores = score_members(points)
    insufficient = len(counted) < 2 or points.to_numpy().sum() == 0
    if insufficient:
        scores = scores * 0.0

    reports = [
        {
            "member_id": member_id,
            "share": float(scores.loc[member_id, "share"]),
            "facets": {name: float(scores.loc[member_id, name]) for name in FACETS},
            "flags": sorted(name for name, who in flagged_by.items() if member_id in who),
            "evidence": _evidence(counted[counted["member_id"] == member_id]),
        }
        for member_id in member_ids
    ]

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