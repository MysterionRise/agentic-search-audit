"""Search results extraction."""

import logging
from urllib.parse import urljoin

from ..core.types import BrowserClient, ResultItem, ResultsConfig

logger = logging.getLogger(__name__)


class ResultsExtractor:
    """Extracts search results from the page."""

    def __init__(self, client: BrowserClient, config: ResultsConfig, base_url: str):
        """Initialize results extractor.

        Args:
            client: MCP browser client
            config: Results configuration
            base_url: Base URL for resolving relative URLs
        """
        self.client = client
        self.config = config
        self.base_url = base_url

    async def count_visible_results(self) -> int:
        """Count visible result items on the page without full extraction.

        Returns:
            Number of matching result items currently in the DOM.
        """
        for selector in self.config.item_selectors:
            script = f"""
            (function() {{
                var items = document.querySelectorAll('{selector}');
                return items.length;
            }})()
            """
            try:
                count_str = await self.client.evaluate(script)
                if not count_str or count_str in ("undefined", "null"):
                    continue
                count = int(count_str)
                if count > 0:
                    return count
            except (ValueError, TypeError):
                continue
            except Exception:
                continue
        return 0

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
        for rank, (base_selector, index) in enumerate(items[:top_k], start=1):
            try:
                result = await self._extract_result_details(rank, base_selector, index)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Failed to extract result {rank}: {e}")
                continue

        logger.info(f"Successfully extracted {len(results)} results")
        return results

    async def _find_result_items(self) -> list[tuple[str, int]]:
        """Find all result item elements.

        Returns:
            List of (base_selector, index) tuples for result items.
            Uses querySelectorAll indexing to reliably access the nth match,
            avoiding nth-of-type which counts siblings of the same tag type
            rather than matches of the CSS selector.
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
                logger.debug(f"Selector {selector} returned: {count_str!r}")
                # Handle undefined/null responses
                if not count_str or count_str in ["undefined", "null"]:
                    logger.debug(f"Selector {selector} returned empty/undefined, trying next")
                    count = 0
                else:
                    count = int(count_str)

                if count > 0:
                    logger.info(f"Found {count} items with selector: {selector}")
                    return [(selector, i) for i in range(count)]
                else:
                    logger.debug(f"Selector {selector} found 0 items")
            except (ValueError, TypeError) as e:
                logger.debug(f"Selector {selector} failed to parse count '{count_str}': {e}")
                continue
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue

        return []

    async def _extract_result_details(
        self, rank: int, base_selector: str, index: int
    ) -> ResultItem | None:
        """Extract details from a single result item.

        Args:
            rank: Result rank (1-indexed)
            base_selector: CSS selector matching all result items
            index: Zero-based index into querySelectorAll results

        Returns:
            ResultItem or None if extraction failed
        """
        logger.debug(f"Extracting details for result {rank}: {base_selector}[{index}]")

        # Extract title
        title = await self._extract_text_from_selectors(
            base_selector, index, self.config.title_selectors
        )

        # Extract URL
        url = await self._extract_url(base_selector, index)

        # Additional attributes
        attributes: dict[str, str] = {}

        # Validate extracted URL
        if url:
            from urllib.parse import urlparse

            parsed_url = urlparse(url)
            # Check for valid scheme
            if parsed_url.scheme not in ("http", "https", ""):
                logger.warning(f"Result {rank}: invalid URL scheme '{parsed_url.scheme}': {url}")
                url = None
            elif parsed_url.netloc:
                # Check for off-domain URLs (ad network links etc.)
                base_netloc = urlparse(self.base_url).netloc
                if base_netloc and parsed_url.netloc != base_netloc:
                    # Allow subdomains of the base domain
                    base_domain = ".".join(base_netloc.split(".")[-2:])
                    url_domain = ".".join(parsed_url.netloc.split(".")[-2:])
                    if base_domain != url_domain:
                        attributes["url_off_domain"] = "true"
                        logger.debug(
                            f"Result {rank}: off-domain URL detected:"
                            f" {parsed_url.netloc}"
                            f" (expected: {base_netloc})"
                        )

        # Extract snippet
        snippet = await self._extract_text_from_selectors(
            base_selector, index, self.config.snippet_selectors
        )

        # Extract price (optional)
        price = await self._extract_text_from_selectors(
            base_selector, index, self.config.price_selectors
        )

        # Extract image (optional)
        image = await self._extract_image_url(base_selector, index)

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
        self, base_selector: str, index: int, selectors: list[str]
    ) -> str | None:
        """Extract text from first matching child selector within a result item.

        Uses querySelectorAll indexing to reliably access the parent element.

        Args:
            base_selector: CSS selector matching all result items
            index: Zero-based index into querySelectorAll results
            selectors: List of child selectors to try

        Returns:
            Extracted text or None
        """
        for selector in selectors:
            script = f"""
            (function() {{
                var parent = document.querySelectorAll('{base_selector}')[{index}];
                if (!parent) return null;
                var el = parent.querySelector('{selector}');
                if (!el) return null;
                return (el.textContent || '').trim();
            }})()
            """
            text = await self.client.evaluate(script)
            if text and text not in ("null", "undefined", ""):
                return str(text).strip()

        return None

    async def _extract_url(self, base_selector: str, index: int) -> str | None:
        """Extract URL from result item.

        Uses querySelectorAll indexing to reliably access the element.

        Args:
            base_selector: CSS selector matching all result items
            index: Zero-based index into querySelectorAll results

        Returns:
            Absolute URL or None
        """
        script = f"""
        (function() {{
            var parent = document.querySelectorAll('{base_selector}')[{index}];
            if (!parent) return null;
            var url = parent.getAttribute('{self.config.url_attr}');
            if (url) return url;
            var a = parent.querySelector('a');
            if (a) return a.getAttribute('href');
            return null;
        }})()
        """
        url = await self.client.evaluate(script)
        if url and url not in ("null", "undefined"):
            return urljoin(self.base_url, url)

        return None

    async def _extract_image_url(self, base_selector: str, index: int) -> str | None:
        """Extract image URL from result item.

        Uses querySelectorAll indexing to reliably access the element.

        Args:
            base_selector: CSS selector matching all result items
            index: Zero-based index into querySelectorAll results

        Returns:
            Absolute image URL or None
        """
        for selector in self.config.image_selectors:
            script = f"""
            (function() {{
                var parent = document.querySelectorAll('{base_selector}')[{index}];
                if (!parent) return null;
                var el = parent.querySelector('{selector}');
                if (!el) return null;
                return el.getAttribute('src') || el.getAttribute('data-src') || null;
            }})()
            """
            src = await self.client.evaluate(script)
            if src and src not in ("null", "undefined"):
                return urljoin(self.base_url, src)

        return None

    async def check_for_no_results(self) -> bool:
        """Check if page shows a 'no results' message.

        Uses site-specific ``no_results_selectors`` when configured.
        Otherwise falls back to a heuristic text search scoped to the
        main content area (``main``, ``[role=main]``, ``#content``,
        ``.content``) to avoid false positives from footer / FAQ text.
        If no content container is found, searches ``document.body`` but
        excludes ``<header>``, ``<footer>``, and ``<nav>`` elements.

        Returns:
            True if a no-results indicator is detected.
        """
        # --- Strategy 1: explicit selectors from config ---
        if self.config.no_results_selectors:
            for selector in self.config.no_results_selectors:
                script = f"""
                (function() {{
                    var el = document.querySelector('{selector}');
                    if (!el) return false;
                    var style = window.getComputedStyle(el);
                    return style.display !== 'none' && style.visibility !== 'hidden';
                }})()
                """
                result = await self.client.evaluate(script)
                if result and str(result).lower() == "true":
                    logger.info(f"Detected no-results element via selector: '{selector}'")
                    return True
            return False

        # --- Strategy 2: heuristic text search, scoped to content area ---
        no_results_patterns = [
            "no results",
            "no items found",
            "0 results",
            "nothing found",
            "try a different search",
        ]

        # Build a JS snippet that extracts text only from the main
        # content area, excluding header/footer/nav.
        scope_script = """
        (function() {
            var container = document.querySelector('main, [role="main"], #content, .content');
            if (container) return container.textContent.toLowerCase();
            // Fallback: body text minus header/footer/nav
            var clone = document.body.cloneNode(true);
            var exclude = clone.querySelectorAll('header, footer, nav, [role="banner"], [role="contentinfo"], [role="navigation"]');
            for (var i = 0; i < exclude.length; i++) exclude[i].remove();
            return clone.textContent.toLowerCase();
        })()
        """

        scoped_text = await self.client.evaluate(scope_script)
        if not scoped_text or scoped_text in ("null", "undefined"):
            return False

        scoped_text_lower = str(scoped_text).lower()
        for pattern in no_results_patterns:
            if pattern in scoped_text_lower:
                logger.info(f"Detected no results message: '{pattern}'")
                return True

        return False
