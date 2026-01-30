"""Tests for rate limiting and retry policies."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from agentic_search_audit.core.policies import RateLimiter, retry_with_backoff


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_init_with_positive_rps(self):
        """Test RateLimiter initialization with positive RPS."""
        limiter = RateLimiter(requests_per_second=2.0)
        assert limiter.rps == 2.0
        assert limiter.min_interval == 0.5
        assert limiter.last_request_time == 0.0

    def test_init_with_zero_rps(self):
        """Test RateLimiter initialization with zero RPS (disabled)."""
        limiter = RateLimiter(requests_per_second=0)
        assert limiter.rps == 0
        assert limiter.min_interval == 0

    def test_init_with_fractional_rps(self):
        """Test RateLimiter initialization with fractional RPS."""
        limiter = RateLimiter(requests_per_second=0.5)
        assert limiter.rps == 0.5
        assert limiter.min_interval == 2.0  # 1 / 0.5 = 2 seconds

    @pytest.mark.asyncio
    async def test_acquire_no_wait_on_first_request(self):
        """Test that first request doesn't wait."""
        limiter = RateLimiter(requests_per_second=1.0)

        start = asyncio.get_event_loop().time()
        await limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start

        # First request should be nearly instant
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_acquire_waits_between_requests(self):
        """Test that subsequent requests wait for rate limit."""
        limiter = RateLimiter(requests_per_second=10.0)  # 0.1 second intervals

        await limiter.acquire()
        start = asyncio.get_event_loop().time()
        await limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start

        # Should wait approximately 0.1 seconds
        assert elapsed >= 0.08  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_acquire_disabled_with_zero_rps(self):
        """Test that rate limiting is disabled when RPS is 0."""
        limiter = RateLimiter(requests_per_second=0)

        start = asyncio.get_event_loop().time()
        for _ in range(5):
            await limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start

        # Should be nearly instant when disabled
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_acquire_respects_exact_rps(self):
        """Test that acquire respects the configured RPS."""
        rps = 5.0  # 5 requests per second = 0.2 second intervals
        limiter = RateLimiter(requests_per_second=rps)

        start = asyncio.get_event_loop().time()
        for _ in range(3):
            await limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start

        # 3 requests at 5 RPS should take at least 0.4 seconds (2 intervals)
        expected_min = 2 * (1.0 / rps) - 0.02  # Allow 20ms tolerance
        assert elapsed >= expected_min

    @pytest.mark.asyncio
    async def test_acquire_no_wait_if_enough_time_passed(self):
        """Test that acquire doesn't wait if enough time has passed."""
        limiter = RateLimiter(requests_per_second=10.0)

        await limiter.acquire()
        # Simulate time passing
        await asyncio.sleep(0.2)  # More than 0.1 second interval

        start = asyncio.get_event_loop().time()
        await limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start

        # Should not wait since enough time passed
        assert elapsed < 0.05

    @pytest.mark.asyncio
    async def test_acquire_updates_last_request_time(self):
        """Test that acquire updates the last request time."""
        limiter = RateLimiter(requests_per_second=1.0)

        assert limiter.last_request_time == 0.0
        await limiter.acquire()
        assert limiter.last_request_time > 0.0


class TestRetryWithBackoff:
    """Tests for retry_with_backoff function."""

    @pytest.mark.asyncio
    async def test_successful_first_attempt(self):
        """Test that successful first attempt returns immediately."""
        mock_func = AsyncMock(return_value="success")

        result = await retry_with_backoff(mock_func, max_retries=3)

        assert result == "success"
        mock_func.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_successful_after_retry(self):
        """Test that function retries on failure and eventually succeeds."""
        mock_func = AsyncMock(side_effect=[Exception("fail"), Exception("fail"), "success"])

        result = await retry_with_backoff(
            mock_func, max_retries=3, initial_delay=0.01, backoff_factor=2.0
        )

        assert result == "success"
        assert mock_func.await_count == 3

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test that function raises after max retries exceeded."""
        mock_func = AsyncMock(side_effect=Exception("persistent failure"))

        with pytest.raises(Exception, match="persistent failure"):
            await retry_with_backoff(mock_func, max_retries=2, initial_delay=0.01)

        assert mock_func.await_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self):
        """Test that retries use exponential backoff timing."""
        delays = []

        async def track_delay():
            delays.append(asyncio.get_event_loop().time())
            raise Exception("fail")

        mock_func = AsyncMock(side_effect=track_delay)

        try:
            await retry_with_backoff(
                mock_func, max_retries=2, initial_delay=0.1, backoff_factor=2.0
            )
        except Exception:
            pass

        # Check that delays are approximately exponential
        # First retry after ~0.1s, second after ~0.2s more
        assert len(delays) == 3
        delay1 = delays[1] - delays[0]
        delay2 = delays[2] - delays[1]

        assert delay1 >= 0.08  # ~0.1s
        assert delay2 >= 0.16  # ~0.2s

    @pytest.mark.asyncio
    async def test_with_sync_function(self):
        """Test retry_with_backoff with synchronous function."""
        call_count = 0

        def sync_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("fail")
            return "success"

        result = await retry_with_backoff(sync_func, max_retries=3, initial_delay=0.01)

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_with_args_and_kwargs(self):
        """Test retry_with_backoff passes args and kwargs."""
        mock_func = AsyncMock(return_value="result")

        result = await retry_with_backoff(
            mock_func,
            1,  # max_retries
            0.01,  # initial_delay
            2.0,  # backoff_factor
            "arg1",
            "arg2",
            kwarg1="value1",
            kwarg2="value2",
        )

        assert result == "result"
        mock_func.assert_awaited_once_with("arg1", "arg2", kwarg1="value1", kwarg2="value2")

    @pytest.mark.asyncio
    async def test_zero_retries(self):
        """Test with zero retries (only initial attempt)."""
        mock_func = AsyncMock(side_effect=Exception("fail"))

        with pytest.raises(Exception, match="fail"):
            await retry_with_backoff(mock_func, max_retries=0, initial_delay=0.01)

        mock_func.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_custom_backoff_factor(self):
        """Test with custom backoff factor."""
        call_times = []

        async def track_time():
            call_times.append(asyncio.get_event_loop().time())
            raise Exception("fail")

        mock_func = AsyncMock(side_effect=track_time)

        try:
            await retry_with_backoff(
                mock_func, max_retries=2, initial_delay=0.05, backoff_factor=3.0
            )
        except Exception:
            pass

        # With backoff_factor=3, delays should be 0.05, 0.15 (0.05*3)
        assert len(call_times) == 3
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]

        assert delay1 >= 0.04  # ~0.05s
        assert delay2 >= 0.12  # ~0.15s (0.05 * 3)

    @pytest.mark.asyncio
    async def test_different_exception_types(self):
        """Test that all exception types trigger retry."""
        mock_func = AsyncMock(
            side_effect=[ValueError("value error"), TypeError("type error"), "success"]
        )

        result = await retry_with_backoff(mock_func, max_retries=3, initial_delay=0.01)

        assert result == "success"
        assert mock_func.await_count == 3

    @pytest.mark.asyncio
    async def test_preserves_exception_message(self):
        """Test that the last exception message is preserved."""
        mock_func = AsyncMock(side_effect=ValueError("specific error message"))

        with pytest.raises(ValueError, match="specific error message"):
            await retry_with_backoff(mock_func, max_retries=1, initial_delay=0.01)
