"""Mining logger and registration utility for open-source corpus repositories (Section 5.6 & 7.2).

Maintains an isolated catalog in `corpus_repos` table for offline model pretraining
and robustness benchmarking, kept strictly separate from student repository data.
"""

import sys
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

# Setup path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import SessionLocal
from app.models.operational import CorpusRepo


def log_corpus_repo(
    full_name: str,
    licence: str,
    commit_count: int,
    contributors: int,
    db=None,
) -> CorpusRepo:
    """Log or update an open-source mined repository in corpus_repos table."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        repo = db.query(CorpusRepo).filter(CorpusRepo.full_name == full_name).first()
        if not repo:
            repo = CorpusRepo(
                id=str(uuid.uuid4()),
                full_name=full_name,
                licence=licence,
                commit_count=commit_count,
                contributors=contributors,
                collected_at=datetime.now(timezone.utc),
            )
            db.add(repo)
        else:
            repo.licence = licence
            repo.commit_count = commit_count
            repo.contributors = contributors

        db.commit()
        db.refresh(repo)
        print(f"Logged corpus repo: {repo.full_name} ({repo.commit_count} commits, {repo.contributors} contributors, {repo.licence})")
        return repo
    finally:
        if close_db:
            db.close()


def list_corpus_repos(db=None) -> List[Dict[str, Any]]:
    """List all mined corpus repos for model training and robustness benchmarking."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        repos = db.query(CorpusRepo).all()
        return [
            {
                "id": r.id,
                "full_name": r.full_name,
                "licence": r.licence,
                "commit_count": r.commit_count,
                "contributors": r.contributors,
                "collected_at": r.collected_at.isoformat() if r.collected_at else None,
            }
            for r in repos
        ]
    finally:
        if close_db:
            db.close()


def verify_corpus_repo(full_name: str, db=None) -> bool:
    """Check if a corpus repository exists in the database."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        repo = db.query(CorpusRepo).filter(CorpusRepo.full_name == full_name).first()
        return repo is not None
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    sample_corpus = [
        ("psf/requests", "Apache-2.0", 6540, 620),
        ("pallets/flask", "BSD-3-Clause", 4980, 580),
        ("tiangolo/fastapi", "MIT", 4200, 490),
    ]
    for fn, lic, cc, contrib in sample_corpus:
        log_corpus_repo(fn, lic, cc, contrib)
