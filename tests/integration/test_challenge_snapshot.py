"""detect_challenge against saved pages rendered in a real Chromium."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from agentic_search_audit.browser.challenge_detector import detect_challenge

SNAPSHOTS_DIR = Path(__file__).parent.parent / "data" / "snapshots"

pytestmark = [pytest.mark.browser, pytest.mark.asyncio(loop_scope="module")]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def browser() -> AsyncIterator[Any]:
    playwright = pytest.importorskip("playwright.async_api")
    pw = await playwright.async_playwright().start()
    try:
        chromium = await pw.chromium.launch(headless=True)
    except Exception as exc:  # browser binary missing
        await pw.stop()
        pytest.skip(f"Chromium not available: {exc}")
    try:
        yield chromium
    finally:
        await chromium.close()
        await pw.stop()


async def _detect(browser: Any, snapshot: str) -> Any:
    from agentic_search_audit.browser.playwright_client import PlaywrightBrowserClient

    page = await browser.new_page()
    try:
        await page.set_content((SNAPSHOTS_DIR / snapshot).read_text(encoding="utf-8"))
        client = PlaywrightBrowserClient()
        client._page = page
        return await detect_challenge(client)
    finally:
        await page.close()


async def test_ebay_edge_block_page_is_a_challenge(browser: Any) -> None:
    detection = await _detect(browser, "ebay_edge_block.html")
    assert detection.detected is True
    assert detection.challenge_type == "edge_block"


async def test_incapsula_block_iframe_is_a_challenge(browser: Any) -> None:
    detection = await _detect(browser, "incapsula_block.html")
    assert detection.detected is True
    assert detection.challenge_type == "captcha_iframe"
    assert "_incapsula_resource" in detection.message


async def test_a_results_page_is_not_a_challenge(browser: Any) -> None:
    detection = await _detect(browser, "books_toscrape_search.html")
    assert detection.detected is False
