"""Extractor tests against saved HTML snapshots, rendered in a real Chromium.

The browser-backed tests carry the ``browser`` marker and skip when Playwright's
Chromium is not installed; the snapshot-integrity tests always run.
"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from agentic_search_audit.core.types import LLMConfig, ResultsConfig, SearchConfig
from agentic_search_audit.extractors.results import ResultsExtractor
from agentic_search_audit.extractors.search_box import SearchBoxFinder

SNAPSHOTS_DIR = Path(__file__).parent.parent / "data" / "snapshots"


def _load(name: str) -> str:
    path = SNAPSHOTS_DIR / name
    if not path.exists():
        pytest.skip(f"Snapshot file not found: {path}")
    return path.read_text(encoding="utf-8")


@pytest.fixture
def books_toscrape_html() -> str:
    return _load("books_toscrape_search.html")


@pytest.fixture
def fashion_store_html() -> str:
    return _load("fashion_store_homepage.html")


@pytest.fixture
def mock_llm_config() -> LLMConfig:
    return LLMConfig(provider="openai", model="gpt-4o-mini", api_key="test-key")


browser_tests = [pytest.mark.browser, pytest.mark.asyncio(loop_scope="module")]


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


async def _client_for(browser: Any, html: str) -> Any:
    """A PlaywrightBrowserClient whose page shows ``html``."""
    from agentic_search_audit.browser.playwright_client import PlaywrightBrowserClient

    page = await browser.new_page()
    await page.set_content(html)
    client = PlaywrightBrowserClient()
    client._page = page
    return client


BOOKS_CONFIG = ResultsConfig(
    item_selectors=["article.product-card", ".product-card"],
    title_selectors=["h3.product-title", "h3"],
    price_selectors=[".product-price"],
    url_attr="href",
)

FASHION_CONFIG = ResultsConfig(
    item_selectors=["article.product-card", ".product-card"],
    title_selectors=["h3"],
    price_selectors=[".product-price"],
    url_attr="href",
)


@pytest.mark.parametrize("marker", [None], ids=[""])
class TestResultsExtractorWithSnapshots:
    pytestmark = browser_tests

    async def test_extract_results_from_books_snapshot(
        self, browser: Any, books_toscrape_html: str, marker: None
    ) -> None:
        client = await _client_for(browser, books_toscrape_html)
        try:
            extractor = ResultsExtractor(client, BOOKS_CONFIG, "https://books.toscrape.com")
            results = await extractor.extract_results(top_k=10)
        finally:
            await client._page.close()

        assert len(results) == 5
        assert results[0].rank == 1
        assert results[0].title is not None
        assert results[0].url is not None and results[0].url.startswith("https://")
        assert all(r.price is not None and "$" in r.price for r in results)
        assert [r.rank for r in results] == [1, 2, 3, 4, 5]

    async def test_top_k_limits_results(
        self, browser: Any, books_toscrape_html: str, marker: None
    ) -> None:
        client = await _client_for(browser, books_toscrape_html)
        try:
            extractor = ResultsExtractor(client, BOOKS_CONFIG, "https://books.toscrape.com")
            results = await extractor.extract_results(top_k=3)
            count = await extractor.count_visible_results()
        finally:
            await client._page.close()
        assert len(results) == 3
        assert count == 5

    async def test_extract_trending_products(
        self, browser: Any, fashion_store_html: str, marker: None
    ) -> None:
        client = await _client_for(browser, fashion_store_html)
        try:
            extractor = ResultsExtractor(
                client, FASHION_CONFIG, "https://fashion-store.example.com"
            )
            results = await extractor.extract_results(top_k=10)
        finally:
            await client._page.close()
        assert len(results) == 4
        for result in results:
            assert result.price is not None
            assert "$" in result.price

    async def test_search_box_is_found_by_selector(
        self,
        browser: Any,
        fashion_store_html: str,
        mock_llm_config: LLMConfig,
        marker: None,
    ) -> None:
        client = await _client_for(browser, fashion_store_html)
        try:
            config = SearchConfig(
                input_selectors=['input[type="search"]', "#search-input"],
                submit_strategy="enter",
            )
            finder = SearchBoxFinder(
                client=client,
                config=config,
                llm_config=mock_llm_config,
                use_intelligent_fallback=False,
            )
            selector = await finder.find_search_box()
        finally:
            await client._page.close()
        assert selector == 'input[type="search"]'


class TestSnapshotDataIntegrity:
    """Tests to verify snapshot data integrity (no browser needed)."""

    def test_books_snapshot_exists(self) -> None:
        assert (SNAPSHOTS_DIR / "books_toscrape_search.html").exists()

    def test_fashion_snapshot_exists(self) -> None:
        assert (SNAPSHOTS_DIR / "fashion_store_homepage.html").exists()

    def test_books_snapshot_contains_products(self, books_toscrape_html: str) -> None:
        assert "Python Crash Course" in books_toscrape_html
        assert "product-card" in books_toscrape_html
        assert "$29.99" in books_toscrape_html

    def test_fashion_snapshot_contains_brands(self, fashion_store_html: str) -> None:
        assert "Nike" in fashion_store_html
        assert "Adidas" in fashion_store_html
        assert "Zara" in fashion_store_html
        assert "search" in fashion_store_html.lower()
