"""AI/ML Service Implementation and Adapter.

Handles dispatching analysis requests to the AI/ML module, enforcing timeouts,
handling errors, and rigorously validating raw responses against Section 6.4.
"""

from typing import Callable, Optional, Dict, Any
import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.aiml_contract import AIMLAnalysisRequest, AIMLAnalysisResponse
from app.services.aiml.interface import (
    BaseAIMLService,
    AIMLServiceError,
    AIMLValidationError,
    AIMLConnectionError,
    AIMLTimeoutError,
)


class AIMLIntegrationService(BaseAIMLService):
    """Concrete AI/ML integration service.

    Supports:
    1. 'in_process': Invokes a Python function provided by the AI/ML teammate.
    2. 'http': Sends an HTTP POST to an external inference endpoint.

    DETAILS PENDING CONFIRMATION WITH AI/ML TEAMMATE:
    - [ ] Execution mode: In-process Python package vs HTTP microservice.
    - [ ] If in-process: exact package/module name (e.g., `from fairshare_ml import score_repository`).
    - [ ] If HTTP: endpoint path (defaults to `/analyze`).
    - [ ] Handling of intermediate progress callbacks during graph construction.
    """

    def __init__(
        self,
        mode: Optional[str] = None,
        service_url: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        in_process_callable: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ):
        self.mode = mode or settings.AIML_INTEGRATION_MODE
        self.service_url = service_url or settings.AIML_SERVICE_URL
        self.timeout_seconds = timeout_seconds or settings.AIML_SERVICE_TIMEOUT_SECONDS
        self._in_process_callable = in_process_callable

    def register_model_callable(self, func: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        """Register the Python function from the AI/ML teammate's package."""
        self._in_process_callable = func

    def validate_raw_response(self, raw_data: Any) -> AIMLAnalysisResponse:
        """Validate raw dictionary data against the Section 6.4 contract.

        Raises AIMLValidationError with descriptive details if parsing fails.
        """
        if not isinstance(raw_data, dict):
            raise AIMLValidationError(f"Expected JSON object/dict from AI/ML module, got {type(raw_data).__name__}")
        try:
            return AIMLAnalysisResponse.model_validate(raw_data)
        except ValidationError as val_err:
            raise AIMLValidationError(
                f"AI/ML response failed contract validation (Section 6.4): {val_err}"
            ) from val_err

    async def _call_http_service(self, request: AIMLAnalysisRequest) -> Dict[str, Any]:
        """Call external AI/ML HTTP endpoint."""
        url = f"{self.service_url.rstrip('/')}/analyze"
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
                response = await client.post(url, json=request.model_dump())
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            raise AIMLTimeoutError(
                f"AI/ML service timed out after {self.timeout_seconds}s at {url}"
            ) from exc
        except httpx.RequestError as exc:
            raise AIMLConnectionError(
                f"Could not connect to AI/ML service at {url}: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise AIMLServiceError(
                f"AI/ML service returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc

    async def _call_in_process(self, request: AIMLAnalysisRequest) -> Dict[str, Any]:
        """Call in-process registered Python function."""
        if self._in_process_callable is None:
            raise AIMLConnectionError(
                "No in-process model callable has been registered by the AI/ML teammate. "
                "Call 'register_model_callable' or set AIML_INTEGRATION_MODE='http'."
            )
        try:
            # Execute the teammate's model function
            return self._in_process_callable(request.model_dump())
        except Exception as exc:
            raise AIMLServiceError(f"Error during AI/ML model execution: {exc}") from exc

    async def analyze_repository(self, request: AIMLAnalysisRequest) -> AIMLAnalysisResponse:
        """Execute model analysis and validate response."""
        if self.mode == "http":
            raw_result = await self._call_http_service(request)
        elif self.mode == "in_process":
            raw_result = await self._call_in_process(request)
        else:
            raise AIMLServiceError(f"Unsupported AIML_INTEGRATION_MODE: '{self.mode}'")

        return self.validate_raw_response(raw_result)


# Singleton factory for FastAPI dependency injection
_aiml_service_instance: Optional[AIMLIntegrationService] = None


def get_aiml_service() -> AIMLIntegrationService:
    """Retrieve singleton instance of AIMLIntegrationService."""
    global _aiml_service_instance
    if _aiml_service_instance is None:
        _aiml_service_instance = AIMLIntegrationService()
    return _aiml_service_instance
