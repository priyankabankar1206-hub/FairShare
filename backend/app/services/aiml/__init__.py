"""AI/ML Integration Package.

Provides interface contracts and adapters to connect the backend with the AI/ML
model package (FairShare-Lite / FairShare-Net).
"""

from app.services.aiml.interface import (
    BaseAIMLService,
    AIMLServiceError,
    AIMLValidationError,
    AIMLConnectionError,
    AIMLTimeoutError,
)
from app.services.aiml.service import AIMLIntegrationService, get_aiml_service

__all__ = [
    "BaseAIMLService",
    "AIMLServiceError",
    "AIMLValidationError",
    "AIMLConnectionError",
    "AIMLTimeoutError",
    "AIMLIntegrationService",
    "get_aiml_service",
]
