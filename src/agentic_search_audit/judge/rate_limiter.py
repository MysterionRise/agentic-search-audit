"""LLM API rate limiter.

Coordinates concurrency and minimum interval between LLM API calls
shared across the judge and expert panel to avoid hitting rate limits.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class LLMRateLimiter:
    """Async rate limiter for LLM API calls.

    Uses an asyncio.Semaphore for concurrency control and timestamp
    tracking to enforce a minimum interval between calls.

    Usage::

        limiter = LLMRateLimiter(max_concurrent=3, min_interval_seconds=0.5)
        async with limiter.acquire():
            response = await llm_client.create(...)
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        min_interval_seconds: float = 0.5,
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._min_interval = min_interval_seconds
        self._last_call_time: float = 0.0
        self._lock = asyncio.Lock()

    def acquire(self) -> "_RateLimitContext":
        """Return an async context manager that enforces rate limits."""
        return _RateLimitContext(self)

    async def _enter(self) -> None:
        """Acquire the semaphore and enforce minimum interval."""
        await self._semaphore.acquire()
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call_time
            if elapsed < self._min_interval:
                wait = self._min_interval - elapsed
                logger.debug(f"Rate limiter: waiting {wait:.3f}s for min interval")
                await asyncio.sleep(wait)
            self._last_call_time = time.monotonic()

    def _exit(self) -> None:
        """Release the semaphore."""
        self._semaphore.release()


class _RateLimitContext:
    """Async context manager for LLMRateLimiter."""

    def __init__(self, limiter: LLMRateLimiter) -> None:
        self._limiter = limiter

    async def __aenter__(self) -> None:
        await self._limiter._enter()

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self._limiter._exit()
