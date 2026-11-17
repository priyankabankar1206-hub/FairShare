import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.base_class import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_team_status", "team_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)  # 'sync', 'scoring', 'full_pipeline'
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")  # 'queued', 'running', 'completed', 'failed'
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 to 100 percentage
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="jobs")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # 'view_report', 'export_data', 'mark_dispute'
    target: Mapped[str] = mapped_column(String(200), nullable=False)  # e.g., 'team:t_001', 'report:week_4'
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    actor: Mapped["User"] = relationship("User", back_populates="audit_logs")


class CorpusRepo(Base):
    """Mined open-source repositories for offline model training (kept apart from student data)."""
    __tablename__ = "corpus_repos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)  # owner/repo
    licence: Mapped[str] = mapped_column(String(100), nullable=False)
    commit_count: Mapped[int] = mapped_column(Integer, nullable=False)
    contributors: Mapped[int] = mapped_column(Integer, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

