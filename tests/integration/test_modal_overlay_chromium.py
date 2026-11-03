"""ModalHandler's overlay check and close-button finder, rendered in a real Chromium."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from agentic_search_audit.core.types import ModalsConfig
from agentic_search_audit.extractors.modals import ModalHandler

pytestmark = [pytest.mark.browser, pytest.mark.asyncio(loop_scope="module")]

SNAPSHOTS_DIR = Path(__file__).parent.parent / "data" / "snapshots"

# Amazon's results grid: every product image sits in an "s-image-overlay-grey" container,
# in normal flow. Nothing here covers the page.
PRODUCT_GRID = """
<div class="s-main-slot">
  <div class="s-result-item"><div class="s-product-image-container s-image-overlay-grey"
       style="position:relative;width:260px;height:230px">
    <img alt="" style="width:240px;height:200px"></div>
    <button>Close</button><h2>Laptop stand</h2></div>
  <div class="s-result-item"><div class="s-product-image-container s-image-overlay-grey"
       style="position:relative;width:260px;height:230px"></div><h2>Monitor arm</h2></div>
</div>
"""

FIXED_MODAL = """
<div class="newsletter-modal" style="position:fixed;top:10%;left:10%;width:600px;height:400px;
     background:#fff;z-index:1000"><p>Join our list</p><button>No thanks</button></div>
"""


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


async def _handler(browser: Any, body: str) -> tuple[ModalHandler, Any]:
    from agentic_search_audit.browser.playwright_client import PlaywrightBrowserClient

    page = await browser.new_page(viewport={"width": 1366, "height": 900})
    await page.set_content(f"<html><body>{body}</body></html>")
    client = PlaywrightBrowserClient()
    client._page = page
    config = ModalsConfig(close_text_matches=["close", "no thanks", "dismiss"])
    return ModalHandler(client, config), page


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (PRODUCT_GRID, False),
        (FIXED_MODAL, True),
        (PRODUCT_GRID + FIXED_MODAL, True),
        # A pre-rendered dialog that is hidden is not a modal
        ('<div role="dialog" style="visibility:hidden;width:500px;height:300px"></div>', False),
        # aria-modal counts even in normal flow
        ('<div aria-modal="true" style="width:500px;height:300px">Sign in</div>', True),
        # A popup layered above the page
        (
            '<div style="position:relative"><div class="popup" style="position:absolute;'
            'top:0;left:0;width:400px;height:300px;z-index:500"></div></div>',
            True,
        ),
        # A fixed modal parked off-screen
        (
            '<div class="modal" style="position:fixed;top:-2000px;left:0;width:600px;'
            'height:400px"></div>',
            False,
        ),
        # A transparent fixed overlay
        (
            '<div class="overlay" style="position:fixed;inset:0;opacity:0"></div>',
            False,
        ),
    ],
    ids=[
        "amazon-product-grid",
        "fixed-modal",
        "grid-plus-modal",
        "hidden-dialog",
        "aria-modal-in-flow",
        "absolute-popup-high-z",
        "off-screen-modal",
        "transparent-overlay",
    ],
)
async def test_check_modal_overlay(browser: Any, body: str, expected: bool) -> None:
    handler, page = await _handler(browser, body)
    try:
        assert await handler._check_modal_overlay() is expected
    finally:
        await page.close()


async def test_close_button_in_a_product_card_is_not_a_modal_close(browser: Any) -> None:
    handler, page = await _handler(browser, PRODUCT_GRID)
    try:
        assert await handler._find_close_button() is None
    finally:
        await page.close()


async def test_close_button_inside_a_fixed_modal_is_found(browser: Any) -> None:
    handler, page = await _handler(browser, PRODUCT_GRID + FIXED_MODAL)
    try:
        found = await handler._find_close_button()
        assert found is not None
        selector, index = found
        text = await page.evaluate(
            "([s, i]) => document.querySelectorAll(s)[i].textContent.trim()", [selector, index]
        )
        assert text == "No thanks"
    finally:
        await page.close()


async def test_amazon_location_toaster_is_dismissed(browser: Any) -> None:
    """The Dismiss control is an <input> labelled by a sibling span (aria-labelledby)."""
    html = (SNAPSHOTS_DIR / "amazon_glow_toaster.html").read_text(encoding="utf-8")
    handler, page = await _handler(browser, html)
    handler.config.close_text_matches = ["accept", "dismiss", "close", "no thanks", "not now"]
    try:
        assert await handler._check_modal_overlay() is True
        assert await handler.dismiss_modals() >= 1
        assert await page.query_selector(".glow-toaster") is None
        assert await handler._check_modal_overlay() is False
    finally:
        await page.close()


async def test_change_address_is_never_mistaken_for_a_close_button(browser: Any) -> None:
    html = (SNAPSHOTS_DIR / "amazon_glow_toaster.html").read_text(encoding="utf-8")
    handler, page = await _handler(browser, html)
    handler.config.close_text_matches = ["accept", "dismiss", "close"]
    try:
        found = await handler._find_close_button()
        assert found is not None
        selector, index = found
        action = await page.evaluate(
            "([s, i]) => document.querySelectorAll(s)[i].getAttribute('data-action-type')",
            [selector, index],
        )
        assert action == "DISMISS"
    finally:
        await page.close()
