"""Job and sync task status schemas (Section 6.2 & 6.3)."""

from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    """Job status returned by GET /jobs/{id}."""

    id: str
    team_id: str
    kind: str = Field(..., description="e.g. 'sync', 'scoring', 'export'")
    status: str = Field(..., description="'pending', 'in_progress', 'completed', 'failed'")
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="Progress from 0.0 to 1.0")
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Execution telemetry (e.g., commits_synced, prs_synced, resumed)",
    )
