"""Job orchestration and background sync task endpoints (Section 6.3)."""

from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.api.deps import get_current_user, verify_team_access, require_team_consent
from app.schemas.auth import CurrentUser
from app.schemas.job import JobResponse
from app.schemas.github import SyncTriggerRequest, IngestionCheckpoint
from app.services.job_service import get_job_service
from app.services.github.ingestion import get_ingestion_orchestrator

router = APIRouter()


@router.post(
    "/teams/{team_id}/sync",
    response_model=JobResponse,
    summary="Trigger repository sync job",
    description="Starts an asynchronous git clone & API sync job, returning a trackable job_id.",
)
async def trigger_team_sync(
    team_id: str,
    background_tasks: BackgroundTasks,
    payload: Optional[SyncTriggerRequest] = None,
    current_user: CurrentUser = Depends(require_team_consent),
) -> JobResponse:
    job_service = get_job_service()
    orchestrator = get_ingestion_orchestrator()

    # Determine target repo URL
    repo_url = (payload.repo_url if payload and payload.repo_url else None) or "https://github.com/sample/repo"
    resume = payload.resume if payload is not None else True

    # Create tracked job
    job = job_service.create_job(team_id=team_id, kind="sync")

    # Dispatch ingestion in background
    background_tasks.add_task(
        orchestrator.execute_sync,
        job_id=job.id,
        team_id=team_id,
        repo_url=repo_url,
        resume=resume,
    )

    return job


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Get job status and progress",
)
async def get_job_status(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> JobResponse:
    job_service = get_job_service()
    job = job_service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return job


@router.get(
    "/teams/{team_id}/sync/checkpoint",
    response_model=Optional[IngestionCheckpoint],
    summary="Get team ingestion checkpoint",
    description="Inspect saved intermediate state for resumable sync.",
)
async def get_sync_checkpoint(
    team_id: str,
    current_user: CurrentUser = Depends(verify_team_access),
) -> Optional[IngestionCheckpoint]:
    orchestrator = get_ingestion_orchestrator()
    ckpt = orchestrator.load_checkpoint(team_id)
    if not ckpt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No sync checkpoint found for team '{team_id}'.",
        )
    return ckpt
