"""Fixtures for API tests."""

import asyncio

# Mock environment variables before importing app
import os
from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

os.environ.update(
    {
        "AUDIT_SECRET_KEY": "test-secret-key-for-testing-only",
        "AUDIT_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "AUDIT_REDIS_URL": "redis://localhost:6379/0",
        "AUDIT_ENVIRONMENT": "development",
    }
)

# Clear Prometheus registry before tests to avoid duplication errors
try:
    from prometheus_client import REGISTRY

    collectors_to_remove = []
    for name in list(REGISTRY._names_to_collectors.keys()):
        if name.startswith("http_"):
            collectors_to_remove.append(REGISTRY._names_to_collectors[name])
    for collector in collectors_to_remove:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass
except Exception:
    pass


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def clear_prometheus_registry():
    """Clear Prometheus registry before each test to avoid duplication errors."""
    try:
        from prometheus_client import REGISTRY

        collectors_to_remove = []
        for name in list(REGISTRY._names_to_collectors.keys()):
            if name.startswith("http_"):
                collectors_to_remove.append(REGISTRY._names_to_collectors[name])
        for collector in collectors_to_remove:
            try:
                REGISTRY.unregister(collector)
            except Exception:
                pass
    except Exception:
        pass
    yield


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.hgetall = AsyncMock(return_value={})
    redis.hset = AsyncMock(return_value=True)
    redis.lpush = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.zremrangebyscore = AsyncMock(return_value=0)
    redis.zcard = AsyncMock(return_value=0)
    redis.zadd = AsyncMock(return_value=1)
    redis.pipeline = MagicMock()
    redis.pipeline.return_value.execute = AsyncMock(return_value=[0, 0, 1, True])
    return redis


@pytest.fixture
def mock_user():
    """Mock user object."""
    from datetime import datetime

    class MockUser:
        id = uuid4()
        email = "test@example.com"
        name = "Test User"
        password_hash = (
            "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewKyNiAYMyzJ/IvS"  # "password123"
        )
        is_active = True
        is_admin = False
        organization_id = None
        created_at = datetime.utcnow()
        updated_at = datetime.utcnow()

    return MockUser()


@pytest.fixture
def auth_token(mock_user):
    """Generate auth token for tests."""
    from agentic_search_audit.api.config import get_settings
    from agentic_search_audit.api.routes.auth import create_access_token

    settings = get_settings()
    return create_access_token(mock_user.id, settings)


@pytest.fixture
def auth_headers(auth_token):
    """Auth headers for authenticated requests."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def app_with_mocks(mock_db_session, mock_redis, mock_user):
    """Create app with mocked dependencies."""
    with (
        patch("agentic_search_audit.api.deps._db_session_factory") as mock_factory,
        patch("agentic_search_audit.api.deps._redis_client", mock_redis),
        patch("agentic_search_audit.api.deps.get_db_session") as mock_get_db,
    ):

        async def mock_db_generator():
            yield mock_db_session

        mock_get_db.return_value = mock_db_generator()
        mock_factory.return_value.__aenter__.return_value = mock_db_session

        from agentic_search_audit.api.main import create_app

        app = create_app()
        yield app


@pytest.fixture
def client(app_with_mocks):
    """Test client with mocked dependencies."""
    return TestClient(app_with_mocks)


@pytest.fixture
async def async_client(app_with_mocks) -> AsyncGenerator:
    """Async test client."""
    async with AsyncClient(app=app_with_mocks, base_url="http://test") as ac:
        yield ac
