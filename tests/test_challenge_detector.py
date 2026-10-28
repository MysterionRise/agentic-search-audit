"""Tests for bot-challenge detection (one in-page probe, four heuristics)."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from agentic_search_audit.browser.challenge_detector import (
    CHALLENGE_SELECTORS,
    ChallengeDetectedError,
    ChallengeDetection,
    detect_challenge,
)

pytestmark = pytest.mark.unit


def _client(probe: Any) -> AsyncMock:
    client = AsyncMock()
    client.evaluate = AsyncMock(return_value=probe)
    return client


def _probe(**overrides: Any) -> dict[str, Any]:
    probe: dict[str, Any] = {
        "title": "Shop the best deals",
        "selector": None,
        "iframe": None,
        "bodyLen": 50000,
        "bodyText": "welcome to our store, free shipping on orders over 50",
    }
    probe.update(overrides)
    return probe


async def test_clean_page_is_one_call() -> None:
    client = _client(_probe())
    result = await detect_challenge(client)
    assert result.detected is False and result.challenge_type == "none"
    client.evaluate.assert_awaited_once()
    script = client.evaluate.await_args.args[0]
    for selector in CHALLENGE_SELECTORS[:3]:
        assert selector in script  # the selector list is embedded, not probed one by one


@pytest.mark.parametrize(
    "title",
    ["Just a moment...", "Access Denied - Security Check", "Please Verify You Are Human"],
)
async def test_title_match(title: str) -> None:
    result = await detect_challenge(_client(_probe(title=title)))
    assert result.detected is True and result.challenge_type == "title_match"
    assert title in result.message


@pytest.mark.parametrize("selector", ["#challenge-running", "#px-captcha"])
async def test_selector_match(selector: str) -> None:
    result = await detect_challenge(_client(_probe(selector=selector)))
    assert result.detected is True and result.challenge_type == "selector_match"
    assert selector in result.message


async def test_captcha_iframe() -> None:
    result = await detect_challenge(_client(_probe(iframe="recaptcha")))
    assert result.detected is True and result.challenge_type == "captcha_iframe"


async def test_short_body_with_block_keyword() -> None:
    probe = _probe(bodyLen=200, bodyText="access denied by cloudflare. ray id: abc123")
    result = await detect_challenge(_client(probe))
    assert result.detected is True and result.challenge_type == "short_body_block"


async def test_long_body_with_keyword_is_ignored() -> None:
    probe = _probe(bodyLen=20000, bodyText="we use cloudflare for performance " * 10)
    result = await detect_challenge(_client(probe))
    assert result.detected is False


async def test_short_body_without_keyword_is_clean() -> None:
    result = await detect_challenge(_client(_probe(bodyLen=100, bodyText="loading...")))
    assert result.detected is False


@pytest.mark.parametrize("probe", [None, "not a dict", 7, {"title": 5}], ids=repr)
async def test_malformed_probe_is_not_a_challenge(probe: Any) -> None:
    result = await detect_challenge(_client(probe))
    assert result.detected is False


async def test_probe_failure_is_not_a_challenge() -> None:
    client = AsyncMock()
    client.evaluate = AsyncMock(side_effect=RuntimeError("page gone"))
    result = await detect_challenge(client)
    assert result.detected is False


async def test_title_wins_over_other_signals() -> None:
    probe = _probe(title="Just a moment...", selector="#px-captcha", iframe="hcaptcha")
    result = await detect_challenge(_client(probe))
    assert result.challenge_type == "title_match"


def test_challenge_detected_error_carries_the_detection() -> None:
    detection = ChallengeDetection(detected=True, challenge_type="title_match", message="m")
    error = ChallengeDetectedError(detection)
    assert error.detection is detection and str(error) == "m"
