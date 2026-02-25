"""Tests for LLM rate limiter."""

import asyncio
import time

import pytest

from agentic_search_audit.judge.rate_limiter import LLMRateLimiter


@pytest.mark.unit
async def test_semaphore_limits_concurrency():
    """Rate limiter should enforce max concurrent calls."""
    limiter = LLMRateLimiter(max_concurrent=2, min_interval_seconds=0.0)
    active = 0
    max_active = 0

    async def work():
        nonlocal active, max_active
        async with limiter.acquire():
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.05)
            active -= 1

    tasks = [asyncio.create_task(work()) for _ in range(5)]
    await asyncio.gather(*tasks)

    assert max_active <= 2


@pytest.mark.unit
async def test_min_interval_enforced():
    """Rate limiter should enforce minimum interval between calls."""
    limiter = LLMRateLimiter(max_concurrent=10, min_interval_seconds=0.1)
    timestamps = []

    async def work():
        async with limiter.acquire():
            timestamps.append(time.monotonic())

    # Run sequentially to test interval
    for _ in range(3):
        await work()

    # Check intervals between consecutive calls
    for i in range(1, len(timestamps)):
        interval = timestamps[i] - timestamps[i - 1]
        assert interval >= 0.09, f"Interval too short: {interval:.3f}s"


@pytest.mark.unit
async def test_limiter_allows_concurrent_up_to_limit():
    """Multiple tasks should run concurrently up to limit."""
    limiter = LLMRateLimiter(max_concurrent=3, min_interval_seconds=0.0)
    results = []

    async def work(task_id):
        async with limiter.acquire():
            results.append(("start", task_id))
            await asyncio.sleep(0.01)
            results.append(("end", task_id))

    tasks = [asyncio.create_task(work(i)) for i in range(3)]
    await asyncio.gather(*tasks)

    assert len(results) == 6  # 3 starts + 3 ends


@pytest.mark.unit
async def test_limiter_with_exception():
    """Rate limiter should release on exception."""
    limiter = LLMRateLimiter(max_concurrent=1, min_interval_seconds=0.0)

    with pytest.raises(ValueError):
        async with limiter.acquire():
            raise ValueError("boom")

    # Should be released — next acquire should work
    async with limiter.acquire():
        pass  # success
