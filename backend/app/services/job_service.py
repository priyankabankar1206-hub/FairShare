"""Job Orchestration and State Management Service (Section 6.2 & 6.3).

Tracks asynchronous tasks (sync jobs, scoring jobs) with progress reporting
and execution telemetry.

NOTE FOR DATABASE TEAMMATE:
This service manages the `jobs` entity (id, team_id, kind, status, progress, error,
started_at, finished_at). Once the SQLAlchemy `jobs` model is available, this service
will delegate persistence to PostgreSQL.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from app.schemas.job import JobResponse


class JobService:
    """Manages background job tracking, progress calculation, and state updates."""

    def __init__(self):
        # In-memory store: {job_id: JobResponse}
        self._jobs: Dict[str, JobResponse] = {}

    def create_job(self, team_id: str, kind: str = "sync") -> JobResponse:
        """Create a new job in 'pending' status."""
        job_id = f"job_{kind}_{team_id}_{uuid.uuid4().hex[:8]}"
        job = JobResponse(
            id=job_id,
            team_id=team_id,
            kind=kind,
            status="pending",
            progress=0.0,
            started_at=datetime.now(timezone.utc),
            details={"step": "queued"},
        )
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[JobResponse]:
        """Retrieve job by its unique identifier."""
        return self._jobs.get(job_id)

    def list_team_jobs(self, team_id: str) -> List[JobResponse]:
        """List all jobs for a specific team."""
        return [job for job in self._jobs.values() if job.team_id == team_id]

    def update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Optional[JobResponse]:
        """Update job status, progress percentage (0.0 - 1.0), and details."""
        job = self._jobs.get(job_id)
        if not job:
            return None

        if status is not None:
            job.status = status
            if status in {"completed", "failed"}:
                job.finished_at = datetime.now(timezone.utc)
        if progress is not None:
            job.progress = max(0.0, min(1.0, progress))
        if error is not None:
            job.error = error
        if details:
            job.details.update(details)

        return job


_job_service_instance: Optional[JobService] = None


def get_job_service() -> JobService:
    global _job_service_instance
    if _job_service_instance is None:
        _job_service_instance = JobService()
    return _job_service_instance
