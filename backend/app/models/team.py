import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    github_login: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="student")  # 'student' or 'instructor'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    team_memberships: Mapped[List["TeamMember"]] = relationship("TeamMember", back_populates="user")
    authored_notes: Mapped[List["Note"]] = relationship("Note", back_populates="author", foreign_keys="Note.author_id")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="actor")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    course: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    repo_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Cascading relationships to child tables
    members: Mapped[List["TeamMember"]] = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    identities: Mapped[List["Identity"]] = relationship("Identity", back_populates="team", cascade="all, delete-orphan")
    commits: Mapped[List["Commit"]] = relationship("Commit", back_populates="team", cascade="all, delete-orphan")
    pull_requests: Mapped[List["PullRequest"]] = relationship("PullRequest", back_populates="team", cascade="all, delete-orphan")
    issues: Mapped[List["Issue"]] = relationship("Issue", back_populates="team", cascade="all, delete-orphan")
    scores: Mapped[List["Score"]] = relationship("Score", back_populates="team", cascade="all, delete-orphan")
    alerts: Mapped[List["Alert"]] = relationship("Alert", back_populates="team", cascade="all, delete-orphan")
    notes: Mapped[List["Note"]] = relationship("Note", back_populates="team", cascade="all, delete-orphan")
    surveys: Mapped[List["Survey"]] = relationship("Survey", back_populates="team", cascade="all, delete-orphan")
    jobs: Mapped[List["Job"]] = relationship("Job", back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_member"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    consent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    anonymised_id: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: f"anon_{uuid.uuid4().hex[:12]}", nullable=False)

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="team_memberships")
    identities: Mapped[List["Identity"]] = relationship("Identity", back_populates="member")
    scores: Mapped[List["Score"]] = relationship("Score", back_populates="member")
    reviews: Mapped[List["Review"]] = relationship("Review", back_populates="reviewer_member")
    pull_requests: Mapped[List["PullRequest"]] = relationship("PullRequest", back_populates="author_member")
    issues: Mapped[List["Issue"]] = relationship("Issue", back_populates="author_member")
    rated_surveys: Mapped[List["Survey"]] = relationship("Survey", back_populates="rater_member", foreign_keys="Survey.rater_member_id")
    received_surveys: Mapped[List["Survey"]] = relationship("Survey", back_populates="ratee_member", foreign_keys="Survey.ratee_member_id")
    notes: Mapped[List["Note"]] = relationship("Note", back_populates="member", foreign_keys="Note.member_id")
