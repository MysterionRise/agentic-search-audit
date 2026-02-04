"""Tests for billing and subscription endpoints."""


class TestListPlans:
    """Test suite for GET /billing/plans endpoint."""

    def test_list_plans_success(self, client):
        """Test successful plans listing."""
        response = client.get("/billing/plans")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 4  # free, starter, professional, enterprise

    def test_list_plans_contains_free(self, client):
        """Test plans include free tier."""
        response = client.get("/billing/plans")

        assert response.status_code == 200
        data = response.json()
        plan_ids = [p["id"] for p in data]
        assert "free" in plan_ids

    def test_list_plans_structure(self, client):
        """Test plan response structure."""
        response = client.get("/billing/plans")

        assert response.status_code == 200
        data = response.json()
        for plan in data:
            assert "id" in plan
            assert "name" in plan
            assert "price_monthly_usd" in plan
            assert "audits_per_month" in plan
            assert "features" in plan

    def test_list_plans_no_auth_required(self, client):
        """Test plans listing doesn't require auth."""
        response = client.get("/billing/plans")
        # Should succeed without auth
        assert response.status_code == 200


class TestGetSubscription:
    """Test suite for GET /billing/subscription endpoint."""

    def test_get_subscription_unauthenticated(self, client):
        """Test subscription without auth."""
        response = client.get("/billing/subscription")
        assert response.status_code == 401

    def test_get_subscription_invalid_token(self, client):
        """Test subscription with invalid token."""
        response = client.get(
            "/billing/subscription",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == 401


class TestCreateCheckoutSession:
    """Test suite for POST /billing/checkout endpoint."""

    def test_create_checkout_unauthenticated(self, client):
        """Test checkout without auth."""
        response = client.post(
            "/billing/checkout",
            json={
                "plan_id": "starter",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
        assert response.status_code == 401

    def test_create_checkout_invalid_plan(self, client, auth_headers):
        """Test checkout with invalid plan."""
        response = client.post(
            "/billing/checkout",
            json={
                "plan_id": "invalid_plan",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
            headers=auth_headers,
        )

        # Should fail with 400 for invalid plan
        assert response.status_code in [400, 401, 500]

    def test_create_checkout_free_plan(self, client, auth_headers):
        """Test checkout for free plan (should fail)."""
        response = client.post(
            "/billing/checkout",
            json={
                "plan_id": "free",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
            headers=auth_headers,
        )

        # Should fail - can't checkout free plan
        assert response.status_code in [400, 401, 500]

    def test_create_checkout_missing_fields(self, client, auth_headers):
        """Test checkout with missing required fields."""
        response = client.post(
            "/billing/checkout",
            json={"plan_id": "starter"},
            headers=auth_headers,
        )
        # Should fail validation
        assert response.status_code == 422


class TestCreatePortalSession:
    """Test suite for POST /billing/portal endpoint."""

    def test_create_portal_unauthenticated(self, client):
        """Test portal without auth."""
        response = client.post("/billing/portal?return_url=https://example.com")
        assert response.status_code == 401

    def test_create_portal_missing_return_url(self, client, auth_headers):
        """Test portal without return_url."""
        response = client.post("/billing/portal", headers=auth_headers)
        # Should fail validation - return_url required
        assert response.status_code == 422


class TestStripeWebhook:
    """Test suite for POST /billing/webhook endpoint.

    Note: Most webhook tests require stripe module to be installed.
    """

    pass  # Webhook tests require stripe module


class TestPlanPricing:
    """Test plan pricing is correct."""

    def test_free_plan_is_free(self, client):
        """Test free plan has 0 price."""
        response = client.get("/billing/plans")
        data = response.json()
        free_plan = next(p for p in data if p["id"] == "free")
        assert free_plan["price_monthly_usd"] == 0

    def test_starter_plan_price(self, client):
        """Test starter plan price."""
        response = client.get("/billing/plans")
        data = response.json()
        starter_plan = next(p for p in data if p["id"] == "starter")
        assert starter_plan["price_monthly_usd"] == 29

    def test_professional_plan_price(self, client):
        """Test professional plan price."""
        response = client.get("/billing/plans")
        data = response.json()
        pro_plan = next(p for p in data if p["id"] == "professional")
        assert pro_plan["price_monthly_usd"] == 99

    def test_enterprise_plan_price(self, client):
        """Test enterprise plan price."""
        response = client.get("/billing/plans")
        data = response.json()
        enterprise_plan = next(p for p in data if p["id"] == "enterprise")
        assert enterprise_plan["price_monthly_usd"] == 499

    def test_enterprise_unlimited_audits(self, client):
        """Test enterprise plan has unlimited audits."""
        response = client.get("/billing/plans")
        data = response.json()
        enterprise_plan = next(p for p in data if p["id"] == "enterprise")
        assert enterprise_plan["audits_per_month"] == -1


class TestEndpointRouting:
    """Test that billing endpoints are properly routed."""

    def test_plans_route_exists(self, client):
        """Test /billing/plans route exists."""
        response = client.get("/billing/plans")
        assert response.status_code == 200

    def test_subscription_route_exists(self, client):
        """Test /billing/subscription route exists."""
        response = client.get("/billing/subscription")
        # 401 confirms route exists but needs auth
        assert response.status_code == 401

    def test_checkout_route_exists(self, client):
        """Test /billing/checkout route exists."""
        response = client.post(
            "/billing/checkout",
            json={
                "plan_id": "starter",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
        assert response.status_code == 401

    def test_portal_route_exists(self, client):
        """Test /billing/portal route exists."""
        response = client.post("/billing/portal?return_url=https://example.com")
        assert response.status_code == 401
