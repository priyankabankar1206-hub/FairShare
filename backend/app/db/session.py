"""Database connection and session management placeholder.

IMPORTANT:
The database schema, ORM models, and migrations are maintained by the Database Teammate.
This file provides a placeholder connection factory and FastAPI dependency (`get_db`)
so backend routers and services can cleanly consume database sessions once the
database teammate supplies the connection and models.
"""

from typing import Generator, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

# Lazy initialization: Engine will only attempt connection when first queried
_engine = None
_SessionLocal = None


def get_engine():
    """Retrieve or create the SQLAlchemy engine using DATABASE_URL."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(
            settings.DATABASE_URL,
            pool_pre_ping=True,
            future=True,
        )
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=_engine,
        )
    return _engine


def get_db() -> Generator[Optional[Session], None, None]:
    """FastAPI dependency to yield a database session.

    To be used by endpoint route handlers:
    `db: Session = Depends(get_db)`
    """
    try:
        get_engine()
        session: Session = _SessionLocal()
        try:
            yield session
        finally:
            session.close()
    except Exception as exc:
        # Graceful placeholder: allows backend to run in decoupled mode
        # until the database teammate provides the live PostgreSQL instance.
        yield None
