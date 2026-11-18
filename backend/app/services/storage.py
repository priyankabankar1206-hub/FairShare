
"""File Storage and Artifact Management Service (Section 7.3).

Manages filesystem storage for repository artifacts alongside PostgreSQL:
- Raw GitHub API responses: data/{team_id}/raw/
- Cached code-change embeddings: data/{team_id}/features/{sha}.npy
- Graph snapshots: data/{team_id}/graphs/week_{n}.pt
- Analysis caches: data/{team_id}/analysis/
- Research export dataset: data/research_export/ (kept strictly separate from team data)
- Temporary repository clones and orphaned clone cleanup
"""

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Union, Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.team import Team


class FileStorageManager:
    """Manages filesystem storage for team artifacts, features, and graphs."""

    def __init__(self, base_data_dir: Union[str, Path] = "data"):
        self.base_data_dir = Path(base_data_dir).resolve()
        self.research_dir = self.base_data_dir / "research_export"

    def get_team_root_dir(self, team_id: str) -> Path:
        """Return root folder for a team: data/{team_id}."""
        return self.base_data_dir / str(team_id)

    def get_raw_dir(self, team_id: str) -> Path:
        """Return and ensure raw API cache folder: data/{team_id}/raw/."""
        raw_path = self.get_team_root_dir(team_id) / "raw"
        raw_path.mkdir(parents=True, exist_ok=True)
        return raw_path

    def get_features_dir(self, team_id: str) -> Path:
        """Return and ensure commit feature embeddings folder: data/{team_id}/features/."""
        feat_path = self.get_team_root_dir(team_id) / "features"
        feat_path.mkdir(parents=True, exist_ok=True)
        return feat_path

    def get_graphs_dir(self, team_id: str) -> Path:
        """Return and ensure graph snapshot folder: data/{team_id}/graphs/."""
        graphs_path = self.get_team_root_dir(team_id) / "graphs"
        graphs_path.mkdir(parents=True, exist_ok=True)
        return graphs_path

    def get_analysis_dir(self, team_id: str) -> Path:
        """Return and ensure analysis folder: data/{team_id}/analysis/."""
        analysis_path = self.get_team_root_dir(team_id) / "analysis"
        analysis_path.mkdir(parents=True, exist_ok=True)
        return analysis_path

    def get_feature_file_path(self, team_id: str, commit_sha: str) -> Path:
        """Return path for a cached commit embedding .npy file."""
        return self.get_features_dir(team_id) / f"{commit_sha}.npy"

    def get_graph_file_path(self, team_id: str, week: int) -> Path:
        """Return path for a weekly graph snapshot .pt file."""
        return self.get_graphs_dir(team_id) / f"week_{week}.pt"

    def get_research_export_dir(self) -> Path:
        """Return dedicated directory for anonymized research exports, separated from team data."""
        self.research_dir.mkdir(parents=True, exist_ok=True)
        return self.research_dir

    def delete_team_storage(self, team_id: str) -> bool:
        """Completely remove all filesystem artifacts for a team."""
        team_dir = self.get_team_root_dir(team_id)
        if team_dir.exists() and team_dir.is_dir():
            shutil.rmtree(team_dir, ignore_errors=True)
            return True
        return False

    def cleanup_orphaned_clones(
        self,
        max_age_seconds: int = 3600,
        target_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Safely remove expired temporary repository clones.

        When target_path is supplied, only that specific directory is checked.
        Otherwise, scan the standard FairShare temporary clone locations.
        """
        now = time.time()
        cleaned: List[str] = []
        failed: List[str] = []
        errors: List[str] = []

        if target_path is not None:
            scan_items = [Path(target_path)]
        else:
            scan_roots = [
                Path(tempfile.gettempdir()),
                Path("temp_repos").resolve(),
            ]
            scan_items = [
                item
                for root in scan_roots
                if root.exists()
                for item in root.glob("fairshare_clone_*")
            ]

        for item in scan_items:
            if not item.is_dir() or not item.name.startswith("fairshare_clone_"):
                continue

            try:
                mtime = item.stat().st_mtime
                if (now - mtime) >= max_age_seconds:
                    shutil.rmtree(item)
                    cleaned.append(str(item))
            except Exception as exc:
                failed.append(str(item))
                errors.append(f"{item}: {exc}")

        return {
            "cleaned_count": len(cleaned),
            "cleaned_paths": cleaned,
            "failed_count": len(failed),
            "failed_paths": failed,
            "errors": errors,
        }


# Global default storage manager instance
storage_manager = FileStorageManager()


def delete_team_completely(
    db: Session,
    team_id: str,
    storage: FileStorageManager = storage_manager,
) -> bool:
    """Unified Team Deletion Service (Section 6.6 & 7.2):

    Deletes relational records from PostgreSQL (cascading across all 13 dependent child tables)
    AND deletes all files in data/{team_id}/ (raw responses, features, graphs).
    """
    team = db.get(Team, team_id)
    if not team:
        # Also clean up any orphan directory on disk if it exists
        storage.delete_team_storage(team_id)
        return False

    # 1. Delete team from DB (foreign keys ON DELETE CASCADE handle all child rows)
    db.delete(team)
    db.commit()

    # 2. Delete filesystem artifacts
    storage.delete_team_storage(team_id)
    return True
