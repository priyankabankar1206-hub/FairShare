"""AI/ML Service Implementation and Adapter.

Handles dispatching analysis requests to the AI/ML module, enforcing timeouts,
handling errors, and rigorously validating raw responses against Section 6.4.
"""

from typing import Callable, Optional, Dict, Any
import json
import logging
import re
from pathlib import Path
import httpx
from pydantic import ValidationError

from app.core.config import settings

logger = logging.getLogger("fairshare.aiml")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

_SAFE_TEAM_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")
from app.schemas.aiml_contract import (
    AIMLAnalysisRequest,
    AIMLAnalysisResponse,
    validate_response_members,
)
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

    def has_model_callable(self) -> bool:
        """Return True if an in-process model callable has been registered."""
        return self._in_process_callable is not None

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

        validated_response = self.validate_raw_response(raw_result)

        try:
            validate_response_members(request, validated_response)
        except ValueError as exc:
            raise AIMLValidationError(str(exc)) from exc

        return validated_response


# Singleton factory for FastAPI dependency injection
_aiml_service_instance: Optional[AIMLIntegrationService] = None


def get_aiml_service() -> AIMLIntegrationService:
    """Retrieve singleton instance of AIMLIntegrationService."""
    global _aiml_service_instance
    if _aiml_service_instance is None:
        _aiml_service_instance = AIMLIntegrationService()
    return _aiml_service_instance


# ==============================================================================
# Analysis Result Caching Layer (Part A)
# ==============================================================================

def validate_safe_team_id(team_id: str) -> str:
    """Validate team_id against path traversal and illegal characters."""
    if not team_id or not isinstance(team_id, str):
        raise ValueError("Invalid team_id: must be a non-empty string.")
    cleaned = team_id.strip()
    if not _SAFE_TEAM_ID_REGEX.match(cleaned) or ".." in cleaned:
        raise ValueError(f"Invalid team_id '{team_id}': contains unsafe characters.")
    return cleaned


def get_analysis_cache_path(team_id: str, base_data_dir: str = "data") -> Path:
    """Resolve the filesystem path for cached analysis results."""
    safe_id = validate_safe_team_id(team_id)
    cache_dir = Path(base_data_dir) / safe_id / "analysis"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "latest_scores.json"


def save_cached_analysis(
    team_id: str,
    response: AIMLAnalysisResponse,
    base_data_dir: str = "data",
) -> Path:
    """Persist validated AIMLAnalysisResponse to cache with team_id validation."""
    safe_id = validate_safe_team_id(team_id)
    if response.team_id != safe_id:
        raise ValueError(
            f"Response team_id '{response.team_id}' does not match requested team_id '{safe_id}'."
        )
    target_path = get_analysis_cache_path(safe_id, base_data_dir=base_data_dir)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(response.model_dump(mode="json"), f, indent=2)
    logger.debug(f"[AIML Cache] Cached analysis for team '{safe_id}' at {target_path}")
    return target_path


def load_cached_analysis(
    team_id: str,
    base_data_dir: str = "data",
) -> Optional[AIMLAnalysisResponse]:
    """Retrieve and validate cached analysis from filesystem.

    Validates:
      1. team_id is safe against path traversal.
      2. File exists and parses cleanly via AIMLAnalysisResponse.
      3. Cached team_id matches requested team_id.
    """
    try:
        safe_id = validate_safe_team_id(team_id)
    except ValueError:
        return None

    target_path = Path(base_data_dir) / safe_id / "analysis" / "latest_scores.json"
    if not target_path.exists():
        return None

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        cached = AIMLAnalysisResponse.model_validate(raw_data)
        if cached.team_id != safe_id:
            logger.warning(
                f"[AIML Cache] Cache for '{safe_id}' contained mismatched team_id '{cached.team_id}'. Invalidating."
            )
            invalidate_cached_analysis(safe_id, base_data_dir=base_data_dir)
            return None
        return cached
    except Exception as exc:
        logger.warning(f"[AIML Cache] Failed to load/validate cache for '{safe_id}': {exc}")
        return None


def invalidate_cached_analysis(
    team_id: str,
    base_data_dir: str = "data",
) -> bool:
    """Safely invalidate/remove cached analysis for a team."""
    try:
        safe_id = validate_safe_team_id(team_id)
    except ValueError:
        return False

    target_path = Path(base_data_dir) / safe_id / "analysis" / "latest_scores.json"
    if target_path.exists():
        try:
            target_path.unlink()
            logger.info(f"[AIML Cache] Invalidated cached analysis for team '{safe_id}'.")
            return True
        except OSError as exc:
            logger.warning(f"[AIML Cache] Failed to delete cache file for '{safe_id}': {exc}")
            return False
    return False
