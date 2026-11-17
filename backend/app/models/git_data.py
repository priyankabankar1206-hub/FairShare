import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base_class import Base


class Identity(Base):
    __tablename__ = "identities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    git_name: Mapped[str] = mapped_column(String(200), nullable=False)
    git_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    member_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="identities")
    member: Mapped[Optional["TeamMember"]] = relationship("TeamMember", back_populates="identities")
    commits: Mapped[List["Commit"]] = relationship("Commit", back_populates="identity")


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (
        UniqueConstraint("team_id", "sha", name="uq_commits_team_sha"),
        Index("ix_commits_team_sha", "team_id", "sha"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    sha: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    identity_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("identities.id", ondelete="SET NULL"), nullable=True, index=True)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flag: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 'substantive', 'no-op', 'duplicate', 'generated'

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="commits")
    identity: Mapped[Optional["Identity"]] = relationship("Identity", back_populates="commits")
    file_changes: Mapped[List["FileChange"]] = relationship("FileChange", back_populates="commit", cascade="all, delete-orphan")


class FileChange(Base):
    __tablename__ = "file_changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    commit_id: Mapped[str] = mapped_column(String(36), ForeignKey("commits.id", ondelete="CASCADE"), nullable=False, index=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    complexity_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tree_edit_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flag: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # e.g., 'substantive', 'whitespace-only'

    # Relationships
    commit: Mapped["Commit"] = relationship("Commit", back_populates="file_changes")


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("team_id", "number", name="uq_pr_team_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    author_member_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    merged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(String(30), nullable=False)  # 'open', 'closed', 'merged'

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="pull_requests")
    author_member: Mapped[Optional["TeamMember"]] = relationship("TeamMember", back_populates="pull_requests")
    reviews: Mapped[List["Review"]] = relationship("Review", back_populates="pull_request", cascade="all, delete-orphan")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pull_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("pull_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_member_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False)  # 'APPROVED', 'CHANGES_REQUESTED', 'COMMENTED'
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    pull_request: Mapped["PullRequest"] = relationship("PullRequest", back_populates="reviews")
    reviewer_member: Mapped[Optional["TeamMember"]] = relationship("TeamMember", back_populates="reviews")


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("team_id", "number", name="uq_issue_team_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    author_member_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True)
    labels: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="issues")
    author_member: Mapped[Optional["TeamMember"]] = relationship("TeamMember", back_populates="issues")

