"""FairShare Research Anonymizer and Export Script (Section 7.4).

Requirements:
- Export only teams where every member has consented to research use (Section 7.2 & 7.4).
- Replace member identities and names with 'anonymised_id'.
- Remove raw personal emails and commit messages.
- Hash file paths using SHA-256 while strictly preserving file extensions.
- Keep research export separate from normal application operational data in data/research_export/.
- Respect retention policy: Do not invent a retention period; flag the instructor's decision if it is missing.
- Test that teams without complete consent are excluded.
"""

import sys
import os
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

# Ensure backend root is on Python path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.models.team import Team, TeamMember
from app.models.git_data import Identity, Commit, FileChange, PullRequest, Review, Issue
from app.models.analysis import Score, Evidence, Alert, Survey
from app.services.consent_service import get_consent_service
from app.services.storage import storage_manager


def hash_path(original_path: str, salt: str = "fairshare_research") -> str:
    """Hash a source file path while preserving the original file extension.

    Example: 'backend/app/auth/router.py' -> 'file_3d79f0a82e12.py'
    """
    path_obj = Path(original_path)
    extension = path_obj.suffix  # e.g., '.py', '.dart', '.ts'
    path_hash = hashlib.sha256(f"{salt}:{original_path}".encode("utf-8")).hexdigest()[:12]
    return f"file_{path_hash}{extension}"


def check_team_research_consent(db, team_id: str) -> Tuple[bool, List[str]]:
    """Verify that every member of the team has recorded consent.

    Returns (is_consented, missing_member_ids).
    """
    members = db.query(TeamMember).filter(TeamMember.team_id == team_id).all()
    if not members:
        return False, []

    unconsented = [m.id for m in members if m.consent_at is None]
    return len(unconsented) == 0, unconsented


def export_anonymised_team(
    db,
    team: Team,
    salt: str = "fairshare_export",
    retention_until: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Export and anonymize a single team if and only if all members have granted consent."""
    is_consented, missing_members = check_team_research_consent(db, team.id)
    if not is_consented:
        print(f"⚠️  Skipping team '{team.name}' (ID: {team.id}): {len(missing_members)} member(s) have not granted consent.")
        return None

    # Map member_id to anonymised_id
    member_to_anon: Dict[str, str] = {}
    for member in team.members:
        member_to_anon[member.id] = member.anonymised_id

    # Map identities to anonymised identifiers
    identity_to_anon: Dict[str, str] = {}
    for ident in team.identities:
        if ident.is_bot:
            identity_to_anon[ident.id] = "bot_account"
        elif ident.member_id and ident.member_id in member_to_anon:
            identity_to_anon[ident.id] = member_to_anon[ident.member_id]
        else:
            anon_external = f"anon_ext_{hashlib.sha256(ident.git_email.encode()).hexdigest()[:8]}"
            identity_to_anon[ident.id] = anon_external

    # Anonymized Commits & File changes (commit messages & emails removed)
    anonymised_commits = []
    for c in team.commits:
        anon_files = []
        for fc in c.file_changes:
            anon_files.append({
                "path": hash_path(fc.path, salt=salt),
                "language": fc.language,
                "additions": fc.additions,
                "deletions": fc.deletions,
                "complexity_delta": fc.complexity_delta,
                "tree_edit_size": fc.tree_edit_size,
                "flag": fc.flag,
            })

        anonymised_commits.append({
            "sha": c.sha,
            "author_anon_id": identity_to_anon.get(c.identity_id, "unknown"),
            "committed_at": c.committed_at.isoformat() if c.committed_at else None,
            "additions": c.additions,
            "deletions": c.deletions,
            "flag": c.flag,
            # Commit message and author email omitted per Section 7.4
            "file_changes": anon_files,
        })

    # Anonymized Pull Requests & Reviews
    anonymised_prs = []
    for pr in team.pull_requests:
        anon_reviews = []
        for r in pr.reviews:
            anon_reviews.append({
                "reviewer_anon_id": member_to_anon.get(r.reviewer_member_id, "external"),
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                "state": r.state,
                "comment_count": r.comment_count,
            })

        anonymised_prs.append({
            "number": pr.number,
            "author_anon_id": member_to_anon.get(pr.author_member_id, "external"),
            "opened_at": pr.opened_at.isoformat() if pr.opened_at else None,
            "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
            "state": pr.state,
            "reviews": anon_reviews,
        })

    # Anonymized Scores & Evidence
    anonymised_scores = []
    for s in team.scores:
        ev_items = []
        for ev in s.evidence_items:
            ev_items.append({
                "commit_sha": ev.commit_sha,
                "reason": ev.reason,
                "rank": ev.rank,
            })

        anonymised_scores.append({
            "member_anon_id": member_to_anon.get(s.member_id, "unknown"),
            "week": s.week,
            "model_version": s.model_version,
            "share": s.share,
            "facets": s.facets,
            "flags": s.flags,
            "evidence": ev_items,
        })

    # Anonymized Peer Surveys
    anonymised_surveys = []
    for surv in team.surveys:
        anonymised_surveys.append({
            "rater_anon_id": member_to_anon.get(surv.rater_member_id, "unknown"),
            "ratee_anon_id": member_to_anon.get(surv.ratee_member_id, "unknown"),
            "percent": surv.percent,
            "submitted_at": surv.submitted_at.isoformat() if surv.submitted_at else None,
        })

    # Anonymized Alerts
    anonymised_alerts = []
    for al in team.alerts:
        anonymised_alerts.append({
            "week": al.week,
            "label": al.label,
            "gini": al.gini,
            "details": al.details,
        })

    # Respect retention policy: Do not invent a retention period; flag instructor's decision if missing
    retention_info: Dict[str, Any] = {}
    if retention_until:
        retention_info["retention_policy"] = "specified"
        retention_info["retention_until"] = retention_until
    else:
        retention_info["retention_policy"] = "instructor_decision_required"
        retention_info["retention_until"] = None
        retention_info["retention_decision_status"] = "pending_instructor_decision"

    team_export_data = {
        "team_anon_id": f"team_{hashlib.sha256(team.id.encode()).hexdigest()[:10]}",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "retention": retention_info,
        "members": list(member_to_anon.values()),
        "commits": anonymised_commits,
        "pull_requests": anonymised_prs,
        "scores": anonymised_scores,
        "surveys": anonymised_surveys,
        "alerts": anonymised_alerts,
    }
    return team_export_data


def run_research_export(
    output_filepath: Optional[str] = None,
    db=None,
    retention_until: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Execute research export across all teams, saving to separate research directory."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Save in data/research_export/ unless explicit path given
        if output_filepath:
            output_path = Path(output_filepath).resolve()
        else:
            export_dir = storage_manager.get_research_export_dir()
            output_path = export_dir / "research_export.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        teams = db.query(Team).all()
        exported_dataset = []

        print(f"📦 Running research export across {len(teams)} team(s)...")
        for team in teams:
            team_data = export_anonymised_team(db, team, retention_until=retention_until)
            if team_data:
                exported_dataset.append(team_data)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(exported_dataset, f, indent=2)

        print(f"✅ Anonymized research dataset saved to: {output_path}")
        print(f"   Exported {len(exported_dataset)} fully consented team(s).")
        return exported_dataset
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else None
    run_research_export(out_file)
