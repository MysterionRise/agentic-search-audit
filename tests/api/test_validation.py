"""Tests for API input validation using Pydantic schemas."""

import pytest
from pydantic import ValidationError

from agentic_search_audit.api.schemas import (
    APIKeyCreate,
    AuditCancelRequest,
    AuditCreateRequest,
    OrganizationCreate,
    UserCreate,
    UserLogin,
)


class TestAuditCreateRequestValidation:
    """Tests for AuditCreateRequest schema validation."""

    def test_valid_minimal_request(self):
        """Test valid request with minimal fields."""
        request = AuditCreateRequest(
            site_url="https://example.com",
            queries=["test query"],
        )
        assert str(request.site_url) == "https://example.com/"
        assert request.queries == ["test query"]
        assert request.headless is True
        assert request.top_k == 10
        assert request.webhook_url is None

    def test_valid_full_request(self):
        """Test valid request with all fields."""
        request = AuditCreateRequest(
            site_url="https://example.com/search",
            queries=["query1", "query2", "query3"],
            config_override={"timeout": 30},
            headless=False,
            top_k=20,
            webhook_url="https://webhook.example.com/callback",
        )
        assert "example.com" in str(request.site_url)
        assert len(request.queries) == 3
        assert request.config_override == {"timeout": 30}
        assert request.headless is False
        assert request.top_k == 20
        assert request.webhook_url is not None

    def test_invalid_site_url_not_url(self):
        """Test that non-URL site_url is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AuditCreateRequest(
                site_url="not-a-url",
                queries=["test"],
            )
        errors = exc_info.value.errors()
        assert len(errors) >= 1
        assert any("url" in str(e).lower() for e in errors)

    def test_invalid_site_url_missing_scheme(self):
        """Test that URL without scheme is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AuditCreateRequest(
                site_url="example.com",
                queries=["test"],
            )
        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_invalid_queries_empty_list(self):
        """Test that empty queries list is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AuditCreateRequest(
                site_url="https://example.com",
                queries=[],
            )
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "queries" in errors[0]["loc"]

    def test_invalid_queries_too_many(self):
        """Test that more than 100 queries is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AuditCreateRequest(
                site_url="https://example.com",
                queries=[f"query{i}" for i in range(101)],
            )
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "queries" in errors[0]["loc"]

    def test_queries_at_max_limit(self):
        """Test that exactly 100 queries is accepted."""
        request = AuditCreateRequest(
            site_url="https://example.com",
            queries=[f"query{i}" for i in range(100)],
        )
        assert len(request.queries) == 100

    def test_invalid_top_k_zero(self):
        """Test that top_k=0 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AuditCreateRequest(
                site_url="https://example.com",
                queries=["test"],
                top_k=0,
            )
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "top_k" in errors[0]["loc"]

    def test_invalid_top_k_negative(self):
        """Test that negative top_k is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AuditCreateRequest(
                site_url="https://example.com",
                queries=["test"],
                top_k=-1,
            )
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "top_k" in errors[0]["loc"]

    def test_invalid_top_k_too_large(self):
        """Test that top_k > 50 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AuditCreateRequest(
                site_url="https://example.com",
                queries=["test"],
                top_k=51,
            )
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "top_k" in errors[0]["loc"]

    def test_top_k_at_limits(self):
        """Test that top_k at min and max limits is accepted."""
        request_min = AuditCreateRequest(
            site_url="https://example.com",
            queries=["test"],
            top_k=1,
        )
        assert request_min.top_k == 1

        request_max = AuditCreateRequest(
            site_url="https://example.com",
            queries=["test"],
            top_k=50,
        )
        assert request_max.top_k == 50

    def test_invalid_webhook_url(self):
        """Test that invalid webhook_url is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AuditCreateRequest(
                site_url="https://example.com",
                queries=["test"],
                webhook_url="not-a-url",
            )
        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_missing_required_fields(self):
        """Test that missing required fields are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AuditCreateRequest()
        errors = exc_info.value.errors()
        # Should have errors for site_url and queries
        assert len(errors) >= 2

    def test_missing_site_url(self):
        """Test that missing site_url is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AuditCreateRequest(queries=["test"])
        errors = exc_info.value.errors()
        assert any("site_url" in str(e["loc"]) for e in errors)

    def test_missing_queries(self):
        """Test that missing queries is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AuditCreateRequest(site_url="https://example.com")
        errors = exc_info.value.errors()
        assert any("queries" in str(e["loc"]) for e in errors)


class TestAuditCancelRequestValidation:
    """Tests for AuditCancelRequest schema validation."""

    def test_valid_with_reason(self):
        """Test valid request with reason."""
        request = AuditCancelRequest(reason="No longer needed")
        assert request.reason == "No longer needed"

    def test_valid_without_reason(self):
        """Test valid request without reason."""
        request = AuditCancelRequest()
        assert request.reason is None

    def test_valid_empty_request(self):
        """Test valid empty request body."""
        request = AuditCancelRequest.model_validate({})
        assert request.reason is None


class TestUserCreateValidation:
    """Tests for UserCreate schema validation."""

    def test_valid_user(self):
        """Test valid user creation."""
        user = UserCreate(
            email="test@example.com",
            name="Test User",
            password="securepassword123",
        )
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.password == "securepassword123"

    def test_valid_user_without_name(self):
        """Test valid user creation without optional name."""
        user = UserCreate(
            email="test@example.com",
            password="securepassword123",
        )
        assert user.email == "test@example.com"
        assert user.name is None

    def test_invalid_password_too_short(self):
        """Test that password shorter than 8 characters is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(
                email="test@example.com",
                password="short",
            )
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "password" in errors[0]["loc"]

    def test_password_at_minimum_length(self):
        """Test that password with exactly 8 characters is accepted."""
        user = UserCreate(
            email="test@example.com",
            password="12345678",
        )
        assert len(user.password) == 8

    def test_missing_email(self):
        """Test that missing email is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(password="securepassword123")
        errors = exc_info.value.errors()
        assert any("email" in str(e["loc"]) for e in errors)

    def test_missing_password(self):
        """Test that missing password is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(email="test@example.com")
        errors = exc_info.value.errors()
        assert any("password" in str(e["loc"]) for e in errors)


class TestUserLoginValidation:
    """Tests for UserLogin schema validation."""

    def test_valid_login(self):
        """Test valid login request."""
        login = UserLogin(
            email="test@example.com",
            password="mypassword",
        )
        assert login.email == "test@example.com"
        assert login.password == "mypassword"

    def test_missing_email(self):
        """Test that missing email is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            UserLogin(password="mypassword")
        errors = exc_info.value.errors()
        assert any("email" in str(e["loc"]) for e in errors)

    def test_missing_password(self):
        """Test that missing password is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            UserLogin(email="test@example.com")
        errors = exc_info.value.errors()
        assert any("password" in str(e["loc"]) for e in errors)


class TestAPIKeyCreateValidation:
    """Tests for APIKeyCreate schema validation."""

    def test_valid_api_key(self):
        """Test valid API key creation."""
        key = APIKeyCreate(name="My API Key")
        assert key.name == "My API Key"
        assert key.expires_at is None

    def test_valid_api_key_with_expiry(self):
        """Test valid API key creation with expiry."""
        from datetime import datetime, timedelta

        expiry = datetime.now() + timedelta(days=30)
        key = APIKeyCreate(name="My API Key", expires_at=expiry)
        assert key.name == "My API Key"
        assert key.expires_at == expiry

    def test_invalid_name_empty(self):
        """Test that empty name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            APIKeyCreate(name="")
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "name" in errors[0]["loc"]

    def test_invalid_name_too_long(self):
        """Test that name longer than 100 characters is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            APIKeyCreate(name="a" * 101)
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "name" in errors[0]["loc"]

    def test_name_at_max_length(self):
        """Test that name with exactly 100 characters is accepted."""
        key = APIKeyCreate(name="a" * 100)
        assert len(key.name) == 100

    def test_name_at_min_length(self):
        """Test that name with exactly 1 character is accepted."""
        key = APIKeyCreate(name="a")
        assert len(key.name) == 1


class TestOrganizationValidation:
    """Tests for Organization schema validation."""

    def test_valid_organization(self):
        """Test valid organization creation."""
        org = OrganizationCreate(name="My Company")
        assert org.name == "My Company"

    def test_invalid_name_empty(self):
        """Test that empty name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            OrganizationCreate(name="")
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "name" in errors[0]["loc"]

    def test_invalid_name_too_long(self):
        """Test that name longer than 200 characters is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            OrganizationCreate(name="a" * 201)
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "name" in errors[0]["loc"]

    def test_name_at_max_length(self):
        """Test that name with exactly 200 characters is accepted."""
        org = OrganizationCreate(name="a" * 200)
        assert len(org.name) == 200

    def test_name_at_min_length(self):
        """Test that name with exactly 1 character is accepted."""
        org = OrganizationCreate(name="a")
        assert len(org.name) == 1


class TestEdgeCases:
    """Tests for edge cases and special values."""

    def test_audit_request_with_unicode_queries(self):
        """Test that unicode queries are accepted."""
        request = AuditCreateRequest(
            site_url="https://example.com",
            queries=["日本語", "中文", "한국어", "emoji 🔍"],
        )
        assert len(request.queries) == 4
        assert "日本語" in request.queries

    def test_audit_request_with_special_characters_in_url(self):
        """Test URL with query parameters."""
        request = AuditCreateRequest(
            site_url="https://example.com/search?q=test&lang=en",
            queries=["test"],
        )
        assert "search" in str(request.site_url)

    def test_user_create_with_unicode_name(self):
        """Test that unicode names are accepted."""
        user = UserCreate(
            email="test@example.com",
            name="用户名 Пользователь",
            password="securepassword123",
        )
        assert user.name == "用户名 Пользователь"

    def test_api_key_name_with_special_characters(self):
        """Test API key name with special characters."""
        key = APIKeyCreate(name="Test Key - Production (v2.0)")
        assert key.name == "Test Key - Production (v2.0)"

    def test_whitespace_handling_queries(self):
        """Test that whitespace-only queries are accepted (validation at schema level)."""
        # Note: Schema accepts them, business logic may reject
        request = AuditCreateRequest(
            site_url="https://example.com",
            queries=["   ", "\t", "\n"],
        )
        assert len(request.queries) == 3

    def test_extremely_long_query(self):
        """Test that very long query strings are accepted at schema level."""
        long_query = "a" * 10000
        request = AuditCreateRequest(
            site_url="https://example.com",
            queries=[long_query],
        )
        assert len(request.queries[0]) == 10000


class TestTypeCoercion:
    """Tests for type coercion behavior."""

    def test_top_k_from_string(self):
        """Test that string numbers are coerced to int."""
        # Pydantic v2 coerces by default
        request = AuditCreateRequest.model_validate(
            {
                "site_url": "https://example.com",
                "queries": ["test"],
                "top_k": "25",
            }
        )
        assert request.top_k == 25

    def test_headless_from_string(self):
        """Test that string booleans are coerced."""
        request = AuditCreateRequest.model_validate(
            {
                "site_url": "https://example.com",
                "queries": ["test"],
                "headless": "false",
            }
        )
        assert request.headless is False

    def test_invalid_type_for_queries(self):
        """Test that non-list queries are rejected."""
        with pytest.raises(ValidationError):
            AuditCreateRequest.model_validate(
                {
                    "site_url": "https://example.com",
                    "queries": "single query string",
                }
            )

    def test_invalid_type_for_top_k(self):
        """Test that non-numeric top_k is rejected."""
        with pytest.raises(ValidationError):
            AuditCreateRequest.model_validate(
                {
                    "site_url": "https://example.com",
                    "queries": ["test"],
                    "top_k": "not a number",
                }
            )
