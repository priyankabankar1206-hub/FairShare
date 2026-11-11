"""GitHub Repository Ingestion Orchestrator and Resumption Manager.

Manages the end-to-end repository synchronization workflow:
1. Validates repository access.
2. Checks for existing checkpoints in `data/{team_id}/raw/checkpoint.json`.
3. Clones repository into a temporary workspace.
4. Mines commits, authors, timestamps, and file changes (resuming from last commit).
5. Fetches Pull Requests via GitHub API with pagination and rate-limit handling.
6. Persists raw intermediate data to `data/{team_id}/raw/` for resumable restarts.
7. Ensures temporary Git clone is unconditionally deleted at the end.
8. Coordinates progress reporting with JobService (0% -> 100%).
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from app.schemas.github import IngestionCheckpoint, MinedCommit, PullRequestRecord
from app.services.github.client import GitHubService, get_github_service, parse_repo_url
from app.services.job_service import JobService, get_job_service
from app.services.audit_service import AuditLogService, get_audit_service
from app.services.github.exceptions import (
    GitHubError,
    GitHubRateLimitError,
    GitHubRepoNotFoundError,
    GitHubAuthError,
)


class IngestionOrchestrator:
    """Orchestrates git mining, API pulling, checkpointing, and job updates."""

    def __init__(
        self,
        base_data_dir: str = "data",
        github_service: Optional[GitHubService] = None,
        job_service: Optional[JobService] = None,
        audit_service: Optional[AuditLogService] = None,
    ):
        self.base_data_dir = Path(base_data_dir)
        self.github = github_service or get_github_service()
        self.jobs = job_service or get_job_service()
        self.audit = audit_service or get_audit_service()

    def get_raw_dir(self, team_id: str) -> Path:
        """Get or create data/{team_id}/raw/ directory (Section 7.3)."""
        raw_dir = self.base_data_dir / team_id / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        return raw_dir

    def load_checkpoint(self, team_id: str) -> Optional[IngestionCheckpoint]:
        """Load saved checkpoint for a team if one exists."""
        ckpt_file = self.get_raw_dir(team_id) / "checkpoint.json"
        if not ckpt_file.exists():
            return None
        try:
            with open(ckpt_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return IngestionCheckpoint.model_validate(data)
        except Exception:
            return None

    def save_checkpoint(self, team_id: str, checkpoint: IngestionCheckpoint) -> None:
        """Persist checkpoint to data/{team_id}/raw/checkpoint.json."""
        ckpt_file = self.get_raw_dir(team_id) / "checkpoint.json"
        with open(ckpt_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint.model_dump(mode="json"), f, indent=2)

    def save_raw_json(self, team_id: str, filename: str, data: Any) -> Path:
        """Save intermediate raw data for resumable caching."""
        target_file = self.get_raw_dir(team_id) / filename
        with open(target_file, "w", encoding="utf-8") as f:
            if isinstance(data, list) and data and hasattr(data[0], "model_dump"):
                json_data = [item.model_dump(mode="json") for item in data]
            elif hasattr(data, "model_dump"):
                json_data = data.model_dump(mode="json")
            else:
                json_data = data
            json.dump(json_data, f, indent=2)
        return target_file

    def load_raw_json(self, team_id: str, filename: str) -> Optional[Any]:
        """Load previously saved raw JSON data."""
        target_file = self.get_raw_dir(team_id) / filename
        if not target_file.exists():
            return None
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    async def execute_sync(
        self,
        job_id: str,
        team_id: str,
        repo_url: str,
        auth_token: Optional[str] = None,
        resume: bool = True,
    ) -> None:
        """Execute full repository sync workflow with progress and checkpoint tracking."""
        temp_clone_dir: Optional[str] = None
        self.jobs.update_job(
            job_id,
            status="in_progress",
            progress=0.05,
            details={"step": "validating_repository", "repo_url": repo_url},
        )

        try:
            # Step 1: Parse repo URL
            owner, repo_name = parse_repo_url(repo_url)

            # Step 2: Check for existing checkpoint
            checkpoint = self.load_checkpoint(team_id) if resume else None
            resuming = checkpoint is not None and not checkpoint.is_completed

            mined_commits: List[MinedCommit] = []
            mined_prs: List[PullRequestRecord] = []
            last_sha: Optional[str] = None
            last_pr_page = 1

            if resuming and checkpoint:
                self.jobs.update_job(
                    job_id,
                    progress=0.15,
                    details={"step": "resuming_from_checkpoint", "resumed": True},
                )
                last_sha = checkpoint.last_synced_sha
                last_pr_page = checkpoint.last_pr_page
                # Load previously saved commits if present
                raw_commits = self.load_raw_json(team_id, "commits.json")
                if raw_commits:
                    mined_commits = [MinedCommit.model_validate(c) for c in raw_commits]

            # Step 3: Clone repository temporarily (Section 6.5)
            self.jobs.update_job(
                job_id,
                progress=0.25,
                details={"step": "cloning_repository"},
            )
            temp_clone_dir = self.github.clone_repository_temporarily(repo_url, auth_token)

            # Step 4: Mine commits and file changes
            self.jobs.update_job(
                job_id,
                progress=0.50,
                details={"step": "mining_commits_and_diffs"},
            )
            new_commits = self.github.mine_repository_commits(
                temp_clone_dir,
                resume_after_sha=last_sha,
            )
            mined_commits.extend(new_commits)
            if mined_commits:
                last_sha = mined_commits[-1].sha

            # Save commits checkpoint
            self.save_raw_json(team_id, "commits.json", mined_commits)

            # Step 5: Fetch Pull Requests via GitHub REST API with pagination
            self.jobs.update_job(
                job_id,
                progress=0.75,
                details={"step": "fetching_pull_requests", "commits_mined": len(mined_commits)},
            )

            # Load previously fetched PRs if resuming
            raw_prs = self.load_raw_json(team_id, "pulls.json")
            if raw_prs and resuming:
                mined_prs = [PullRequestRecord.model_validate(p) for p in raw_prs]

            current_page = max(1, last_pr_page)
            has_next = True
            while has_next:
                page_prs, has_next = await self.github.fetch_pull_requests_page(
                    owner=owner,
                    repo=repo_name,
                    page=current_page,
                    per_page=30,
                )
                mined_prs.extend(page_prs)
                current_page += 1

                # Update intermediate checkpoint
                self.save_checkpoint(
                    team_id,
                    IngestionCheckpoint(
                        team_id=team_id,
                        repo_url=repo_url,
                        last_synced_sha=last_sha,
                        total_commits_synced=len(mined_commits),
                        last_pr_page=current_page,
                        is_completed=False,
                        updated_at=datetime.now(timezone.utc),
                    ),
                )
                # Cap pagination defensively in test/dev environments
                if current_page > 20:
                    break

            self.save_raw_json(team_id, "pulls.json", mined_prs)

            # Step 6: Mark checkpoint as completed
            final_checkpoint = IngestionCheckpoint(
                team_id=team_id,
                repo_url=repo_url,
                last_synced_sha=last_sha,
                total_commits_synced=len(mined_commits),
                last_pr_page=current_page,
                is_completed=True,
                updated_at=datetime.now(timezone.utc),
            )
            self.save_checkpoint(team_id, final_checkpoint)

            # Step 7: Finalize job status
            self.jobs.update_job(
                job_id,
                status="completed",
                progress=1.0,
                details={
                    "step": "completed",
                    "commits_synced": len(mined_commits),
                    "prs_synced": len(mined_prs),
                    "resumed": resuming,
                },
            )
            self.audit.log_action(
                actor_id=f"job:{job_id}",
                action="REPOSITORY_SYNC_COMPLETED",
                target=f"team:{team_id}",
                details={"commits_count": len(mined_commits), "prs_count": len(mined_prs)},
            )

        except GitHubRateLimitError as exc:
            self.jobs.update_job(
                job_id,
                status="failed",
                error=f"Rate limit exceeded: {exc}. Retry after {exc.retry_after_seconds}s.",
                details={"error_type": "rate_limit", "retry_after_seconds": exc.retry_after_seconds},
            )
        except Exception as exc:
            self.jobs.update_job(
                job_id,
                status="failed",
                error=str(exc),
                details={"error_type": type(exc).__name__},
            )
        finally:
            # Always ensure temporary clone is deleted (Section 6.5)
            if temp_clone_dir:
                self.github.cleanup_temporary_clone(temp_clone_dir)


_orchestrator_instance: Optional[IngestionOrchestrator] = None


def get_ingestion_orchestrator() -> IngestionOrchestrator:
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = IngestionOrchestrator()
    return _orchestrator_instance
