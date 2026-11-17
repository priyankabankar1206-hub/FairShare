import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.db.base_class import Base


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        Index("ix_scores_team_week", "team_id", "week"),
        UniqueConstraint("team_id", "member_id", "week", "model_version", name="uq_score_member_week_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("team_members.id", ondelete="CASCADE"), nullable=False, index=True)
    week: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    share: Mapped[float] = mapped_column(Float, nullable=False)  # Individual percentage / share of total (adds to 1.0)
    facets: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)  # {"code": 0.52, "review": 0.30, "testing": 0.25, ...}
    flags: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)  # ["split_commits", ...]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="scores")
    member: Mapped["TeamMember"] = relationship("TeamMember", back_populates="scores")
    evidence_items: Mapped[List["Evidence"]] = relationship("Evidence", back_populates="score", cascade="all, delete-orphan")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    score_id: Mapped[str] = mapped_column(String(36), ForeignKey("scores.id", ondelete="CASCADE"), nullable=False, index=True)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 to 5 ranking

    # Relationships
    score: Mapped["Score"] = relationship("Score", back_populates="evidence_items")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_team_week", "team_id", "week"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(30), nullable=False)  # 'balanced', 'watch', 'at risk'
    gini: Mapped[float] = mapped_column(Float, nullable=False)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)  # Plain text reason / per-person warning details

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="alerts")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("team_members.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)  # 'instructor_note', 'dispute'
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="notes")
    author: Mapped["User"] = relationship("User", back_populates="authored_notes", foreign_keys=[author_id])
    member: Mapped[Optional["TeamMember"]] = relationship("TeamMember", back_populates="notes", foreign_keys=[member_id])


class Survey(Base):
    __tablename__ = "surveys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    rater_member_id: Mapped[str] = mapped_column(String(36), ForeignKey("team_members.id", ondelete="CASCADE"), nullable=False, index=True)
    ratee_member_id: Mapped[str] = mapped_column(String(36), ForeignKey("team_members.id", ondelete="CASCADE"), nullable=False, index=True)
    percent: Mapped[float] = mapped_column(Float, nullable=False)  # Peer estimated percentage
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="surveys")
    rater_member: Mapped["TeamMember"] = relationship("TeamMember", back_populates="rated_surveys", foreign_keys=[rater_member_id])
    ratee_member: Mapped["TeamMember"] = relationship("TeamMember", back_populates="received_surveys", foreign_keys=[ratee_member_id])

