"""Tests for ProxyRotator."""

import pytest

from agentic_search_audit.browser.proxy import ProxyRotator
from agentic_search_audit.core.types import ProxyRotationStrategy


@pytest.mark.unit
def test_none_strategy_returns_none():
    """NONE strategy always returns None."""
    rotator = ProxyRotator(ProxyRotationStrategy.NONE)
    assert rotator.next_proxy() is None
    assert rotator.next_proxy() is None


@pytest.mark.unit
def test_per_site_returns_same_proxy():
    """PER_SITE strategy returns the same proxy every time."""
    proxies = ["http://proxy1:8080", "http://proxy2:8080", "http://proxy3:8080"]
    rotator = ProxyRotator(ProxyRotationStrategy.PER_SITE, proxies)

    first = rotator.next_proxy()
    assert first in proxies

    # All subsequent calls return the same proxy
    for _ in range(10):
        assert rotator.next_proxy() == first


@pytest.mark.unit
def test_per_query_round_robin():
    """PER_QUERY strategy cycles through all proxies."""
    proxies = ["http://p1:8080", "http://p2:8080", "http://p3:8080"]
    rotator = ProxyRotator(ProxyRotationStrategy.PER_QUERY, proxies)

    seen = set()
    for _ in range(len(proxies)):
        proxy = rotator.next_proxy()
        assert proxy is not None
        seen.add(proxy)

    assert seen == set(proxies)


@pytest.mark.unit
def test_per_query_refills_after_exhaustion():
    """PER_QUERY reshuffles and continues when pool is exhausted."""
    proxies = ["http://p1:8080", "http://p2:8080"]
    rotator = ProxyRotator(ProxyRotationStrategy.PER_QUERY, proxies)

    results = [rotator.next_proxy() for _ in range(6)]
    assert all(p in proxies for p in results)
    assert len(results) == 6


@pytest.mark.unit
def test_none_strategy_with_proxy_list():
    """NONE strategy ignores proxy list."""
    rotator = ProxyRotator(ProxyRotationStrategy.NONE, ["http://proxy:8080"])
    assert rotator.next_proxy() is None


@pytest.mark.unit
def test_per_query_empty_list():
    """PER_QUERY with empty list returns None."""
    rotator = ProxyRotator(ProxyRotationStrategy.PER_QUERY, [])
    assert rotator.next_proxy() is None
