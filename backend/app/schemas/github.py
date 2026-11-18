"""Pydantic schemas for GitHub repository ingestion and data mining (Phase 4).

Adheres to Section 6.5 ("GitHub integration") and Section 7.2 of the
FairShare Project Documentation.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class CommitAuthor(BaseModel):
    """Git commit author identity."""
    name: str
    email: str
    date: Optional[datetime] = None


class FileChange(BaseModel):
    """File modification details in a commit."""
    path: str
    additions: int = 0
    deletions: int = 0
    change_type: str = Field(
        default="modified",
        description="'added', 'modified', 'deleted', 'renamed'",
    )


class MinedCommit(BaseModel):
    """Complete commit extracted from local git history (Section 6.5 & 7.2)."""
    sha: str
    author: CommitAuthor
    message: str
    additions: int = 0
    deletions: int = 0
    files_changed: List[FileChange] = Field(default_factory=list)
    parent_shas: List[str] = Field(default_factory=list)
    stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw stats dict (additions, deletions, total) from GitPython",
    )


class PullRequestRecord(BaseModel):
    """GitHub Pull Request metadata fetched via REST API (Section 6.5 & 7.2)."""
    id: int
    number: int
    title: str
    author_login: str
    state: str = Field(..., description="'open', 'closed'")
    created_at: datetime
    merged_at: Optional[datetime] = None
    comments_count: int = 0


class IngestionCheckpoint(BaseModel):
    """State saved in data/{team_id}/raw/checkpoint.json for resumable sync (Section 7.3)."""
    team_id: str
    repo_url: str
    last_synced_sha: Optional[str] = None
    total_commits_synced: int = 0
    last_pr_page: int = 0
    is_completed: bool = False
    updated_at: datetime


class SyncTriggerRequest(BaseModel):
    """Request payload to initiate or resume repository sync."""
    repo_url: Optional[str] = Field(
        default=None,
        description="Optional repository URL override (defaults to team's registered repo_url)",
    )
    resume: bool = Field(
        default=True,
        description="Whether to resume from last saved checkpoint if one exists",
    )
