"""Policies for rate limiting, retries, and compliance."""

import asyncio
import logging
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RateLimiter:
    """Rate limiter for controlling request frequency."""

    def __init__(self, requests_per_second: float):
        """Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests per second
        """
        self.rps = requests_per_second
        self.min_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0
        self.last_request_time = 0.0

    async def acquire(self) -> None:
        """Acquire permission to make a request (with rate limiting)."""
        if self.rps <= 0:
            return

        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_interval:
            wait_time = self.min_interval - time_since_last
            logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)

        self.last_request_time = asyncio.get_event_loop().time()


async def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    *args,
    **kwargs,
) -> T:
    """Retry a function with exponential backoff.

    Args:
        func: Function to retry
        max_retries: Maximum number of retries
        initial_delay: Initial delay in seconds
        backoff_factor: Backoff multiplier
        *args: Function arguments
        **kwargs: Function keyword arguments

    Returns:
        Function result

    Raises:
        Exception: If all retries fail
    """
    delay = initial_delay

    for attempt in range(max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        except Exception as e:
            if attempt == max_retries:
                logger.error(f"All {max_retries} retries failed: {e}")
                raise

            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s...")
            await asyncio.sleep(delay)
            delay *= backoff_factor

    raise RuntimeError("Retry logic error")  # Should never reach here
