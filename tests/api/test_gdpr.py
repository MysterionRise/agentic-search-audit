"""Tests for GDPR compliance endpoints."""

from uuid import uuid4

import pytest


class TestDataExport:
    """Test suite for GET /gdpr/export endpoint."""

    def test_export_data_unauthenticated(self, client):
        """Test data export without auth."""
        response = client.get("/gdpr/export")
        assert response.status_code == 401

    def test_export_data_invalid_token(self, client):
        """Test data export with invalid token."""
        response = client.get(
            "/gdpr/export",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == 401

    def test_export_data_query_params(self, client):
        """Test export with query parameters."""
        response = client.get(
            "/gdpr/export?include_audits=true&include_reports=false"
        )
        # 401 confirms route exists and accepts params
        assert response.status_code == 401


class TestAccountDeletion:
    """Test suite for POST /gdpr/delete endpoint."""

    def test_delete_account_unauthenticated(self, client):
        """Test deletion without auth."""
        response = client.post(
            "/gdpr/delete",
            json={
                "password": "password123",
                "confirm": True,
            },
        )
        assert response.status_code == 401

    def test_delete_account_invalid_token(self, client):
        """Test deletion with invalid token."""
        response = client.post(
            "/gdpr/delete",
            json={
                "password": "password123",
                "confirm": True,
            },
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == 401

    def test_delete_account_missing_password(self, client, auth_headers):
        """Test deletion without password."""
        response = client.post(
            "/gdpr/delete",
            json={"confirm": True},
            headers=auth_headers,
        )
        # Should fail validation
        assert response.status_code == 422

    def test_delete_account_missing_confirm(self, client, auth_headers):
        """Test deletion without confirm flag."""
        response = client.post(
            "/gdpr/delete",
            json={"password": "password123"},
            headers=auth_headers,
        )
        # Should fail validation
        assert response.status_code == 422


class TestImmediateDeletion:
    """Test suite for POST /gdpr/delete/immediate endpoint."""

    def test_immediate_delete_unauthenticated(self, client):
        """Test immediate deletion without auth."""
        response = client.post(
            "/gdpr/delete/immediate",
            json={
                "password": "password123",
                "confirm": True,
            },
        )
        assert response.status_code == 401

    def test_immediate_delete_missing_fields(self, client, auth_headers):
        """Test immediate deletion without required fields."""
        response = client.post(
            "/gdpr/delete/immediate",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestConsentStatus:
    """Test suite for GET /gdpr/consent endpoint."""

    def test_get_consent_unauthenticated(self, client):
        """Test consent status without auth."""
        response = client.get("/gdpr/consent")
        assert response.status_code == 401

    def test_get_consent_invalid_token(self, client):
        """Test consent status with invalid token."""
        response = client.get(
            "/gdpr/consent",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == 401


class TestUpdateConsent:
    """Test suite for PATCH /gdpr/consent endpoint."""

    def test_update_consent_unauthenticated(self, client):
        """Test consent update without auth."""
        response = client.patch(
            "/gdpr/consent",
            json={"marketing_emails": True},
        )
        assert response.status_code == 401

    def test_update_consent_empty_body(self, client):
        """Test consent update with empty body requires auth."""
        response = client.patch(
            "/gdpr/consent",
            json={},
        )
        # Without auth, should return 401
        assert response.status_code == 401


class TestAccessLog:
    """Test suite for GET /gdpr/access-log endpoint."""

    def test_get_access_log_unauthenticated(self, client):
        """Test access log without auth."""
        response = client.get("/gdpr/access-log")
        assert response.status_code == 401

    def test_get_access_log_invalid_token(self, client):
        """Test access log with invalid token."""
        response = client.get(
            "/gdpr/access-log",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == 401

    def test_get_access_log_pagination_params(self, client):
        """Test access log with pagination parameters."""
        response = client.get("/gdpr/access-log?page=2&page_size=25")
        # 401 confirms route accepts pagination params
        assert response.status_code == 401


class TestEndpointRouting:
    """Test that GDPR endpoints are properly routed."""

    def test_export_route_exists(self, client):
        """Test /gdpr/export route exists."""
        response = client.get("/gdpr/export")
        assert response.status_code == 401

    def test_delete_route_exists(self, client):
        """Test /gdpr/delete route exists."""
        response = client.post(
            "/gdpr/delete",
            json={"password": "test", "confirm": True},
        )
        assert response.status_code == 401

    def test_delete_immediate_route_exists(self, client):
        """Test /gdpr/delete/immediate route exists."""
        response = client.post(
            "/gdpr/delete/immediate",
            json={"password": "test", "confirm": True},
        )
        assert response.status_code == 401

    def test_consent_get_route_exists(self, client):
        """Test GET /gdpr/consent route exists."""
        response = client.get("/gdpr/consent")
        assert response.status_code == 401

    def test_consent_patch_route_exists(self, client):
        """Test PATCH /gdpr/consent route exists."""
        response = client.patch("/gdpr/consent", json={})
        assert response.status_code == 401

    def test_access_log_route_exists(self, client):
        """Test /gdpr/access-log route exists."""
        response = client.get("/gdpr/access-log")
        assert response.status_code == 401
