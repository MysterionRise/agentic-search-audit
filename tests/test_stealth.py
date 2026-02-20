"""Tests for anti-bot stealth utilities."""

import pytest

from agentic_search_audit.browser.stealth import (
    USER_AGENTS,
    human_typing_delay,
    mouse_jitter_js,
    post_action_delay,
    pre_action_delay,
    random_user_agent,
)


@pytest.mark.unit
class TestUserAgents:
    """User-agent pool and rotation."""

    def test_pool_is_nonempty(self) -> None:
        assert len(USER_AGENTS) > 0

    def test_random_user_agent_returns_string(self) -> None:
        ua = random_user_agent()
        assert isinstance(ua, str)
        assert "Mozilla" in ua

    def test_random_user_agent_from_pool(self) -> None:
        for _ in range(20):
            assert random_user_agent() in USER_AGENTS


@pytest.mark.unit
class TestHumanTypingDelay:
    """Human-like typing delay generation."""

    def test_returns_positive_int(self) -> None:
        for _ in range(50):
            d = human_typing_delay(50)
            assert isinstance(d, int)
            assert d > 0

    def test_never_below_minimum(self) -> None:
        for _ in range(100):
            d = human_typing_delay(30)
            assert d >= 20  # The minimum floor defined in the function

    def test_varies_across_calls(self) -> None:
        delays = {human_typing_delay(50) for _ in range(50)}
        # Should produce at least a few distinct values (not constant)
        assert len(delays) > 3


@pytest.mark.unit
class TestPrePostActionDelay:
    """Random micro-delays for actions."""

    def test_pre_action_delay_range(self) -> None:
        for _ in range(50):
            d = pre_action_delay()
            assert 0.05 <= d <= 0.3

    def test_post_action_delay_range(self) -> None:
        for _ in range(50):
            d = post_action_delay()
            assert 0.1 <= d <= 0.4


@pytest.mark.unit
class TestMouseJitterJS:
    """Mouse jitter JavaScript generation."""

    def test_returns_js_string(self) -> None:
        js = mouse_jitter_js(100, 200)
        assert isinstance(js, str)
        assert "mousemove" in js

    def test_contains_dispatch_events(self) -> None:
        js = mouse_jitter_js(100, 200, steps=3)
        assert js.count("dispatchEvent") == 3

    def test_custom_steps(self) -> None:
        js = mouse_jitter_js(50, 50, steps=7)
        assert js.count("dispatchEvent") == 7
