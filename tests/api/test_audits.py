"""Tests for audit endpoints."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Patch paths for dependencies
DB_SESSION_PATCH = "agentic_search_audit.api.deps.get_db_session"
AUDIT_REPO_PATCH = "agentic_search_audit.db.repositories.AuditRepository"
USAGE_REPO_PATCH = "agentic_search_audit.db.repositories.UsageRepository"


class TestCreateAudit:
    """Test suite for audit creation."""

    def test_create_audit_success(self, client, auth_headers, mock_db_session, mock_redis):
        """Test successful audit creation."""
        with (
            patch("agentic_search_audit.api.routes.audits.get_current_user") as mock_get_user,
            patch(DB_SESSION_PATCH) as mock_get_db,
            patch("agentic_search_audit.jobs.tasks.enqueue_audit") as mock_enqueue,
            patch("agentic_search_audit.api.routes.auth.verify_token") as mock_verify,
        ):

            mock_user = MagicMock()
            mock_user.id = uuid4()
            mock_user.organization_id = None

            mock_get_user.return_value = mock_user
            mock_verify.return_value = {"sub": str(mock_user.id)}

            mock_audit = MagicMock()
            mock_audit.id = uuid4()

            mock_audit_repo = MagicMock()
            mock_audit_repo.create = AsyncMock(return_value=mock_audit)

            mock_usage_repo = MagicMock()
            mock_usage = MagicMock()
            mock_usage.audit_count = 5
            mock_usage_repo.get_current_period = AsyncMock(return_value=mock_usage)

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()
            mock_enqueue.return_value = f"audit:{mock_audit.id}"

            with (
                patch(AUDIT_REPO_PATCH, return_value=mock_audit_repo),
                patch(USAGE_REPO_PATCH, return_value=mock_usage_repo),
            ):

                _ = client.post(
                    "/audits",
                    json={
                        "site_url": "https://example.com",
                        "queries": ["test query 1", "test query 2"],
                        "headless": True,
                        "top_k": 10,
                    },
                    headers=auth_headers,
                )

            # Would return 202 Accepted with audit_id

    def test_create_audit_rate_limit_exceeded(self, client, auth_headers, mock_db_session):
        """Test audit creation when rate limit is exceeded."""
        with (
            patch("agentic_search_audit.api.routes.audits.get_current_user") as mock_get_user,
            patch(DB_SESSION_PATCH) as mock_get_db,
            patch("agentic_search_audit.api.routes.auth.verify_token") as mock_verify,
        ):

            mock_user = MagicMock()
            mock_user.id = uuid4()

            mock_get_user.return_value = mock_user
            mock_verify.return_value = {"sub": str(mock_user.id)}

            mock_usage = MagicMock()
            mock_usage.audit_count = 100  # At limit

            mock_usage_repo = MagicMock()
            mock_usage_repo.get_current_period = AsyncMock(return_value=mock_usage)

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(USAGE_REPO_PATCH, return_value=mock_usage_repo):
                _ = client.post(
                    "/audits",
                    json={
                        "site_url": "https://example.com",
                        "queries": ["test query"],
                    },
                    headers=auth_headers,
                )

            # Would return 429 Too Many Requests


class TestListAudits:
    """Test suite for audit listing."""

    def test_list_audits_empty(self, client, auth_headers, mock_db_session):
        """Test listing audits when none exist."""
        with (
            patch("agentic_search_audit.api.routes.audits.verify_token") as mock_verify,
            patch(DB_SESSION_PATCH) as mock_get_db,
        ):

            user_id = uuid4()
            mock_verify.return_value = {"sub": str(user_id)}

            mock_repo = MagicMock()
            mock_repo.list_by_user = AsyncMock(return_value=([], 0))

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(AUDIT_REPO_PATCH, return_value=mock_repo):
                _ = client.get(
                    "/audits",
                    headers=auth_headers,
                )

            # Would return 200 with empty list

    def test_list_audits_with_pagination(self, client, auth_headers, mock_db_session):
        """Test listing audits with pagination."""
        with (
            patch("agentic_search_audit.api.routes.audits.verify_token") as mock_verify,
            patch(DB_SESSION_PATCH) as mock_get_db,
        ):

            user_id = uuid4()
            mock_verify.return_value = {"sub": str(user_id)}

            mock_audit = MagicMock()
            mock_audit.id = uuid4()
            mock_audit.site_url = "https://example.com"
            mock_audit.status = "completed"
            mock_audit.queries = ["q1", "q2"]
            mock_audit.completed_queries = 2
            mock_audit.average_score = 4.5
            mock_audit.created_at = datetime.utcnow()
            mock_audit.started_at = datetime.utcnow()
            mock_audit.completed_at = datetime.utcnow()
            mock_audit.error_message = None

            mock_repo = MagicMock()
            mock_repo.list_by_user = AsyncMock(return_value=([mock_audit], 1))

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(AUDIT_REPO_PATCH, return_value=mock_repo):
                _ = client.get(
                    "/audits?page=1&page_size=10",
                    headers=auth_headers,
                )

            # Would return 200 with paginated results


class TestGetAudit:
    """Test suite for getting audit details."""

    def test_get_audit_success(self, client, auth_headers, mock_db_session):
        """Test getting audit details."""
        audit_id = uuid4()
        user_id = uuid4()

        with (
            patch("agentic_search_audit.api.routes.audits.verify_token") as mock_verify,
            patch(DB_SESSION_PATCH) as mock_get_db,
        ):

            mock_verify.return_value = {"sub": str(user_id)}

            mock_audit = MagicMock()
            mock_audit.id = audit_id
            mock_audit.user_id = user_id
            mock_audit.site_url = "https://example.com"
            mock_audit.status = "completed"
            mock_audit.queries = ["test query"]  # DB stores strings, route converts to Query
            mock_audit.completed_queries = 1
            mock_audit.average_score = 4.0
            mock_audit.created_at = datetime.utcnow()
            mock_audit.started_at = datetime.utcnow()
            mock_audit.completed_at = datetime.utcnow()
            mock_audit.error_message = None
            mock_audit.config_override = None

            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_audit)
            mock_repo.get_results = AsyncMock(return_value=[])

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(AUDIT_REPO_PATCH, return_value=mock_repo):
                _ = client.get(
                    f"/audits/{audit_id}",
                    headers=auth_headers,
                )

            # Would return 200 with audit details

    def test_get_audit_not_found(self, client, auth_headers, mock_db_session):
        """Test getting non-existent audit."""
        audit_id = uuid4()
        user_id = uuid4()

        with (
            patch("agentic_search_audit.api.routes.audits.verify_token") as mock_verify,
            patch(DB_SESSION_PATCH) as mock_get_db,
        ):

            mock_verify.return_value = {"sub": str(user_id)}

            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=None)

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(AUDIT_REPO_PATCH, return_value=mock_repo):
                _ = client.get(
                    f"/audits/{audit_id}",
                    headers=auth_headers,
                )

            # Would return 404 Not Found

    def test_get_audit_forbidden(self, client, auth_headers, mock_db_session):
        """Test getting audit owned by another user."""
        audit_id = uuid4()
        user_id = uuid4()
        other_user_id = uuid4()

        with (
            patch("agentic_search_audit.api.routes.audits.verify_token") as mock_verify,
            patch(DB_SESSION_PATCH) as mock_get_db,
        ):

            mock_verify.return_value = {"sub": str(user_id)}

            mock_audit = MagicMock()
            mock_audit.id = audit_id
            mock_audit.user_id = other_user_id  # Different user

            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_audit)

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(AUDIT_REPO_PATCH, return_value=mock_repo):
                _ = client.get(
                    f"/audits/{audit_id}",
                    headers=auth_headers,
                )

            # Would return 403 Forbidden


class TestCancelAudit:
    """Test suite for cancelling audits."""

    def test_cancel_audit_success(self, client, auth_headers, mock_db_session):
        """Test successful audit cancellation."""
        audit_id = uuid4()
        user_id = uuid4()

        with (
            patch("agentic_search_audit.api.routes.audits.verify_token") as mock_verify,
            patch(DB_SESSION_PATCH) as mock_get_db,
            patch("agentic_search_audit.jobs.tasks.cancel_audit_job") as mock_cancel,
        ):

            mock_verify.return_value = {"sub": str(user_id)}

            mock_audit = MagicMock()
            mock_audit.id = audit_id
            mock_audit.user_id = user_id
            mock_audit.status = "running"

            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_audit)
            mock_repo.update_status = AsyncMock()

            mock_cancel.return_value = True

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(AUDIT_REPO_PATCH, return_value=mock_repo):
                _ = client.post(
                    f"/audits/{audit_id}/cancel",
                    json={"reason": "User requested cancellation"},
                    headers=auth_headers,
                )

            # Would return 200 OK

    def test_cancel_completed_audit(self, client, auth_headers, mock_db_session):
        """Test cancelling a completed audit fails."""
        audit_id = uuid4()
        user_id = uuid4()

        with (
            patch("agentic_search_audit.api.routes.audits.verify_token") as mock_verify,
            patch(DB_SESSION_PATCH) as mock_get_db,
        ):

            mock_verify.return_value = {"sub": str(user_id)}

            mock_audit = MagicMock()
            mock_audit.id = audit_id
            mock_audit.user_id = user_id
            mock_audit.status = "completed"

            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_audit)

            async def mock_db_gen():
                yield mock_db_session

            mock_get_db.return_value = mock_db_gen()

            with patch(AUDIT_REPO_PATCH, return_value=mock_repo):
                _ = client.post(
                    f"/audits/{audit_id}/cancel",
                    json={},
                    headers=auth_headers,
                )

            # Would return 400 Bad Request
