import os
import subprocess
from pathlib import Path


def git(args: list[str], cwd: str) -> None:
    """Run  git <args>  inside cwd, with line-ending conversion switched off."""
    subprocess.run(
        ["git"] + args,
        cwd=cwd,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.autocrlf",
            "GIT_CONFIG_VALUE_0": "false",
        },
    )


def init_repo(path: Path) -> Path:
    """Create an empty git repository at `path`."""
    path.mkdir()
    git(["init"], cwd=str(path))
    git(["config", "user.email", "ci@test.com"], cwd=str(path))
    git(["config", "user.name", "CI"], cwd=str(path))
    return path
