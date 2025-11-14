"""Search results extraction."""

import logging
from urllib.parse import urljoin

from ..core.types import ResultItem, ResultsConfig
from ..mcp.client import MCPBrowserClient

logger = logging.getLogger(__name__)


class ResultsExtractor:
    """Extracts search results from the page."""

    def __init__(self, client: MCPBrowserClient, config: ResultsConfig, base_url: str):
        """Initialize results extractor.

        Args:
            client: MCP browser client
            config: Results configuration
            base_url: Base URL for resolving relative URLs
        """
        self.client = client
        self.config = config
        self.base_url = base_url

    async def extract_results(self, top_k: int = 10) -> list[ResultItem]:
        """Extract top-K search results from the page.

        Args:
            top_k: Maximum number of results to extract

        Returns:
            List of result items
        """
        logger.info(f"Extracting top {top_k} search results...")

        # Find result items
        items = await self._find_result_items()
        if not items:
            logger.warning("No result items found")
            return []

        logger.info(f"Found {len(items)} result items")

        # Extract details for each item
        results: list[ResultItem] = []
        for rank, item_selector in enumerate(items[:top_k], start=1):
            try:
                result = await self._extract_result_details(rank, item_selector)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Failed to extract result {rank}: {e}")
                continue

        logger.info(f"Successfully extracted {len(results)} results")
        return results

    async def _find_result_items(self) -> list[str]:
        """Find all result item elements.

        Returns:
            List of CSS selectors for result items
        """
        for selector in self.config.item_selectors:
            logger.debug(f"Trying item selector: {selector}")

            # Count matching elements
            script = f"""
            (function() {{
                const items = document.querySelectorAll('{selector}');
                return items.length;
            }})()
            """

            try:
                count_str = await self.client.evaluate(script)
                count = int(count_str) if count_str else 0

                if count > 0:
                    logger.info(f"Found {count} items with selector: {selector}")
                    # Return list of nth-child selectors
                    return [f"{selector}:nth-of-type({i+1})" for i in range(count)]
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue

        return []

    async def _extract_result_details(self, rank: int, item_selector: str) -> ResultItem | None:
        """Extract details from a single result item.

        Args:
            rank: Result rank (1-indexed)
            item_selector: CSS selector for the result item

        Returns:
            ResultItem or None if extraction failed
        """
        logger.debug(f"Extracting details for result {rank}: {item_selector}")

        # Extract title
        title = await self._extract_text_from_selectors(item_selector, self.config.title_selectors)

        # Extract URL
        url = await self._extract_url(item_selector)

        # Extract snippet
        snippet = await self._extract_text_from_selectors(
            item_selector, self.config.snippet_selectors
        )

        # Extract price (optional)
        price = await self._extract_text_from_selectors(item_selector, self.config.price_selectors)

        # Extract image (optional)
        image = await self._extract_image_url(item_selector)

        # Additional attributes
        attributes = {}

        return ResultItem(
            rank=rank,
            title=title,
            url=url,
            snippet=snippet,
            price=price,
            image=image,
            attributes=attributes,
        )

    async def _extract_text_from_selectors(
        self, parent_selector: str, selectors: list[str]
    ) -> str | None:
        """Extract text from first matching selector within parent.

        Args:
            parent_selector: Parent element selector
            selectors: List of child selectors to try

        Returns:
            Extracted text or None
        """
        for selector in selectors:
            combined = f"{parent_selector} {selector}"
            text = await self.client.get_element_text(combined)
            if text:
                return text.strip()

        return None

    async def _extract_url(self, item_selector: str) -> str | None:
        """Extract URL from result item.

        Args:
            item_selector: Result item selector

        Returns:
            Absolute URL or None
        """
        # Try to get href from the item itself
        url = await self.client.get_element_attribute(item_selector, self.config.url_attr)

        if not url:
            # Try to find an anchor tag within the item
            a_selector = f"{item_selector} a"
            url = await self.client.get_element_attribute(a_selector, "href")

        if url:
            # Convert to absolute URL
            return urljoin(self.base_url, url)

        return None

    async def _extract_image_url(self, item_selector: str) -> str | None:
        """Extract image URL from result item.

        Args:
            item_selector: Result item selector

        Returns:
            Absolute image URL or None
        """
        for selector in self.config.image_selectors:
            combined = f"{item_selector} {selector}"

            # Try src attribute
            src = await self.client.get_element_attribute(combined, "src")
            if src:
                return urljoin(self.base_url, src)

            # Try data-src (lazy loading)
            data_src = await self.client.get_element_attribute(combined, "data-src")
            if data_src:
                return urljoin(self.base_url, data_src)

        return None

    async def check_for_no_results(self) -> bool:
        """Check if page shows 'no results' message.

        Returns:
            True if no results found
        """
        no_results_patterns = [
            "no results",
            "no items found",
            "0 results",
            "nothing found",
            "try a different search",
        ]

        for pattern in no_results_patterns:
            script = f"""
            (function() {{
                const text = document.body.textContent.toLowerCase();
                return text.includes('{pattern}');
            }})()
            """

            result = await self.client.evaluate(script)
            if result and result.lower() == "true":
                logger.info(f"Detected no results message: '{pattern}'")
                return True

        return False
