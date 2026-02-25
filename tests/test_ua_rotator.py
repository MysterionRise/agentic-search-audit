"""Tests for UserAgentRotator."""

import pytest

from agentic_search_audit.browser.stealth import USER_AGENTS, UserAgentRotator


@pytest.mark.unit
def test_rotator_returns_all_agents_before_repeating():
    """Rotator should exhaust the full pool before any repeat."""
    agents = ["UA-1", "UA-2", "UA-3"]
    rotator = UserAgentRotator(agents)

    seen = []
    for _ in range(len(agents)):
        ua = rotator.next()
        assert ua not in seen, f"Got repeat '{ua}' before pool exhausted"
        seen.append(ua)

    assert set(seen) == set(agents)


@pytest.mark.unit
def test_rotator_refills_after_exhaustion():
    """Rotator should reshuffle and continue after exhaustion."""
    agents = ["UA-1", "UA-2"]
    rotator = UserAgentRotator(agents)

    results = [rotator.next() for _ in range(6)]
    assert len(results) == 6
    assert set(results) == set(agents)


@pytest.mark.unit
def test_rotator_default_agents():
    """Rotator should use USER_AGENTS when no agents provided."""
    rotator = UserAgentRotator()
    ua = rotator.next()
    assert ua in USER_AGENTS


@pytest.mark.unit
def test_rotator_single_agent():
    """Rotator should handle single agent pool."""
    rotator = UserAgentRotator(["UA-only"])
    assert rotator.next() == "UA-only"
    assert rotator.next() == "UA-only"


@pytest.mark.unit
def test_ua_pool_size():
    """USER_AGENTS pool should have at least 12 agents."""
    assert len(USER_AGENTS) >= 12
