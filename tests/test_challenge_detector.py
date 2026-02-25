"""Tests for CAPTCHA/challenge page detection."""

import json
from unittest.mock import AsyncMock

import pytest

from agentic_search_audit.browser.challenge_detector import (
    ChallengeDetectedError,
    ChallengeDetection,
    detect_challenge,
)


@pytest.fixture
def mock_client():
    """Create a mock browser client."""
    client = AsyncMock()
    client.evaluate = AsyncMock(return_value=None)
    client.query_selector = AsyncMock(return_value=None)
    return client


@pytest.mark.unit
async def test_detect_challenge_clean_page(mock_client):
    """No challenge detected on a normal page."""
    call_count = 0

    async def evaluate_side_effect(expression):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # title check
            return "Nike Search Results"
        if "iframe" in expression:  # iframe check
            return ""
        # body check
        return json.dumps({"len": 5000, "text": "lots of normal page content"})

    mock_client.evaluate = AsyncMock(side_effect=evaluate_side_effect)
    mock_client.query_selector = AsyncMock(return_value=None)
    result = await detect_challenge(mock_client)
    assert result.detected is False
    assert result.challenge_type == "none"


@pytest.mark.unit
async def test_detect_challenge_title_cloudflare(mock_client):
    """Detect Cloudflare challenge via title."""
    mock_client.evaluate = AsyncMock(return_value="Just a moment...")
    result = await detect_challenge(mock_client)
    assert result.detected is True
    assert result.challenge_type == "title_match"
    assert "Just a moment" in result.message


@pytest.mark.unit
async def test_detect_challenge_title_access_denied(mock_client):
    """Detect access denied via title."""
    mock_client.evaluate = AsyncMock(return_value="Access Denied - Security Check")
    result = await detect_challenge(mock_client)
    assert result.detected is True
    assert result.challenge_type == "title_match"


@pytest.mark.unit
async def test_detect_challenge_title_verify_human(mock_client):
    """Detect human verification page via title."""
    mock_client.evaluate = AsyncMock(return_value="Please Verify You Are Human")
    result = await detect_challenge(mock_client)
    assert result.detected is True
    assert result.challenge_type == "title_match"


@pytest.mark.unit
async def test_detect_challenge_selector_cloudflare(mock_client):
    """Detect Cloudflare challenge via CSS selector."""
    mock_client.evaluate = AsyncMock(return_value="Normal Title")

    # Return None for title check, then match on the selector
    async def query_side_effect(selector):
        if selector == "#challenge-running":
            return {"exists": True}
        return None

    mock_client.query_selector = AsyncMock(side_effect=query_side_effect)
    result = await detect_challenge(mock_client)
    assert result.detected is True
    assert result.challenge_type == "selector_match"


@pytest.mark.unit
async def test_detect_challenge_selector_perimeterx(mock_client):
    """Detect PerimeterX challenge via selector."""
    mock_client.evaluate = AsyncMock(return_value="Normal Title")

    async def query_side_effect(selector):
        if selector == "#px-captcha":
            return {"exists": True}
        return None

    mock_client.query_selector = AsyncMock(side_effect=query_side_effect)
    result = await detect_challenge(mock_client)
    assert result.detected is True
    assert result.challenge_type == "selector_match"


@pytest.mark.unit
async def test_detect_challenge_captcha_iframe(mock_client):
    """Detect challenge via CAPTCHA iframe."""
    # Title is normal, no selectors match
    call_count = 0

    async def evaluate_side_effect(expression):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # title check
            return "Normal Title"
        if "iframe" in expression:  # iframe check
            return "recaptcha"
        # body check
        return json.dumps({"len": 5000, "text": "lots of content"})

    mock_client.evaluate = AsyncMock(side_effect=evaluate_side_effect)
    mock_client.query_selector = AsyncMock(return_value=None)
    result = await detect_challenge(mock_client)
    assert result.detected is True
    assert result.challenge_type == "captcha_iframe"


@pytest.mark.unit
async def test_detect_challenge_short_body_with_block_keyword(mock_client):
    """Detect block page via short body with keywords."""
    call_count = 0

    async def evaluate_side_effect(expression):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # title check
            return "Normal Title"
        if "iframe" in expression:  # iframe check
            return ""
        # body check
        return json.dumps({"len": 200, "text": "access denied by cloudflare. ray id: abc123"})

    mock_client.evaluate = AsyncMock(side_effect=evaluate_side_effect)
    mock_client.query_selector = AsyncMock(return_value=None)
    result = await detect_challenge(mock_client)
    assert result.detected is True
    assert result.challenge_type == "short_body_block"


@pytest.mark.unit
async def test_detect_challenge_long_body_ignored(mock_client):
    """Long body should not trigger short-body detection even with keywords."""
    call_count = 0

    async def evaluate_side_effect(expression):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "Normal Title"
        if "iframe" in expression:
            return ""
        return json.dumps({"len": 5000, "text": "cloudflare protects this site..."})

    mock_client.evaluate = AsyncMock(side_effect=evaluate_side_effect)
    mock_client.query_selector = AsyncMock(return_value=None)
    result = await detect_challenge(mock_client)
    assert result.detected is False


@pytest.mark.unit
async def test_challenge_detected_error():
    """ChallengeDetectedError carries detection info."""
    detection = ChallengeDetection(
        detected=True,
        challenge_type="title_match",
        message="Challenge page detected via title: 'Just a moment'",
    )
    error = ChallengeDetectedError(detection)
    assert error.detection is detection
    assert "Just a moment" in str(error)
