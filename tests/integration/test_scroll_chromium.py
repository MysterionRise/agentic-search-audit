"""The audit's scroll steps against a real Chromium (marker: browser).

Scroll methods return a Promise since Chrome 155, and evaluate() rejects promises, so a bare
``window.scrollBy(...)`` failed every query that reached the lazy-load scroll.
"""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from agentic_search_audit.core.types import AuditConfig, ResultsConfig, RunConfig, SiteConfig

pytestmark = [pytest.mark.browser, pytest.mark.asyncio(loop_scope="module")]

TALL_PAGE = (
    "<html><body>"
    + "".join(f"<div class='card' style='height:300px'>item {i}</div>" for i in range(40))
    + "</body></html>"
)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def client() -> AsyncIterator[Any]:
    playwright = pytest.importorskip("playwright.async_api")
    from agentic_search_audit.browser.playwright_client import PlaywrightBrowserClient

    pw = await playwright.async_playwright().start()
    try:
        browser = await pw.chromium.launch(headless=True)
    except Exception as exc:  # browser binary missing
        await pw.stop()
        pytest.skip(f"Chromium not available: {exc}")
    page = await browser.new_page()
    await page.set_content(TALL_PAGE)
    browser_client = PlaywrightBrowserClient()
    browser_client._page = page
    try:
        yield browser_client
    finally:
        await page.close()
        await browser.close()
        await pw.stop()


async def test_scroll_for_results_runs_on_chromium(client: Any) -> None:
    from agentic_search_audit.core.orchestrator import SearchAuditOrchestrator
    from agentic_search_audit.extractors.results import ResultsExtractor

    config = AuditConfig(
        site=SiteConfig(url="https://example.com"),
        run=RunConfig(top_k=100, max_scroll_attempts=2, scroll_pause_ms=0),
    )
    orchestrator = SearchAuditOrchestrator(config, [], MagicMock())
    orchestrator.client = client
    extractor = ResultsExtractor(
        client, ResultsConfig(item_selectors=[".card"]), "https://example.com"
    )
    with patch("agentic_search_audit.core.orchestrator.asyncio.sleep"):
        await orchestrator._scroll_for_results(extractor, 100)
    assert await client.evaluate("window.scrollY") == 0  # scrolled back to the top


async def test_human_scroll_jitter_runs_on_chromium(client: Any) -> None:
    from agentic_search_audit.browser.stealth import inject_human_behavior

    with (
        patch("agentic_search_audit.browser.stealth.random.choice", side_effect=["scroll", 1]),
        patch("agentic_search_audit.browser.stealth.asyncio.sleep"),
    ):
        await inject_human_behavior(client)
