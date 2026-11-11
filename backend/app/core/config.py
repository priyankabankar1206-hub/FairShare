"""Application Configuration Settings.

Uses pydantic-settings to safely load and validate environment variables.
Sensitive values default to safe placeholders and must be set via .env in production.
"""

from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """FairShare backend settings loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # General App Settings
    APP_NAME: str = "FairShare Backend"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # CORS
    ALLOWED_ORIGINS: Union[str, List[str]] = "http://localhost:3000,http://127.0.0.1:3000"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # Security & Tokens
    SECRET_KEY: str = "insecure_dev_secret_key_change_in_production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Fernet encryption key for storing tokens securely at rest (Section 6.6)
    FERNET_KEY: str = "placeholder_fernet_key_override_in_env"

    # Database Configuration (Placeholder until database teammate provides schema & credentials)
    DATABASE_URL: str = "postgresql://fairshare_user:placeholder_password@localhost:5432/fairshare_db"

    # GitHub OAuth / GitHub App Credentials
    GITHUB_CLIENT_ID: str = "placeholder_client_id"
    GITHUB_CLIENT_SECRET: str = "placeholder_client_secret"
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/github/callback"

    # AI/ML Integration Settings
    # NOTE: To be confirmed with AI/ML teammate:
    # 'in_process' (direct Python function package import) vs 'http' (separate inference server)
    AIML_INTEGRATION_MODE: str = "in_process"
    AIML_SERVICE_URL: str = "http://localhost:8500"
    AIML_SERVICE_TIMEOUT_SECONDS: int = 60


settings = Settings()
