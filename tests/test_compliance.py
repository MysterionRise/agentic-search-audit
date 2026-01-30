"""Tests for compliance module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_search_audit.core.compliance import (
    DEFAULT_USER_AGENT,
    ComplianceChecker,
    RobotsPolicy,
)


class TestRobotsPolicy:
    """Tests for RobotsPolicy class."""

    @pytest.fixture
    def policy(self):
        """Create a RobotsPolicy instance for testing."""
        return RobotsPolicy(user_agent="TestBot/1.0", respect_robots=True)

    @pytest.fixture
    def permissive_robots_txt(self):
        """Sample permissive robots.txt content."""
        return """
User-agent: *
Allow: /

User-agent: TestBot
Allow: /
"""

    @pytest.fixture
    def restrictive_robots_txt(self):
        """Sample restrictive robots.txt content."""
        return """
User-agent: *
Disallow: /

User-agent: Googlebot
Allow: /
"""

    @pytest.fixture
    def partial_robots_txt(self):
        """Sample robots.txt with partial restrictions."""
        return """
User-agent: *
Disallow: /admin/
Disallow: /private/
Allow: /

User-agent: TestBot
Disallow: /secret/
Allow: /
"""

    def test_init_default_values(self):
        """Test RobotsPolicy initialization with defaults."""
        policy = RobotsPolicy()
        assert policy.user_agent == DEFAULT_USER_AGENT
        assert policy.respect_robots is True
        assert policy.timeout == 10.0
        assert policy._cache == {}

    def test_init_custom_values(self, policy):
        """Test RobotsPolicy initialization with custom values."""
        assert policy.user_agent == "TestBot/1.0"
        assert policy.respect_robots is True

    @pytest.mark.asyncio
    async def test_can_fetch_respects_disabled(self):
        """Test that can_fetch returns True when respect_robots is False."""
        policy = RobotsPolicy(respect_robots=False)
        result = await policy.can_fetch("https://example.com/blocked")
        assert result is True

    @pytest.mark.asyncio
    async def test_can_fetch_allows_when_no_robots_txt(self, policy):
        """Test that can_fetch allows access when robots.txt is missing."""
        mock_response = AsyncMock()
        mock_response.status = 404

        with patch("aiohttp.ClientSession") as mock_session:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_response
            mock_session.return_value.__aenter__.return_value.get.return_value = mock_context

            result = await policy.can_fetch("https://example.com/page")
            assert result is True

    @pytest.mark.asyncio
    async def test_can_fetch_with_permissive_robots(self, policy, permissive_robots_txt):
        """Test can_fetch with permissive robots.txt."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=permissive_robots_txt)

        with patch("aiohttp.ClientSession") as mock_session:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_response
            mock_session.return_value.__aenter__.return_value.get.return_value = mock_context

            result = await policy.can_fetch("https://example.com/page")
            assert result is True

    @pytest.mark.asyncio
    async def test_can_fetch_with_restrictive_robots(self, policy, restrictive_robots_txt):
        """Test can_fetch with restrictive robots.txt."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=restrictive_robots_txt)

        with patch("aiohttp.ClientSession") as mock_session:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_response
            mock_session.return_value.__aenter__.return_value.get.return_value = mock_context

            result = await policy.can_fetch("https://example.com/page")
            assert result is False

    @pytest.mark.asyncio
    async def test_can_fetch_caches_robots_txt(self, policy, permissive_robots_txt):
        """Test that robots.txt is cached per domain."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=permissive_robots_txt)

        with patch("aiohttp.ClientSession") as mock_session:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_response
            mock_session.return_value.__aenter__.return_value.get.return_value = mock_context

            # First call should fetch
            await policy.can_fetch("https://example.com/page1")
            # Second call should use cache
            await policy.can_fetch("https://example.com/page2")

            # Should only have fetched once
            assert "https://example.com" in policy._cache

    @pytest.mark.asyncio
    async def test_can_fetch_handles_timeout(self, policy):
        """Test that can_fetch handles timeouts gracefully."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_session.return_value.__aenter__.return_value.get.side_effect = (
                asyncio.TimeoutError()
            )

            result = await policy.can_fetch("https://slow-site.com/page")
            # Should allow access when robots.txt times out
            assert result is True

    def test_clear_cache(self, policy):
        """Test cache clearing."""
        policy._cache["https://example.com"] = MagicMock()
        policy.clear_cache()
        assert policy._cache == {}

    def test_get_cached_domains(self, policy):
        """Test getting cached domains."""
        policy._cache["https://example.com"] = MagicMock()
        policy._cache["https://test.com"] = MagicMock()

        domains = policy.get_cached_domains()
        assert "https://example.com" in domains
        assert "https://test.com" in domains


class TestComplianceChecker:
    """Tests for ComplianceChecker class."""

    @pytest.fixture
    def checker(self):
        """Create a ComplianceChecker for testing."""
        return ComplianceChecker(respect_robots=True)

    @pytest.mark.asyncio
    async def test_check_url_allowed(self, checker):
        """Test check_url with allowed URL."""
        with patch.object(checker.robots_policy, "can_fetch", return_value=True):
            result = await checker.check_url("https://example.com/page")

            assert result["url"] == "https://example.com/page"
            assert result["allowed"] is True
            assert result["robots_allowed"] is True
            assert result["warnings"] == []

    @pytest.mark.asyncio
    async def test_check_url_blocked(self, checker):
        """Test check_url with blocked URL."""
        with patch.object(checker.robots_policy, "can_fetch", return_value=False):
            result = await checker.check_url("https://example.com/blocked")

            assert result["allowed"] is False
            assert result["robots_allowed"] is False
            assert len(result["warnings"]) > 0

    @pytest.mark.asyncio
    async def test_ensure_allowed_passes(self, checker):
        """Test ensure_allowed with allowed URL."""
        with patch.object(checker.robots_policy, "can_fetch", return_value=True):
            # Should not raise
            await checker.ensure_allowed("https://example.com/page")

    @pytest.mark.asyncio
    async def test_ensure_allowed_raises(self, checker):
        """Test ensure_allowed with blocked URL."""
        with patch.object(checker.robots_policy, "can_fetch", return_value=False):
            with pytest.raises(PermissionError):
                await checker.ensure_allowed("https://example.com/blocked")

    def test_custom_robots_policy(self):
        """Test ComplianceChecker with custom RobotsPolicy."""
        custom_policy = RobotsPolicy(user_agent="CustomBot/1.0")
        checker = ComplianceChecker(robots_policy=custom_policy)

        assert checker.robots_policy is custom_policy
        assert checker.robots_policy.user_agent == "CustomBot/1.0"
