"""Identity Mapping Service (Phase 5 — FairShare Section 6.2 & 6.3).

Responsibilities:
  1. Automatically match Git commit author identities to FairShare team members
     using GitHub username, email heuristics, and known member registration data.
  2. Record manual identity corrections submitted by instructors.
  3. Detect and report unmatched (ambiguous) Git identities.
  4. Prevent duplicate and conflicting mappings.
  5. Record every manual mapping in the audit log.

NOTE FOR DATABASE TEAMMATE:
  - Replace the in-memory dicts with SQLAlchemy queries against the
    `identity_mappings` table (columns: id, team_id, git_name, git_email,
     member_id, mapped_by, mapped_at, is_bot, is_manual).
  - The `_team_rosters` dict should be replaced by a JOIN on the
    `team_members` table.
  - Replace `_commit_author_counts` with a query on `commits`.
"""

import uuid
import logging
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timezone

from app.schemas.identity import (
    IdentityMappingRecord,
    UnmatchedIdentity,
    IdentityMappingListResponse,
)
from app.schemas.github import MinedCommit
from app.services.audit_service import get_audit_service

logger = logging.getLogger("fairshare.identity")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


def _mapping_key(git_email: str, git_name: str) -> str:
    """Build a stable dict key from email + name for identity uniqueness checks."""
    return f"{git_email.lower().strip()}|{git_name.lower().strip()}"


class IdentityMappingService:
    """In-memory identity mapping service.

    Data structures:
        _mappings:  { team_id -> { mapping_key -> IdentityMappingRecord } }
        _rosters:   { team_id -> set of member_id strings }
        _member_meta: { team_id -> { member_id -> { 'email': ..., 'github_login': ... } } }
        _commit_counts: { team_id -> { mapping_key -> int } }
    """

    def __init__(self):
        # team_id → { key → IdentityMappingRecord }
        self._mappings: Dict[str, Dict[str, IdentityMappingRecord]] = {}

        # team_id → { member_id → { 'email': str, 'github_login': str } }
        self._member_meta: Dict[str, Dict[str, Dict[str, str]]] = {}

        # team_id → set(member_id)
        self._rosters: Dict[str, set] = {}

        # team_id → { key → commit_count }
        self._commit_counts: Dict[str, Dict[str, int]] = {}

    # ------------------------------------------------------------------
    # Roster Management
    # ------------------------------------------------------------------

    def register_team_member(
        self,
        team_id: str,
        member_id: str,
        github_login: str = "",
        email: str = "",
    ) -> None:
        """Register a team member so their identity can be used in auto-matching.

        Args:
            team_id:      FairShare team identifier.
            member_id:    FairShare member account identifier.
            github_login: GitHub username (may be empty if not yet linked).
            email:        Primary email of the member.

        NOTE FOR DATABASE TEAMMATE:
            Replace with a query: SELECT member_id, github_login, email
            FROM team_members WHERE team_id = :team_id
        """
        self._rosters.setdefault(team_id, set()).add(member_id)
        self._member_meta.setdefault(team_id, {})[member_id] = {
            "email": email.lower().strip(),
            "github_login": github_login.lower().strip(),
        }
        logger.debug(
            f"[IdentityService] Registered member '{member_id}' in team '{team_id}' "
            f"(github={github_login}, email={email})"
        )

    def _get_roster(self, team_id: str) -> set:
        """Return the known member IDs for a team (empty set if unknown)."""
        return self._rosters.get(team_id, set())

    def _member_is_in_team(self, team_id: str, member_id: str) -> bool:
        """Return True if member_id is registered in the team roster."""
        return member_id in self._get_roster(team_id)

    # ------------------------------------------------------------------
    # Auto-Matching
    # ------------------------------------------------------------------

    def auto_match_from_commits(
        self,
        team_id: str,
        commits: List[MinedCommit],
    ) -> int:
        """Attempt to automatically match commit authors to known team members.

        Matching strategy (in priority order):
          1. Exact email match against registered member email.
          2. Case-insensitive GitHub login match against commit author name.

        Only creates a mapping if the roster has at least one member registered.

        Args:
            team_id: Team to perform matching for.
            commits: List of MinedCommit objects from the ingestion service.

        Returns:
            int: Number of new auto-mappings created in this call.

        NOTE FOR DATABASE TEAMMATE:
            After matching, persist the produced IdentityMappingRecord rows
            to the identity_mappings table.
        """
        created = 0
        team_roster = self._get_roster(team_id)
        team_meta = self._member_meta.get(team_id, {})

        for commit in commits:
            if not commit.author:
                continue

            git_name = (commit.author.name or "").strip()
            git_email = (commit.author.email or "").lower().strip()
            if not git_email and not git_name:
                continue

            key = _mapping_key(git_email, git_name)

            # Track commit count per author key (used for unmatched listing)
            self._commit_counts.setdefault(team_id, {})
            self._commit_counts[team_id][key] = (
                self._commit_counts[team_id].get(key, 0) + 1
            )

            # Skip if already mapped
            if key in self._mappings.get(team_id, {}):
                continue

            # Try to find a matching member
            matched_member_id: Optional[str] = None
            for member_id in team_roster:
                meta = team_meta.get(member_id, {})
                member_email = meta.get("email", "")
                member_login = meta.get("github_login", "")

                # Priority 1: exact email match
                if member_email and git_email and git_email == member_email:
                    matched_member_id = member_id
                    break

                # Priority 2: GitHub login matches commit author name (case-insensitive)
                if (
                    member_login
                    and git_name
                    and git_name.lower() == member_login.lower()
                ):
                    matched_member_id = member_id
                    break

            if matched_member_id:
                record = IdentityMappingRecord(
                    id=f"idmap_{uuid.uuid4().hex[:12]}",
                    team_id=team_id,
                    git_name=git_name,
                    git_email=git_email,
                    member_id=matched_member_id,
                    mapped_by="system:auto_match",
                    mapped_at=datetime.now(timezone.utc),
                    is_bot=False,
                    is_manual=False,
                )
                self._mappings.setdefault(team_id, {})[key] = record
                created += 1
                logger.info(
                    f"[IdentityService] Auto-matched '{git_name}' <{git_email}> "
                    f"→ member '{matched_member_id}' in team '{team_id}'"
                )

        return created

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_all_mappings(self, team_id: str) -> List[IdentityMappingRecord]:
        """Return all resolved identity mappings for the given team.

        NOTE FOR DATABASE TEAMMATE:
            SELECT * FROM identity_mappings WHERE team_id = :team_id AND is_active = TRUE
        """
        return list(self._mappings.get(team_id, {}).values())

    def get_unmatched(self, team_id: str) -> List[UnmatchedIdentity]:
        """Return git identities seen in commits that have no mapping.

        Includes heuristic suggestions (possible_members) based on
        partial email/login similarity.

        NOTE FOR DATABASE TEAMMATE:
            Query commits for unique (author_name, author_email) pairs
            that have no corresponding row in identity_mappings.
        """
        mapped_keys = set(self._mappings.get(team_id, {}).keys())
        counts = self._commit_counts.get(team_id, {})
        team_meta = self._member_meta.get(team_id, {})

        unmatched: List[UnmatchedIdentity] = []
        for key, count in counts.items():
            if key in mapped_keys:
                continue

            # Reconstruct name/email from key (email|name)
            parts = key.split("|", 1)
            git_email = parts[0] if len(parts) > 0 else ""
            git_name = parts[1] if len(parts) > 1 else ""

            # Suggest possible members (simple heuristic: shared email domain)
            possible: List[str] = []
            for member_id, meta in team_meta.items():
                m_email = meta.get("email", "")
                m_login = meta.get("github_login", "")
                if git_email and m_email:
                    # Same email domain hint
                    git_domain = git_email.split("@")[-1] if "@" in git_email else ""
                    m_domain = m_email.split("@")[-1] if "@" in m_email else ""
                    if git_domain and git_domain == m_domain:
                        possible.append(member_id)
                        continue
                if m_login and git_name and m_login.lower() in git_name.lower():
                    possible.append(member_id)

            unmatched.append(
                UnmatchedIdentity(
                    git_name=git_name,
                    git_email=git_email,
                    commit_count=count,
                    possible_members=list(set(possible)),
                )
            )

        return unmatched

    def get_mapping_list_response(self, team_id: str) -> IdentityMappingListResponse:
        """Build the full IdentityMappingListResponse for a team."""
        all_mappings = self.get_all_mappings(team_id)
        unmatched = self.get_unmatched(team_id)
        return IdentityMappingListResponse(
            team_id=team_id,
            total_mappings=len(all_mappings),
            total_unmatched=len(unmatched),
            mappings=all_mappings,
            unmatched=unmatched,
        )

    # ------------------------------------------------------------------
    # Manual Mapping (Instructor Action)
    # ------------------------------------------------------------------

    def apply_manual_mapping(
        self,
        team_id: str,
        git_name: str,
        git_email: str,
        member_id: str,
        actor_id: str,
        is_bot: bool = False,
    ) -> Tuple[IdentityMappingRecord, bool]:
        """Apply an instructor-submitted manual identity mapping.

        Validation rules enforced:
          1. member_id must exist in the team roster (422 if not).
          2. Same git identity already mapped to the SAME member → idempotent, return existing record.
          3. Same git identity mapped to a DIFFERENT member → 409 Conflict.

        Args:
            team_id:   Team the mapping belongs to.
            git_name:  Git commit author name.
            git_email: Git commit author email.
            member_id: FairShare member to assign this identity to.
            actor_id:  Instructor's user ID (for audit log).
            is_bot:    If True, mark identity as a CI/bot account.

        Returns:
            Tuple[IdentityMappingRecord, bool]:
                The mapping record and whether it was newly created (True) or
                was already identical (False — idempotent).

        Raises:
            ValueError("member_not_in_team"): member_id not in team roster.
            ValueError("conflict"): Same git identity already maps to a different member.

        NOTE FOR DATABASE TEAMMATE:
            Use an INSERT ... ON CONFLICT or SELECT-then-INSERT pattern in the DB.
        """
        # Validation 1: member must be in roster
        if not self._member_is_in_team(team_id, member_id):
            raise ValueError(
                f"member_not_in_team|member_id={member_id}|team_id={team_id}"
            )

        key = _mapping_key(git_email, git_name)
        existing = self._mappings.get(team_id, {}).get(key)

        # Validation 2: duplicate (same target member) → idempotent
        if existing is not None and existing.member_id == member_id:
            logger.info(
                f"[IdentityService] Duplicate manual mapping ignored (idempotent): "
                f"'{git_name}' <{git_email}> → '{member_id}' in team '{team_id}'"
            )
            return existing, False

        # Validation 3: conflict (same git identity → different member)
        if existing is not None and existing.member_id != member_id:
            raise ValueError(
                f"conflict|git_email={git_email}|current_member={existing.member_id}|"
                f"requested_member={member_id}"
            )

        # Create new mapping record
        record = IdentityMappingRecord(
            id=f"idmap_{uuid.uuid4().hex[:12]}",
            team_id=team_id,
            git_name=git_name,
            git_email=git_email,
            member_id=member_id,
            mapped_by=actor_id,
            mapped_at=datetime.now(timezone.utc),
            is_bot=is_bot,
            is_manual=True,
        )
        self._mappings.setdefault(team_id, {})[key] = record

        # Audit log — mandatory for all manual corrections (Section 6.6)
        audit_service = get_audit_service()
        audit_service.log_action(
            actor_id=actor_id,
            action="IDENTITY_MAPPED_MANUALLY",
            target=f"team:{team_id}",
            details={
                "mapping_id": record.id,
                "git_name": git_name,
                "git_email": git_email,
                "member_id": member_id,
                "is_bot": is_bot,
            },
        )

        logger.info(
            f"[IdentityService] Manual mapping created: '{git_name}' <{git_email}> "
            f"→ '{member_id}' in team '{team_id}' by instructor '{actor_id}'"
        )
        return record, True

    def clear_team(self, team_id: str) -> None:
        """Remove all in-memory data for a team. Used by cleanup service and tests."""
        self._mappings.pop(team_id, None)
        self._rosters.pop(team_id, None)
        self._member_meta.pop(team_id, None)
        self._commit_counts.pop(team_id, None)


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_identity_service_instance: Optional[IdentityMappingService] = None


def get_identity_service() -> IdentityMappingService:
    """Return the application-wide singleton IdentityMappingService.

    NOTE FOR DATABASE TEAMMATE:
        Inject a database session here when replacing with a DB-backed implementation.
    """
    global _identity_service_instance
    if _identity_service_instance is None:
        _identity_service_instance = IdentityMappingService()
    return _identity_service_instance
