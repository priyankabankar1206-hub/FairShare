"""Pytest fixtures and configuration."""

import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure the backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.main import app
from app.core.security import create_access_token


@pytest.fixture
def client() -> TestClient:
    """Fixture providing a FastAPI TestClient."""
    return TestClient(app)


@pytest.fixture
def student_token() -> str:
    """Return a valid signed JWT for a student enrolled in t_sample_001 and t_001."""
    return create_access_token(
        subject="usr_student_alice",
        role="student",
        github_login="alice_dev",
        team_ids=["t_sample_001", "t_001"],
    )


@pytest.fixture
def student_headers(student_token: str) -> dict:
    return {"Authorization": f"Bearer {student_token}"}


@pytest.fixture
def instructor_token() -> str:
    """Return a valid signed JWT for an instructor managing t_sample_001 and t_001."""
    return create_access_token(
        subject="usr_prof_smith",
        role="instructor",
        github_login="prof_smith",
        managed_team_ids=["t_sample_001", "t_001"],
    )


@pytest.fixture
def instructor_headers(instructor_token: str) -> dict:
    return {"Authorization": f"Bearer {instructor_token}"}
