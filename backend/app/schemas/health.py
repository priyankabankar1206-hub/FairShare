"""Health check response schemas."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check status payload."""

    status: str = Field(default="ok", description="Overall backend health status")
    app_name: str = Field(..., description="Application name")
    environment: str = Field(..., description="Running environment (development/production/testing)")
    version: str = Field(..., description="Backend application version")
    database_status: str = Field(
        default="pending_database_team",
        description="Database readiness status (maintained by Database Teammate)",
    )
