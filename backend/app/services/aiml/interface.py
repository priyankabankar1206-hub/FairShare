"""Abstract interface for AI/ML contribution scoring service.

This interface abstracts whether the model is called as an imported Python
function (Section 6.4: "The AI/ML role ships a Python package with one function
that takes a repository and returns the JSON") or as an external HTTP microservice.

NOTE FOR AI/ML TEAMMATE:
To connect your model:
1. Provide a Python callable: `def run_fairshare_model(repo_path: str, **kwargs) -> dict`
   OR
2. Run an HTTP service matching the AIMLAnalysisRequest / AIMLAnalysisResponse schema.
"""

from abc import ABC, abstractmethod
from app.schemas.aiml_contract import AIMLAnalysisRequest, AIMLAnalysisResponse


class AIMLServiceError(Exception):
    """Base exception for AI/ML integration errors."""
    pass


class AIMLValidationError(AIMLServiceError):
    """Raised when the AI/ML output fails validation against Section 6.4 contract."""
    pass


class AIMLConnectionError(AIMLServiceError):
    """Raised when the backend cannot reach or call the AI/ML module."""
    pass


class AIMLTimeoutError(AIMLServiceError):
    """Raised when model inference times out."""
    pass


class BaseAIMLService(ABC):
    """Abstract Base Class defining the contract for AI/ML model execution."""

    @abstractmethod
    async def analyze_repository(self, request: AIMLAnalysisRequest) -> AIMLAnalysisResponse:
        """Execute model inference on a repository and return validated score report.

        Args:
            request: AIMLAnalysisRequest containing team_id and repository path/details.

        Returns:
            AIMLAnalysisResponse: Validated contribution analysis following Section 6.4.

        Raises:
            AIMLValidationError: If output JSON does not match the specification.
            AIMLConnectionError: If connection to model fails.
            AIMLTimeoutError: If execution exceeds configured timeout.
        """
        raise NotImplementedError
