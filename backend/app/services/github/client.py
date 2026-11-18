"""GitHub Integration Service (Section 6.5 of FairShare Documentation).

Handles:
1. GitHub REST API interactions (repository metadata, pull requests, issues).
2. Pagination handling via 'Link' headers and page iterators.
3. API rate limit detection, retry-after calculations, and backoff exceptions.
4. Git repository cloning into temporary directories via GitPython.
5. In-depth commit, author, timestamp, and file change mining.
6. Safe cleanup of temporary repository clones.
"""

import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
import git
import httpx

from app.core.config import settings
from app.core.security import decrypt_token
from app.schemas.github import (
    CommitAuthor,
    FileChange,
    MinedCommit,
    PullRequestRecord,
)
from app.services.github.exceptions import (
    GitHubError,
    GitHubRateLimitError,
    GitHubRepoNotFoundError,
    GitHubAuthError,
    GitHubCloningError,
)


def parse_repo_url(repo_url: str) -> Tuple[str, str]:
    """Extract (owner, repo_name) from standard GitHub URLs or 'owner/repo' strings.

    Examples:
        - 'https://github.com/octocat/Hello-World' -> ('octocat', 'Hello-World')
        - 'https://github.com/octocat/Hello-World.git' -> ('octocat', 'Hello-World')
        - 'git@github.com:octocat/Hello-World.git' -> ('octocat', 'Hello-World')
        - 'octocat/Hello-World' -> ('octocat', 'Hello-World')
    """
    cleaned = repo_url.strip()
    # Match standard patterns
    patterns = [
        r"github\.com[/:](?P<owner>[^/]+)/(?P<repo>[^/\.]+)(?:\.git)?",
        r"^(?P<owner>[a-zA-Z0-9_\-]+)/(?P<repo>[a-zA-Z0-9_\.\-]+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            return match.group("owner"), match.group("repo")

    raise ValueError(f"Could not parse owner and repo name from repository URL: '{repo_url}'")


class GitHubService:
    """Service handling GitHub API calls and local Git mining."""

    def __init__(self, token: Optional[str] = None):
        # Support either plain token or decrypted token
        self.token = token
        self.base_url = "https://api.github.com"

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "FairShare-Backend/0.1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _check_rate_limit(self, response: httpx.Response) -> None:
        """Inspect rate limit headers and raise GitHubRateLimitError if exhausted."""
        remaining_str = response.headers.get("X-RateLimit-Remaining")
        reset_str = response.headers.get("X-RateLimit-Reset")
        retry_after_str = response.headers.get("Retry-After")

        remaining = int(remaining_str) if remaining_str and remaining_str.isdigit() else None
        reset_time = int(reset_str) if reset_str and reset_str.isdigit() else None
        retry_after = int(retry_after_str) if retry_after_str and retry_after_str.isdigit() else None

        if retry_after is None and reset_time is not None:
            now = int(time.time())
            retry_after = max(0, reset_time - now)

        if response.status_code == 429 or (
            response.status_code == 403 and (remaining == 0 or "rate limit" in response.text.lower())
        ):
            raise GitHubRateLimitError(
                message=f"GitHub API rate limit exceeded. Retry after {retry_after}s.",
                retry_after_seconds=retry_after,
                reset_timestamp=reset_time,
            )

    async def verify_repository_access(self, owner: str, repo: str) -> Dict[str, Any]:
        """Verify repository existence and accessibility."""
        url = f"{self.base_url}/repos/{owner}/{repo}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._get_headers())
            self._check_rate_limit(resp)

            if resp.status_code == 404:
                raise GitHubRepoNotFoundError(f"Repository '{owner}/{repo}' not found on GitHub.")
            if resp.status_code in {401, 403}:
                raise GitHubAuthError(f"Unauthorized access to '{owner}/{repo}': {resp.text}")
            resp.raise_for_status()
            return resp.json()

    async def fetch_pull_requests_page(
        self,
        owner: str,
        repo: str,
        page: int = 1,
        per_page: int = 30,
        state: str = "all",
    ) -> Tuple[List[PullRequestRecord], bool]:
        """Fetch a single page of Pull Requests.

        Returns:
            Tuple of (records_list, has_next_page)
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
        params = {"state": state, "per_page": per_page, "page": page}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._get_headers(), params=params)
            self._check_rate_limit(resp)
            resp.raise_for_status()

            raw_prs = resp.json()
            if not isinstance(raw_prs, list):
                return [], False

            records: List[PullRequestRecord] = []
            for pr in raw_prs:
                created_dt = datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
                merged_dt = (
                    datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
                    if pr.get("merged_at")
                    else None
                )
                user_info = pr.get("user") or {}
                author_login = user_info.get("login", "unknown")

                records.append(
                    PullRequestRecord(
                        id=pr["id"],
                        number=pr["number"],
                        title=pr.get("title", ""),
                        author_login=author_login,
                        state=pr.get("state", "open"),
                        created_at=created_dt,
                        merged_at=merged_dt,
                        comments_count=pr.get("comments", 0) + pr.get("review_comments", 0),
                    )
                )

            # Check pagination via Link header or record count
            link_header = resp.headers.get("Link", "")
            has_next = 'rel="next"' in link_header or len(raw_prs) == per_page
            return records, has_next

    def clone_repository_temporarily(self, repo_url: str, auth_token: Optional[str] = None) -> str:
        """Clone repository into a temporary folder for local Git analysis.

        Rule (Section 6.5): Cloned repositories must be deleted when analysis ends.
        """
        temp_dir = tempfile.mkdtemp(prefix="fairshare_clone_")
        target_url = repo_url
        if auth_token and "github.com" in repo_url:
            try:
                owner, repo = parse_repo_url(repo_url)
                target_url = f"https://x-access-token:{auth_token}@github.com/{owner}/{repo}.git"
            except Exception:
                target_url = repo_url

        try:
            git.Repo.clone_from(target_url, temp_dir, multi_options=["--no-single-branch"])
            return temp_dir
        except Exception as exc:
            self.cleanup_temporary_clone(temp_dir)
            raise GitHubCloningError(f"Failed to clone repository '{repo_url}': {exc}") from exc

    def cleanup_temporary_clone(self, temp_dir: str) -> None:
        """Safely delete cloned temporary repository directory."""
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

    def mine_repository_commits(
        self,
        repo_path: str,
        max_commits: Optional[int] = None,
        resume_after_sha: Optional[str] = None,
    ) -> List[MinedCommit]:
        """Mine commit history, authors, timestamps, and file changes from a local Git repository.

        Args:
            repo_path: Filesystem path to the local git clone.
            max_commits: Maximum commits to return (None for all).
            resume_after_sha: If supplied, stop mining once this SHA is reached (resumption).

        Returns:
            List of MinedCommit objects in chronological order (oldest to newest).
        """
        repo = git.Repo(repo_path)
        mined_commits: List[MinedCommit] = []

        try:
            # Iterate newest to oldest
            for commit in repo.iter_commits(max_count=max_commits):
                # If we encounter the SHA from a previous checkpoint, stop (resumption optimization)
                if resume_after_sha and commit.hexsha == resume_after_sha:
                    break

                author_date = datetime.fromtimestamp(commit.committed_date, tz=timezone.utc)
                author = CommitAuthor(
                    name=commit.author.name or "Unknown",
                    email=commit.author.email or "unknown@email.com",
                    date=author_date,
                )

                # Mine file changes
                file_changes: List[FileChange] = []
                total_adds = 0
                total_dels = 0

                try:
                    stats = commit.stats
                    total_adds = stats.total.get("insertions", 0)
                    total_dels = stats.total.get("deletions", 0)
                    for file_path, fstats in stats.files.items():
                        file_changes.append(
                            FileChange(
                                path=file_path,
                                additions=fstats.get("insertions", 0),
                                deletions=fstats.get("deletions", 0),
                                change_type="modified",
                            )
                        )
                except Exception:
                    pass

                parent_shas = [p.hexsha for p in commit.parents]

                mined_commits.append(
                    MinedCommit(
                        sha=commit.hexsha,
                        author=author,
                        message=commit.message.strip(),
                        additions=total_adds,
                        deletions=total_dels,
                        files_changed=file_changes,
                        parent_shas=parent_shas,
                    )
                )
        except Exception as exc:
            raise GitHubError(f"Error while mining git history from '{repo_path}': {exc}") from exc

        # Return chronological order (oldest -> newest)
        mined_commits.reverse()
        return mined_commits


_github_service_instance: Optional[GitHubService] = None


def get_github_service() -> GitHubService:
    global _github_service_instance
    if _github_service_instance is None:
        _github_service_instance = GitHubService()
    return _github_service_instance
