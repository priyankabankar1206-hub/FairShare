"""Database connection and session management."""

from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

_engine = None
_SessionLocal = None


def get_engine():
    """Retrieve or create the SQLAlchemy engine."""
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


def SessionLocal() -> Session:
    """Create a new session using the initialized engine."""
    get_engine()
    return _SessionLocal()


def get_db() -> Generator[Optional[Session], None, None]:
    """Provide a database session to FastAPI routes.

    Ensures sessions are closed and failed transactions are rolled back.
    Yields None if the engine/session cannot be established.
    """
    try:
        get_engine()
        db: Session = _SessionLocal()
    except Exception:
        yield None
        return

    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
