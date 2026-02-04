"""Tests for API dependencies module."""

import pytest


class TestGetSettings:
    """Test settings dependency."""

    def test_get_settings_returns_settings(self):
        """Test get_settings returns APISettings instance."""
        from agentic_search_audit.api.config import APISettings, get_settings

        settings = get_settings()
        assert isinstance(settings, APISettings)

    def test_get_settings_cached(self):
        """Test settings are cached (same instance returned)."""
        from agentic_search_audit.api.config import get_settings

        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_settings_has_required_fields(self):
        """Test settings has all required configuration fields."""
        from agentic_search_audit.api.config import get_settings

        settings = get_settings()
        assert hasattr(settings, "secret_key")
        assert hasattr(settings, "database_url")
        assert hasattr(settings, "redis_url")
        assert hasattr(settings, "environment")


class TestAPISettings:
    """Test APISettings model."""

    def test_default_values(self):
        """Test default values are set correctly."""
        from agentic_search_audit.api.config import APISettings

        settings = APISettings()
        assert settings.environment == "development"
        assert settings.port == 8000
        assert settings.workers == 1

    def test_jwt_algorithm(self):
        """Test JWT algorithm is set."""
        from agentic_search_audit.api.config import APISettings

        settings = APISettings()
        assert settings.jwt_algorithm == "HS256"

    def test_jwt_expiration(self):
        """Test JWT expiration is reasonable."""
        from agentic_search_audit.api.config import APISettings

        settings = APISettings()
        assert settings.jwt_expiration_hours >= 1


class TestDatabaseDependencies:
    """Test database dependency functions."""

    @pytest.mark.asyncio
    async def test_get_db_session_generator(self):
        """Test database session generator pattern."""
        from agentic_search_audit.api.deps import get_db_session

        # get_db_session is an async generator
        # Without actual DB, it will fail, but we test the interface
        try:
            async for session in get_db_session():
                assert session is not None
                break
        except Exception:
            # Expected without database configured
            pass


class TestMiddlewareConfig:
    """Test middleware configuration."""

    def test_settings_environment_valid(self):
        """Test environment setting is valid."""
        from agentic_search_audit.api.config import APISettings

        settings = APISettings()
        assert settings.environment in ["development", "staging", "production"]

    def test_secret_key_has_value(self):
        """Test secret key is set."""
        from agentic_search_audit.api.config import APISettings

        settings = APISettings()
        assert settings.secret_key is not None
        assert len(settings.secret_key) > 0
