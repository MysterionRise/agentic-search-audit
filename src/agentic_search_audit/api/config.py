"""API configuration settings."""

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Marker for insecure default - used to detect if secret_key was not set
_INSECURE_DEFAULT_MARKER = "INSECURE_DEFAULT_CHANGE_ME"


class APISettings(BaseSettings):
    """API configuration from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="AUDIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application settings
    app_name: str = Field(default="Agentic Search Audit API")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)
    environment: Literal["development", "staging", "production"] = Field(default="development")

    # Server settings
    host: str = Field(default="0.0.0.0")  # nosec B104 - intentional for container deployment
    port: int = Field(default=8000)
    workers: int = Field(default=1)

    # Security
    secret_key: str = Field(
        default=_INSECURE_DEFAULT_MARKER,
        description="Secret key for JWT signing. MUST be set in production.",
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiration_hours: int = Field(default=24)
    api_key_header: str = Field(default="X-API-Key")

    @model_validator(mode="after")
    def validate_secret_key_in_production(self) -> "APISettings":
        """Ensure secret_key is properly set in production environments."""
        if self.environment == "production":
            if self.secret_key == _INSECURE_DEFAULT_MARKER:
                raise ValueError(
                    "AUDIT_SECRET_KEY environment variable must be set in production. "
                    "Generate a secure key with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
                )
            # Warn if key seems too short or weak
            if len(self.secret_key) < 32:
                raise ValueError(
                    "AUDIT_SECRET_KEY is too short. Use at least 32 characters for production."
                )
        elif self.secret_key == _INSECURE_DEFAULT_MARKER:
            # In development, generate a random key if not set (but warn)
            import logging

            logging.getLogger(__name__).warning(
                "Using auto-generated secret key for development. "
                "Set AUDIT_SECRET_KEY for consistent sessions across restarts."
            )
            # Generate a random key for this session
            object.__setattr__(self, "secret_key", secrets.token_urlsafe(32))
        return self

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/audit_db",
        description="PostgreSQL connection URL",
    )
    database_pool_size: int = Field(default=5)
    database_max_overflow: int = Field(default=10)

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for job queue",
    )
    redis_job_ttl: int = Field(default=86400, description="Job TTL in seconds (24h)")

    # Rate limiting
    rate_limit_requests: int = Field(default=100, description="Requests per window")
    rate_limit_window: int = Field(default=3600, description="Window in seconds (1h)")

    # CORS
    cors_origins: list[str] = Field(default=["http://localhost:3000", "http://localhost:8000"])

    # LLM settings (from env)
    openai_api_key: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)
    openrouter_api_key: str | None = Field(default=None)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"


@lru_cache
def get_settings() -> APISettings:
    """Get cached settings instance."""
    return APISettings()
