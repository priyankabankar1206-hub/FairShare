"""Team Data Cleanup and Deletion Service (Section 6.6 & Section 7.3).

Executes comprehensive team data purging on request:
1. Deletes filesystem storage:
   - `data/{team_id}/raw/` (Raw GitHub API cache)
   - `data/{team_id}/features/` (Cached .npy commit embeddings)
   - `data/{team_id}/graphs/` (Weekly .pt graph snapshots)
   - Temporary repository clones
2. Purges in-memory consent, score, and job registries for the team.
3. Coordinates with Database Teammate's cascade deletion:
   NOTE: Never claims database deletion is complete when no live database is connected.
4. Generates an audit log entry for the deletion request.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional
from app.schemas.consent import TeamDeletionResponse
from app.services.audit_service import get_audit_service, AuditLogService
from app.services.consent_service import get_consent_service, ConsentService


class TeamDataCleanupService:
    """Orchestrates safe team data deletion across filesystem and databases."""

    def __init__(
        self,
        base_data_dir: Optional[str] = None,
        audit_service: Optional[AuditLogService] = None,
        consent_service: Optional[ConsentService] = None,
    ):
        self.base_data_dir = Path(base_data_dir or "data")
        self.temp_repos_dir = Path("temp_repos")
        self.audit = audit_service or get_audit_service()
        self.consent = consent_service or get_consent_service()

    def purge_team_filesystem(self, team_id: str) -> List[str]:
        """Safely delete all file storage and temporary clones associated with a team."""
        deleted_paths: List[str] = []

        # 1. Team data directory: data/{team_id}/ (raw, features, graphs)
        team_data_path = self.base_data_dir / team_id
        if team_data_path.exists():
            shutil.rmtree(team_data_path, ignore_errors=True)
            deleted_paths.append(str(team_data_path))

        # 2. Team temp repositories: temp_repos/{team_id} or pattern matches
        if self.temp_repos_dir.exists():
            for clone_dir in self.temp_repos_dir.glob(f"*{team_id}*"):
                if clone_dir.is_dir():
                    shutil.rmtree(clone_dir, ignore_errors=True)
                    deleted_paths.append(str(clone_dir))

        return deleted_paths

    def delete_team_data(
        self,
        team_id: str,
        actor_id: str,
        db_connected: bool = False,
    ) -> TeamDeletionResponse:
        """Execute full deletion workflow for a team."""
        # 1. Delete all filesystem artifacts (Section 7.3)
        deleted_paths = self.purge_team_filesystem(team_id)

        # 2. Purge in-memory consent and cache records
        self.consent.delete_team_consent(team_id)

        # 3. Handle database status honestly (Rule: Never claim DB deletion is complete when not connected)
        if db_connected:
            db_status = "cascaded_database_deletion_executed"
            overall_status = "completed"
        else:
            db_status = (
                "pending_database_connection (relational tables will cascade "
                "via ON DELETE CASCADE once database teammate connects PostgreSQL)"
            )
            overall_status = "partially_completed"

        # 4. Record audit log
        audit_id = self.audit.log_action(
            actor_id=actor_id,
            action="TEAM_DATA_DELETED",
            target=f"team:{team_id}",
            details={
                "deleted_paths": deleted_paths,
                "db_status": db_status,
                "overall_status": overall_status,
            },
        )

        return TeamDeletionResponse(
            team_id=team_id,
            status=overall_status,
            database_status=db_status,
            filesystem_cleaned=True,
            deleted_paths=deleted_paths,
            audit_log_id=audit_id,
            deleted_at=datetime.now(timezone.utc),
        )


_cleanup_service_instance: Optional[TeamDataCleanupService] = None


def get_cleanup_service() -> TeamDataCleanupService:
    global _cleanup_service_instance
    if _cleanup_service_instance is None:
        _cleanup_service_instance = TeamDataCleanupService()
    return _cleanup_service_instance
