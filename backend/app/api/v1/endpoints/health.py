"""Health check endpoint."""

from fastapi import APIRouter
from app.core.config import settings
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check API health status",
    description="Returns current health status, environment, and version.",
)
async def check_health() -> HealthResponse:
    """Check health of the backend application."""
    return HealthResponse(
        status="ok",
        app_name=settings.APP_NAME,
        environment=settings.ENVIRONMENT,
        version="0.1.0",
        database_status="pending_database_team",
    )
