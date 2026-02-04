"""Tests for user management endpoints."""

from datetime import datetime
from uuid import uuid4

import pytest


class TestGetCurrentUserProfile:
    """Test suite for GET /users/me endpoint."""

    def test_get_profile_unauthenticated(self, client):
        """Test profile retrieval without auth."""
        response = client.get("/users/me")
        assert response.status_code == 401

    def test_get_profile_invalid_token(self, client):
        """Test profile retrieval with invalid token."""
        response = client.get(
            "/users/me",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == 401


class TestUpdateCurrentUser:
    """Test suite for PATCH /users/me endpoint."""

    def test_update_unauthenticated(self, client):
        """Test update without auth."""
        response = client.patch("/users/me", json={"name": "New Name"})
        assert response.status_code == 401

    def test_update_invalid_token(self, client):
        """Test update with invalid token."""
        response = client.patch(
            "/users/me",
            json={"name": "New Name"},
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == 401


class TestGetUsage:
    """Test suite for GET /users/me/usage endpoint."""

    def test_get_usage_unauthenticated(self, client):
        """Test usage retrieval without auth."""
        response = client.get("/users/me/usage")
        assert response.status_code == 401

    def test_get_usage_invalid_token(self, client):
        """Test usage retrieval with invalid token."""
        response = client.get(
            "/users/me/usage",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == 401


class TestCreateOrganization:
    """Test suite for POST /users/organizations endpoint."""

    def test_create_organization_unauthenticated(self, client):
        """Test organization creation without auth."""
        response = client.post(
            "/users/organizations",
            json={"name": "New Organization"},
        )
        assert response.status_code == 401

    def test_create_organization_invalid_token(self, client):
        """Test organization creation with invalid token."""
        response = client.post(
            "/users/organizations",
            json={"name": "New Organization"},
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == 401

    def test_create_organization_missing_name(self, client, auth_headers):
        """Test organization creation without name."""
        response = client.post(
            "/users/organizations",
            json={},
            headers=auth_headers,
        )
        # Should fail validation
        assert response.status_code == 422


class TestGetOrganization:
    """Test suite for GET /users/organizations/{org_id} endpoint."""

    def test_get_organization_unauthenticated(self, client):
        """Test organization retrieval without auth."""
        response = client.get(f"/users/organizations/{uuid4()}")
        assert response.status_code == 401

    def test_get_organization_invalid_uuid(self, client, auth_headers):
        """Test organization retrieval with invalid UUID."""
        response = client.get(
            "/users/organizations/not-a-uuid",
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestEndpointRouting:
    """Test that endpoints are properly routed."""

    def test_users_me_route_exists(self, client):
        """Test /users/me route exists."""
        response = client.get("/users/me")
        # 401 means route exists but needs auth
        assert response.status_code == 401

    def test_users_me_usage_route_exists(self, client):
        """Test /users/me/usage route exists."""
        response = client.get("/users/me/usage")
        assert response.status_code == 401

    def test_users_organizations_route_exists(self, client):
        """Test /users/organizations route exists."""
        response = client.post("/users/organizations", json={"name": "Test"})
        assert response.status_code == 401

    def test_users_patch_me_route_exists(self, client):
        """Test PATCH /users/me route exists."""
        response = client.patch("/users/me", json={"name": "Test"})
        assert response.status_code == 401
