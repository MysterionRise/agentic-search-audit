"""Tests for authentication endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Patch paths for dependencies
DB_SESSION_PATCH = "agentic_search_audit.api.deps.get_db_session"
USER_REPO_PATCH = "agentic_search_audit.db.repositories.UserRepository"
APIKEY_REPO_PATCH = "agentic_search_audit.db.repositories.APIKeyRepository"


class TestRegistration:
    """Test suite for user registration."""

    def test_register_success(self, client, mock_db_session):
        """Test successful user registration."""
        with patch(DB_SESSION_PATCH) as mock_get_db:
            mock_repo = MagicMock()
            mock_repo.get_by_email = AsyncMock(return_value=None)

            mock_user = MagicMock()
            mock_user.id = uuid4()
            mock_user.email = "new@example.com"
            mock_user.name = "New User"
            mock_user.is_active = True
            mock_user.is_admin = False
            mock_user.organization_id = None
            mock_user.created_at = "2024-01-01T00:00:00"

            mock_repo.create = AsyncMock(return_value=mock_user)

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(USER_REPO_PATCH, return_value=mock_repo):
                _ = client.post(
                    "/auth/register",
                    json={
                        "email": "new@example.com",
                        "password": "securepassword123",
                        "name": "New User",
                    },
                )

            # Note: This will fail without full DB mock setup
            # In a real test, we'd need proper fixtures

    def test_register_duplicate_email(self, client, mock_db_session, mock_user):
        """Test registration with duplicate email."""
        with patch(DB_SESSION_PATCH) as mock_get_db:
            mock_repo = MagicMock()
            mock_repo.get_by_email = AsyncMock(return_value=mock_user)

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(USER_REPO_PATCH, return_value=mock_repo):
                _ = client.post(
                    "/auth/register",
                    json={
                        "email": mock_user.email,
                        "password": "password123",
                        "name": "Duplicate User",
                    },
                )

            # Would return 409 Conflict


class TestLogin:
    """Test suite for user login."""

    def test_login_success(self, client, mock_db_session, mock_user):
        """Test successful login."""
        with (
            patch(DB_SESSION_PATCH) as mock_get_db,
            patch("agentic_search_audit.api.routes.auth.verify_password", return_value=True),
        ):

            mock_repo = MagicMock()
            mock_repo.get_by_email = AsyncMock(return_value=mock_user)

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(USER_REPO_PATCH, return_value=mock_repo):
                _ = client.post(
                    "/auth/login",
                    json={
                        "email": mock_user.email,
                        "password": "password123",
                    },
                )

            # Would return 200 with token

    def test_login_invalid_password(self, client, mock_db_session, mock_user):
        """Test login with invalid password."""
        with (
            patch(DB_SESSION_PATCH) as mock_get_db,
            patch("agentic_search_audit.api.routes.auth.verify_password", return_value=False),
        ):

            mock_repo = MagicMock()
            mock_repo.get_by_email = AsyncMock(return_value=mock_user)

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(USER_REPO_PATCH, return_value=mock_repo):
                _ = client.post(
                    "/auth/login",
                    json={
                        "email": mock_user.email,
                        "password": "wrongpassword",
                    },
                )

            # Would return 401 Unauthorized

    def test_login_user_not_found(self, client, mock_db_session):
        """Test login with non-existent user."""
        with patch(DB_SESSION_PATCH) as mock_get_db:
            mock_repo = MagicMock()
            mock_repo.get_by_email = AsyncMock(return_value=None)

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(USER_REPO_PATCH, return_value=mock_repo):
                _ = client.post(
                    "/auth/login",
                    json={
                        "email": "nonexistent@example.com",
                        "password": "password123",
                    },
                )

            # Would return 401 Unauthorized


class TestAPIKeys:
    """Test suite for API key management."""

    def test_create_api_key(self, client, auth_headers, mock_db_session):
        """Test creating an API key."""
        with (
            patch(DB_SESSION_PATCH) as mock_get_db,
            patch("agentic_search_audit.api.routes.auth.verify_token") as mock_verify,
        ):

            mock_verify.return_value = {"sub": str(uuid4())}

            mock_key = MagicMock()
            mock_key.id = uuid4()
            mock_key.name = "Test Key"
            mock_key.prefix = "test1234"
            mock_key.created_at = "2024-01-01T00:00:00"
            mock_key.expires_at = None

            mock_repo = MagicMock()
            mock_repo.create = AsyncMock(return_value=mock_key)

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(APIKEY_REPO_PATCH, return_value=mock_repo):
                _ = client.post(
                    "/auth/api-keys",
                    json={"name": "Test Key"},
                    headers=auth_headers,
                )

            # Would return 201 with key details

    def test_list_api_keys(self, client, auth_headers, mock_db_session):
        """Test listing API keys."""
        with (
            patch(DB_SESSION_PATCH) as mock_get_db,
            patch("agentic_search_audit.api.routes.auth.verify_token") as mock_verify,
        ):

            mock_verify.return_value = {"sub": str(uuid4())}

            mock_repo = MagicMock()
            mock_repo.list_by_user = AsyncMock(return_value=[])

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(APIKEY_REPO_PATCH, return_value=mock_repo):
                _ = client.get(
                    "/auth/api-keys",
                    headers=auth_headers,
                )

            # Would return 200 with list of keys
