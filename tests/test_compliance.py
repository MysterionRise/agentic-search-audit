"""Tests for compliance module."""

from unittest.mock import AsyncMock, MagicMock, patch
from urllib.robotparser import RobotFileParser

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
        # Mock _fetch_robots to return None (no robots.txt)
        policy._fetch_robots = AsyncMock(return_value=None)

        result = await policy.can_fetch("https://example.com/page")
        assert result is True

    @pytest.mark.asyncio
    async def test_can_fetch_with_permissive_robots(self, policy, permissive_robots_txt):
        """Test can_fetch with permissive robots.txt."""
        # Create a permissive parser
        parser = RobotFileParser()
        parser.parse(permissive_robots_txt.splitlines())

        policy._fetch_robots = AsyncMock(return_value=parser)

        result = await policy.can_fetch("https://example.com/page")
        assert result is True

    @pytest.mark.asyncio
    async def test_can_fetch_with_restrictive_robots(self, policy, restrictive_robots_txt):
        """Test can_fetch with restrictive robots.txt."""
        # Create a restrictive parser
        parser = RobotFileParser()
        parser.parse(restrictive_robots_txt.splitlines())

        policy._fetch_robots = AsyncMock(return_value=parser)

        result = await policy.can_fetch("https://example.com/page")
        assert result is False

    @pytest.mark.asyncio
    async def test_can_fetch_caches_robots_txt(self, policy, permissive_robots_txt):
        """Test that robots.txt is cached per domain."""
        # Create a parser
        parser = RobotFileParser()
        parser.parse(permissive_robots_txt.splitlines())

        mock_fetch = AsyncMock(return_value=parser)
        policy._fetch_robots = mock_fetch

        # First call should fetch
        await policy.can_fetch("https://example.com/page1")
        # Second call should use cache
        await policy.can_fetch("https://example.com/page2")

        # Should only have fetched once
        assert mock_fetch.call_count == 1
        assert "https://example.com" in policy._cache

    @pytest.mark.asyncio
    async def test_can_fetch_handles_timeout(self, policy):
        """Test that can_fetch handles timeouts gracefully."""
        # Mock _fetch_robots to return None (as it would on timeout)
        policy._fetch_robots = AsyncMock(return_value=None)

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

    @pytest.mark.asyncio
    async def test_can_fetch_different_domains_separate_cache(self, policy, permissive_robots_txt):
        """Test that different domains have separate cache entries."""
        parser = RobotFileParser()
        parser.parse(permissive_robots_txt.splitlines())

        mock_fetch = AsyncMock(return_value=parser)
        policy._fetch_robots = mock_fetch

        await policy.can_fetch("https://example.com/page")
        await policy.can_fetch("https://other.com/page")

        # Should fetch for each domain
        assert mock_fetch.call_count == 2
        assert "https://example.com" in policy._cache
        assert "https://other.com" in policy._cache

    def test_get_crawl_delay_returns_none_when_not_cached(self, policy):
        """Test get_crawl_delay returns None when domain not cached."""
        result = policy.get_crawl_delay("https://example.com")
        assert result is None


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
