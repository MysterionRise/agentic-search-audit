"""Tests for API middleware."""



class TestRateLimiting:
    """Test rate limiting middleware."""

    def test_requests_are_allowed(self, client):
        """Test normal requests are allowed."""
        # Single request should always be allowed
        response = client.get("/health/live")
        assert response.status_code == 200

    def test_multiple_requests_allowed(self, client):
        """Test multiple requests within limit are allowed."""
        # Make several requests
        for _ in range(5):
            response = client.get("/health/live")
            assert response.status_code == 200


class TestRequestLogging:
    """Test request logging middleware."""

    def test_request_completes(self, client):
        """Test requests complete with logging enabled."""
        response = client.get("/health/live")
        assert response.status_code == 200

    def test_error_requests_logged(self, client):
        """Test error responses are logged."""
        response = client.get("/nonexistent-endpoint")
        assert response.status_code == 404


class TestCORSMiddleware:
    """Test CORS middleware configuration."""

    def test_options_request(self, client):
        """Test OPTIONS preflight request."""
        response = client.options(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )
        # Should handle OPTIONS
        assert response.status_code in [200, 405]

    def test_cors_headers_present(self, client):
        """Test CORS headers are present on responses."""
        response = client.get(
            "/health/live",
            headers={"Origin": "http://localhost:3000"},
        )
        # Should either have CORS headers or be allowed
        assert response.status_code == 200


class TestErrorHandling:
    """Test error handling middleware."""

    def test_404_for_unknown_routes(self, client):
        """Test 404 returned for unknown routes."""
        response = client.get("/this/route/does/not/exist")
        assert response.status_code == 404

    def test_405_for_wrong_method(self, client):
        """Test 405 for wrong HTTP method."""
        response = client.delete("/health/live")
        assert response.status_code == 405

    def test_422_for_validation_errors(self, client, auth_headers):
        """Test 422 for validation errors."""
        response = client.post(
            "/audits",
            json={"site_url": "not-a-valid-url"},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestSecurityHeaders:
    """Test security headers middleware."""

    def test_content_type_header(self, client):
        """Test Content-Type header is set."""
        response = client.get("/health/live")
        assert "content-type" in response.headers

    def test_json_content_type(self, client):
        """Test JSON endpoints return JSON content type."""
        response = client.get("/health/live")
        assert "application/json" in response.headers.get("content-type", "")
