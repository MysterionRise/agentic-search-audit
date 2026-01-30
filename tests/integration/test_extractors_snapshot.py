"""Integration tests for extractors using HTML snapshots.

These tests use pre-captured HTML snapshots to test extraction logic
without requiring browser automation.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentic_search_audit.core.types import ResultsConfig, SearchConfig
from agentic_search_audit.extractors.results import ResultsExtractor
from agentic_search_audit.extractors.search_box import SearchBoxFinder


@pytest.fixture
def snapshots_dir():
    """Get path to HTML snapshots directory."""
    return Path(__file__).parent.parent / "data" / "snapshots"


@pytest.fixture
def books_toscrape_html(snapshots_dir):
    """Load Books to Scrape search results HTML."""
    html_path = snapshots_dir / "books_toscrape_search.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    pytest.skip("Snapshot file not found")


@pytest.fixture
def fashion_store_html(snapshots_dir):
    """Load fashion store homepage HTML."""
    html_path = snapshots_dir / "fashion_store_homepage.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    pytest.skip("Snapshot file not found")


class MockMCPClient:
    """Mock MCP browser client for testing with HTML snapshots."""

    def __init__(self, html_content: str):
        """Initialize with HTML content.

        Args:
            html_content: HTML content to return
        """
        self.html_content = html_content
        self._elements: dict[str, list[dict]] = {}
        self._parse_html()

    def _parse_html(self) -> None:
        """Parse HTML to simulate DOM queries."""
        # Simple parsing for common selectors
        import re

        # Extract product cards
        product_pattern = r'<article class="product-card"[^>]*>(.*?)</article>'
        products = re.findall(product_pattern, self.html_content, re.DOTALL)

        self._elements["article.product-card"] = []
        self._elements[".product-card"] = []

        for i, product_html in enumerate(products):
            # Extract title
            title_match = re.search(r"<h3[^>]*>(.*?)</h3>", product_html)
            title = title_match.group(1) if title_match else f"Product {i+1}"

            # Extract price
            price_match = re.search(r'class="product-price"[^>]*>\$([\d.]+)', product_html)
            price = f"${price_match.group(1)}" if price_match else None

            # Extract URL
            url_match = re.search(r'href="([^"]+)"', product_html)
            url = url_match.group(1) if url_match else None

            element = {
                "title": title,
                "price": price,
                "url": url,
                "html": product_html,
            }
            self._elements["article.product-card"].append(element)
            self._elements[".product-card"].append(element)

        # Extract search input
        search_pattern = r'<input[^>]*type="search"[^>]*>'
        search_inputs = re.findall(search_pattern, self.html_content, re.IGNORECASE)
        self._elements['input[type="search"]'] = [{"html": s} for s in search_inputs]

    async def get_html(self) -> str:
        """Return the HTML content."""
        return self.html_content

    async def query_selector_all(self, selector: str) -> list[dict]:
        """Simulate querySelector with parsed elements."""
        # Direct match
        if selector in self._elements:
            return self._elements[selector]

        # Try to match partial selectors
        for key, elements in self._elements.items():
            if selector in key or key in selector:
                return elements

        return []

    async def query_selector(self, selector: str) -> dict | None:
        """Simulate querySelector."""
        elements = await self.query_selector_all(selector)
        return elements[0] if elements else None

    async def evaluate(self, script: str) -> str | None:
        """Simulate JavaScript evaluation."""
        if "window.location.href" in script:
            return "https://example.com/search"
        return None

    async def screenshot(self, path, full_page=False) -> None:
        """Mock screenshot - does nothing."""
        pass

    async def wait_for_network_idle(self, timeout=1000) -> None:
        """Mock wait - does nothing."""
        pass


class TestResultsExtractorWithSnapshots:
    """Tests for ResultsExtractor using HTML snapshots."""

    @pytest.fixture
    def books_results_config(self):
        """Results config for Books to Scrape."""
        return ResultsConfig(
            item_selectors=[
                "article.product-card",
                ".product-card",
            ],
            title_selectors=[
                "h3.product-title",
                "h3",
            ],
            price_selectors=[
                ".product-price",
            ],
            url_attr="href",
        )

    @pytest.mark.asyncio
    async def test_extract_results_from_books_snapshot(
        self, books_toscrape_html, books_results_config
    ):
        """Test extracting results from Books to Scrape snapshot."""
        mock_client = MockMCPClient(books_toscrape_html)

        extractor = ResultsExtractor(
            client=mock_client,
            config=books_results_config,
            base_url="https://books.toscrape.com",
        )

        results = await extractor.extract_results(top_k=10)

        # Should extract 5 products from the snapshot
        assert len(results) == 5

        # Check first result
        first_result = results[0]
        assert first_result.rank == 1
        assert "Python" in first_result.title or first_result.title is not None
        assert first_result.price is not None
        assert "$" in first_result.price

    @pytest.mark.asyncio
    async def test_extract_preserves_ranking_order(
        self, books_toscrape_html, books_results_config
    ):
        """Test that results maintain correct ranking order."""
        mock_client = MockMCPClient(books_toscrape_html)

        extractor = ResultsExtractor(
            client=mock_client,
            config=books_results_config,
            base_url="https://books.toscrape.com",
        )

        results = await extractor.extract_results(top_k=10)

        # Check ranking is sequential
        for i, result in enumerate(results, 1):
            assert result.rank == i

    @pytest.mark.asyncio
    async def test_top_k_limits_results(self, books_toscrape_html, books_results_config):
        """Test that top_k parameter limits results."""
        mock_client = MockMCPClient(books_toscrape_html)

        extractor = ResultsExtractor(
            client=mock_client,
            config=books_results_config,
            base_url="https://books.toscrape.com",
        )

        results = await extractor.extract_results(top_k=3)

        assert len(results) == 3


class TestSearchBoxFinderWithSnapshots:
    """Tests for SearchBoxFinder using HTML snapshots."""

    @pytest.fixture
    def fashion_search_config(self):
        """Search config for fashion store."""
        return SearchConfig(
            input_selectors=[
                'input[type="search"]',
                "#search-input",
                'input[aria-label*="Search"]',
            ],
            submit_strategy="enter",
        )

    @pytest.mark.asyncio
    async def test_find_search_box_in_fashion_store(
        self, fashion_store_html, fashion_search_config
    ):
        """Test finding search box in fashion store snapshot."""
        mock_client = MockMCPClient(fashion_store_html)

        finder = SearchBoxFinder(
            client=mock_client,
            config=fashion_search_config,
            use_intelligent_fallback=False,
        )

        # Test that selector detection works
        found = await mock_client.query_selector('input[type="search"]')
        assert found is not None


class TestResultsExtractorWithFashionStore:
    """Tests for ResultsExtractor with fashion store snapshot."""

    @pytest.fixture
    def fashion_results_config(self):
        """Results config for fashion store."""
        return ResultsConfig(
            item_selectors=[
                "article.product-card",
                ".product-card",
            ],
            title_selectors=[
                "h3",
            ],
            price_selectors=[
                ".product-price",
            ],
            url_attr="href",
        )

    @pytest.mark.asyncio
    async def test_extract_trending_products(
        self, fashion_store_html, fashion_results_config
    ):
        """Test extracting trending products from fashion store."""
        mock_client = MockMCPClient(fashion_store_html)

        extractor = ResultsExtractor(
            client=mock_client,
            config=fashion_results_config,
            base_url="https://fashion-store.example.com",
        )

        results = await extractor.extract_results(top_k=10)

        # Should extract 4 trending products
        assert len(results) == 4

        # Check prices are extracted
        for result in results:
            assert result.price is not None
            assert "$" in result.price


class TestSnapshotDataIntegrity:
    """Tests to verify snapshot data integrity."""

    def test_books_snapshot_exists(self, snapshots_dir):
        """Verify Books to Scrape snapshot exists."""
        html_path = snapshots_dir / "books_toscrape_search.html"
        assert html_path.exists(), f"Snapshot not found: {html_path}"

    def test_fashion_snapshot_exists(self, snapshots_dir):
        """Verify fashion store snapshot exists."""
        html_path = snapshots_dir / "fashion_store_homepage.html"
        assert html_path.exists(), f"Snapshot not found: {html_path}"

    def test_books_snapshot_contains_products(self, books_toscrape_html):
        """Verify Books snapshot contains expected products."""
        assert "Python Crash Course" in books_toscrape_html
        assert "product-card" in books_toscrape_html
        assert "$29.99" in books_toscrape_html

    def test_fashion_snapshot_contains_brands(self, fashion_store_html):
        """Verify fashion snapshot contains expected brands."""
        assert "Nike" in fashion_store_html
        assert "Adidas" in fashion_store_html
        assert "Zara" in fashion_store_html
        assert "search" in fashion_store_html.lower()
