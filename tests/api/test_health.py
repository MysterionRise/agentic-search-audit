"""Tests for health check endpoints."""

from unittest.mock import patch


class TestHealthEndpoints:
    """Test suite for health check endpoints."""

    def test_liveness_probe(self, client):
        """Test liveness probe returns 200."""
        response = client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"

    def test_readiness_probe_healthy(self, client, mock_db_session, mock_redis):
        """Test readiness probe when all services are healthy."""
        with (
            patch("agentic_search_audit.api.routes.health.check_database") as mock_db,
            patch("agentic_search_audit.api.routes.health.check_redis") as mock_redis_check,
        ):

            from agentic_search_audit.api.schemas import ComponentHealth

            mock_db.return_value = ComponentHealth(status="healthy", latency_ms=1.0, message=None)
            mock_redis_check.return_value = ComponentHealth(
                status="healthy", latency_ms=1.0, message=None
            )

            response = client.get("/health/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"

    def test_health_check_full(self, client, mock_db_session, mock_redis):
        """Test full health check endpoint."""
        with (
            patch("agentic_search_audit.api.routes.health.check_database") as mock_db,
            patch("agentic_search_audit.api.routes.health.check_redis") as mock_redis_check,
        ):

            from agentic_search_audit.api.schemas import ComponentHealth

            mock_db.return_value = ComponentHealth(status="healthy", latency_ms=5.0, message=None)
            mock_redis_check.return_value = ComponentHealth(
                status="healthy", latency_ms=2.0, message=None
            )

            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "healthy"
            assert "version" in data
            assert "timestamp" in data
            assert "checks" in data
            assert "database" in data["checks"]
            assert "redis" in data["checks"]

    def test_health_check_degraded(self, client):
        """Test health check when a service is degraded."""
        with (
            patch("agentic_search_audit.api.routes.health.check_database") as mock_db,
            patch("agentic_search_audit.api.routes.health.check_redis") as mock_redis_check,
        ):

            from agentic_search_audit.api.schemas import ComponentHealth

            mock_db.return_value = ComponentHealth(status="healthy", latency_ms=5.0, message=None)
            mock_redis_check.return_value = ComponentHealth(
                status="unhealthy",
                latency_ms=None,
                message="Connection refused",
            )

            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "unhealthy"


class TestMetricsEndpoint:
    """Test suite for Prometheus metrics endpoint."""

    def test_metrics_endpoint(self, client):
        """Test metrics endpoint returns Prometheus format."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")
        # Should contain Prometheus metric format
        content = response.text
        assert "http_requests_total" in content or "python_gc" in content
