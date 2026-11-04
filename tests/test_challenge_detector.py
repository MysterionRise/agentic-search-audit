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


EBAY_BLOCK_TEXT = (
    "SORRY\nSomething went wrong on our end\n0.afe41602.1793671333.12568738\n"
    "Please go back and try again.\nCopyright © 1995-2026 eBay Inc. All Rights Reserved."
)


async def test_edge_block_page_with_reference_id() -> None:
    probe = _probe(title="Error Page | eBay", bodyLen=155, bodyText=EBAY_BLOCK_TEXT)
    result = await detect_challenge(_client(probe))
    assert result.detected is True and result.challenge_type == "edge_block"
    assert "0.afe41602.1793671333.12568738" in result.message


async def test_akamai_access_denied_reference() -> None:
    text = "access denied\nyou don't have permission\nreference #18.2f7d1402.1793671333.1a2b3c4"
    result = await detect_challenge(_client(_probe(bodyLen=120, bodyText=text)))
    assert result.detected is True


async def test_reference_like_number_on_a_long_page_is_ignored() -> None:
    text = "order 0.afe41602.1793671333.12568738 shipped " * 50
    result = await detect_challenge(_client(_probe(bodyLen=len(text), bodyText=text[:1000])))
    assert result.detected is False


async def test_long_body_with_keyword_is_ignored() -> None:
    probe = _probe(bodyLen=20000, bodyText="we use cloudflare for performance " * 10)
    result = await detect_challenge(_client(probe))
    assert result.detected is False


@pytest.mark.parametrize(
    "text",
    [
        "We Are Currently Unable to Provide a Shopping Experience for This Country "
        "Please try again later",
        "We see you have tried to access Gap.com Gap.com currently does not support "
        "shipping outside of the United States to your location.",
        "English Francais Espanol Hello! Choose a country. Canada United States",
    ],
    ids=["jcpenney", "gap", "bestbuy"],
)
async def test_region_block_page(text: str) -> None:
    result = await detect_challenge(_client(_probe(bodyLen=len(text), bodyText=text.lower())))
    assert result.detected is True
    assert result.challenge_type == "geo_block"


async def test_country_selector_in_a_long_page_footer_is_ignored() -> None:
    probe = _probe(bodyLen=20000, bodyText="shop now ... choose a country ... help")
    assert (await detect_challenge(_client(probe))).detected is False


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
