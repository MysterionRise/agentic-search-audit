"""Extended tests for health check endpoints."""


class TestHealthEndpoints:
    """Test suite for health check endpoints."""

    def test_liveness_probe(self, client):
        """Test /health/live endpoint."""
        response = client.get("/health/live")
        # Should return 200 with status
        assert response.status_code == 200

    def test_readiness_probe(self, client):
        """Test /health/ready endpoint."""
        response = client.get("/health/ready")
        # May fail without DB/Redis, but endpoint should exist
        assert response.status_code in [200, 503]

    def test_health_root(self, client):
        """Test /health endpoint."""
        response = client.get("/health")
        assert response.status_code in [200, 503]

    def test_liveness_returns_json(self, client):
        """Test liveness response is JSON."""
        response = client.get("/health/live")
        # Should return JSON
        assert "application/json" in response.headers.get("content-type", "")

    def test_readiness_checks_dependencies(self, client):
        """Test readiness endpoint checks dependencies."""
        response = client.get("/health/ready")
        if response.status_code == 200:
            data = response.json()
            assert "status" in data

    def test_health_no_auth_required(self, client):
        """Test health endpoints don't require authentication."""
        # All health endpoints should be public
        for endpoint in ["/health", "/health/live", "/health/ready"]:
            response = client.get(endpoint)
            assert response.status_code != 401


class TestHealthResponseFormat:
    """Test health response format."""

    def test_live_returns_json(self, client):
        """Test /health/live returns JSON."""
        response = client.get("/health/live")
        assert "application/json" in response.headers.get("content-type", "")

    def test_ready_returns_json(self, client):
        """Test /health/ready returns JSON."""
        response = client.get("/health/ready")
        assert "application/json" in response.headers.get("content-type", "")
