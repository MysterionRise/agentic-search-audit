"""Robots.txt compliance and crawling policies."""

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import aiohttp

logger = logging.getLogger(__name__)

# Default user agent for robots.txt checks
DEFAULT_USER_AGENT = "AgenticSearchAudit/1.0"


class RobotsPolicy:
    """Manages robots.txt compliance for crawled domains.

    Caches robots.txt parsers per domain to avoid repeated fetches.
    """

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        respect_robots: bool = True,
        timeout: float = 10.0,
    ):
        """Initialize robots policy checker.

        Args:
            user_agent: User agent string for robots.txt checks
            respect_robots: Whether to enforce robots.txt rules
            timeout: Timeout for fetching robots.txt in seconds
        """
        self.user_agent = user_agent
        self.respect_robots = respect_robots
        self.timeout = timeout
        self._cache: dict[str, RobotFileParser | None] = {}
        self._fetch_locks: dict[str, asyncio.Lock] = {}

    async def can_fetch(self, url: str) -> bool:
        """Check if the URL can be fetched according to robots.txt.

        Args:
            url: URL to check

        Returns:
            True if the URL can be fetched, False otherwise
        """
        if not self.respect_robots:
            return True

        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        # Get or fetch robots.txt parser for this domain
        parser = await self._get_parser(domain)

        if parser is None:
            # If we couldn't fetch robots.txt, allow access (fail open)
            logger.debug(f"No robots.txt found for {domain}, allowing access")
            return True

        can_fetch = parser.can_fetch(self.user_agent, url)
        if not can_fetch:
            logger.warning(f"robots.txt disallows access to: {url}")

        return can_fetch

    async def _get_parser(self, domain: str) -> RobotFileParser | None:
        """Get or create a robots.txt parser for a domain.

        Args:
            domain: Domain URL (e.g., https://example.com)

        Returns:
            RobotFileParser instance or None if unavailable
        """
        if domain in self._cache:
            return self._cache[domain]

        # Use per-domain locks to prevent concurrent fetches
        if domain not in self._fetch_locks:
            self._fetch_locks[domain] = asyncio.Lock()

        async with self._fetch_locks[domain]:
            # Double-check after acquiring lock
            if domain in self._cache:
                return self._cache[domain]

            parser = await self._fetch_robots(domain)
            self._cache[domain] = parser
            return parser

    async def _fetch_robots(self, domain: str) -> RobotFileParser | None:
        """Fetch and parse robots.txt for a domain.

        Args:
            domain: Domain URL (e.g., https://example.com)

        Returns:
            RobotFileParser instance or None if unavailable
        """
        robots_url = f"{domain}/robots.txt"
        logger.debug(f"Fetching robots.txt from {robots_url}")

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(robots_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        parser = RobotFileParser()
                        parser.parse(content.splitlines())
                        logger.info(f"Loaded robots.txt for {domain}")
                        return parser
                    elif response.status == 404:
                        logger.debug(f"No robots.txt found at {robots_url}")
                        return None
                    else:
                        logger.warning(
                            f"Unexpected status {response.status} fetching {robots_url}"
                        )
                        return None

        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching robots.txt from {robots_url}")
            return None
        except aiohttp.ClientError as e:
            logger.warning(f"Error fetching robots.txt from {robots_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching robots.txt: {e}", exc_info=True)
            return None

    def get_crawl_delay(self, domain: str) -> float | None:
        """Get the crawl delay specified in robots.txt.

        Args:
            domain: Domain URL

        Returns:
            Crawl delay in seconds or None if not specified
        """
        parser = self._cache.get(domain)
        if parser is None:
            return None

        try:
            delay = parser.crawl_delay(self.user_agent)
            return float(delay) if delay is not None else None
        except Exception:
            return None

    def clear_cache(self) -> None:
        """Clear the robots.txt cache."""
        self._cache.clear()

    def get_cached_domains(self) -> list[str]:
        """Get list of domains with cached robots.txt.

        Returns:
            List of domain URLs
        """
        return list(self._cache.keys())


class ComplianceChecker:
    """High-level compliance checker combining multiple policies."""

    def __init__(
        self,
        robots_policy: RobotsPolicy | None = None,
        respect_robots: bool = True,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        """Initialize compliance checker.

        Args:
            robots_policy: Optional pre-configured RobotsPolicy
            respect_robots: Whether to respect robots.txt
            user_agent: User agent for robots.txt checks
        """
        self.robots_policy = robots_policy or RobotsPolicy(
            user_agent=user_agent,
            respect_robots=respect_robots,
        )

    async def check_url(self, url: str) -> dict[str, Any]:
        """Check compliance for a URL.

        Args:
            url: URL to check

        Returns:
            Dictionary with compliance check results
        """
        results: dict[str, Any] = {
            "url": url,
            "allowed": True,
            "robots_allowed": True,
            "warnings": [],
        }

        # Check robots.txt
        robots_allowed = await self.robots_policy.can_fetch(url)
        results["robots_allowed"] = robots_allowed

        if not robots_allowed:
            results["allowed"] = False
            results["warnings"].append(f"robots.txt disallows access to {url}")

        return results

    async def ensure_allowed(self, url: str) -> None:
        """Ensure a URL is allowed to be fetched.

        Args:
            url: URL to check

        Raises:
            PermissionError: If the URL is not allowed
        """
        result = await self.check_url(url)
        if not result["allowed"]:
            warnings = "; ".join(result["warnings"])
            raise PermissionError(f"Access denied: {warnings}")
