import os
import shutil
from pathlib import Path
from typing import Union
from sqlalchemy.orm import Session

from app.models.team import Team


class FileStorageManager:
    """
    Manages filesystem storage for repository artifacts alongside the database (Section 7.3):
    - Raw GitHub API responses: data/{team_id}/raw/
    - Cached code-change embeddings: data/{team_id}/features/{sha}.npy
    - Graph snapshots: data/{team_id}/graphs/week_{n}.pt
    - Temporary clone folders: temporary folder deleted when analysis ends
    """

    def __init__(self, base_data_dir: Union[str, Path] = "data"):
        self.base_data_dir = Path(base_data_dir).resolve()

    def get_team_root_dir(self, team_id: str) -> Path:
        return self.base_data_dir / str(team_id)

    def get_raw_dir(self, team_id: str) -> Path:
        raw_path = self.get_team_root_dir(team_id) / "raw"
        raw_path.mkdir(parents=True, exist_ok=True)
        return raw_path

    def get_features_dir(self, team_id: str) -> Path:
        feat_path = self.get_team_root_dir(team_id) / "features"
        feat_path.mkdir(parents=True, exist_ok=True)
        return feat_path

    def get_graphs_dir(self, team_id: str) -> Path:
        graphs_path = self.get_team_root_dir(team_id) / "graphs"
        graphs_path.mkdir(parents=True, exist_ok=True)
        return graphs_path

    def get_feature_file_path(self, team_id: str, commit_sha: str) -> Path:
        return self.get_features_dir(team_id) / f"{commit_sha}.npy"

    def get_graph_file_path(self, team_id: str, week: int) -> Path:
        return self.get_graphs_dir(team_id) / f"week_{week}.pt"

    def delete_team_storage(self, team_id: str) -> bool:
        """Completely remove all filesystem artifacts for a team."""
        team_dir = self.get_team_root_dir(team_id)
        if team_dir.exists() and team_dir.is_dir():
            shutil.rmtree(team_dir)
            return True
        return False


# Global default instance
storage_manager = FileStorageManager()


def delete_team_completely(db: Session, team_id: str, storage: FileStorageManager = storage_manager) -> bool:
    """
    Unified Team Deletion Service:
    Deletes relational records from PostgreSQL (cascading across all 13 dependent tables)
    AND deletes all files in data/{team_id}/ (raw responses, features, graphs).
    """
    team = db.get(Team, team_id)
    if not team:
        # Also clean up any orphan directory if it exists
        storage.delete_team_storage(team_id)
        return False

    # 1. Delete team from DB (foreign keys ON DELETE CASCADE handle all child rows)
    db.delete(team)
    db.commit()

    # 2. Delete filesystem artifacts
    storage.delete_team_storage(team_id)
    return True

