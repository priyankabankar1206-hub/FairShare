"""Custom exceptions for GitHub integration and API error handling."""

from typing import Optional


class GitHubError(Exception):
    """Base exception for GitHub API and Git operations."""
    pass


class GitHubRateLimitError(GitHubError):
    """Raised when GitHub API rate limit is exceeded (HTTP 429 or 403 secondary limit)."""

    def __init__(
        self,
        message: str = "GitHub API rate limit exceeded.",
        retry_after_seconds: Optional[int] = None,
        reset_timestamp: Optional[int] = None,
    ):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.reset_timestamp = reset_timestamp


class GitHubRepoNotFoundError(GitHubError):
    """Raised when repository does not exist or user lacks access."""
    pass


class GitHubAuthError(GitHubError):
    """Raised when authentication credentials are invalid or missing."""
    pass


class GitHubCloningError(GitHubError):
    """Raised when Git repository cloning fails."""
    pass
