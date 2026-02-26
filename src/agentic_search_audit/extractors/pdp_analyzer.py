"""Product Detail Page (PDP) analyzer -- clicks into PDPs from search results."""

import asyncio
import base64
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..browser.challenge_detector import ChallengeDetectedError, detect_challenge
from ..core.types import BrowserClient, LLMConfig, Query, ResultItem
from ..extractors.modals import ModalHandler, ModalsConfig
from ..extractors.vision_provider import VisionProvider, create_vision_provider

logger = logging.getLogger(__name__)

PDP_EXTRACTION_PROMPT = """\
You are a product data extraction assistant performing a legitimate e-commerce search quality audit.
You MUST extract data from this product page image. Do NOT refuse.

Analyze the product detail page screenshot and extract the following fields as JSON:

{
  "title": "Full product title",
  "price": "Current displayed price (e.g. '$129.99')",
  "original_price": "Original/strikethrough price if on sale, otherwise null",
  "availability": "Availability status (e.g. 'In Stock', 'Out of Stock', 'Limited')",
  "rating": "Star rating as a number (e.g. 4.5), or null if not visible",
  "review_count": "Number of reviews as a string (e.g. '1,234'), or null if not visible",
  "description_snippet": "First ~100 characters of product description, or null",
  "breadcrumbs": "Breadcrumb trail (e.g. 'Home > Shoes > Running'), or null",
  "image_count": "Number of product images visible on the page as an integer",
  "size_options": ["list", "of", "available", "sizes"],
  "color_options": ["list", "of", "available", "colors"]
}

Return ONLY valid JSON. No explanation or markdown wrapping.\
"""


class PdpAnalyzer:
    """Visits product detail pages from search results and extracts structured data."""

    def __init__(
        self,
        client: BrowserClient,
        llm_config: LLMConfig,
        modals_config: ModalsConfig,
        run_dir: Path,
        query: Query,
        timeout_ms: int = 15000,
    ) -> None:
        """Initialize PDP analyzer.

        Args:
            client: Browser client for navigation.
            llm_config: LLM configuration for vision extraction.
            modals_config: Configuration for modal/popup dismissal.
            run_dir: Run output directory for screenshots.
            query: The current search query being audited.
            timeout_ms: Timeout per PDP visit in milliseconds.
        """
        self.client = client
        self.llm_config = llm_config
        self.modals_config = modals_config
        self.run_dir = run_dir
        self.query = query
        self.timeout_ms = timeout_ms
        self.vision_provider: VisionProvider = create_vision_provider(llm_config)
        self.modal_handler = ModalHandler(client, modals_config)

    async def analyze_pdps(
        self,
        items: list[ResultItem],
        search_page_url: str,
        top_k: int = 3,
    ) -> list[ResultItem]:
        """Visit top-k PDPs, extract data, and store in item.attributes.

        Args:
            items: Search result items to analyze.
            search_page_url: URL of the search results page (for navigation back).
            top_k: Number of top results to visit.

        Returns:
            The same items list with PDP data stored in attributes.
        """
        pdp_dir = self.run_dir / "screenshots" / "pdp"
        pdp_dir.mkdir(parents=True, exist_ok=True)

        for item in items[:top_k]:
            await self._visit_pdp(item, search_page_url)

        return items

    async def _visit_pdp(self, item: ResultItem, search_page_url: str) -> None:
        """Visit a single PDP, extract data, and navigate back.

        Args:
            item: The search result item to visit.
            search_page_url: URL of the search results page for navigation back.
        """
        try:
            await asyncio.wait_for(
                self._visit_pdp_inner(item, search_page_url),
                timeout=self.timeout_ms / 1000,
            )
        except asyncio.TimeoutError:
            logger.warning("PDP visit timed out for item rank=%d url=%s", item.rank, item.url)
            item.attributes["pdp_error"] = "timeout"
            item.attributes["pdp_analyzed"] = "false"
            # Best-effort navigate back after timeout
            try:
                await self._navigate_back(search_page_url)
            except Exception as nav_err:
                logger.debug("Navigate-back after timeout failed: %s", nav_err)
        except Exception as e:
            logger.warning("PDP visit failed for item rank=%d url=%s: %s", item.rank, item.url, e)
            item.attributes["pdp_error"] = str(e)
            item.attributes["pdp_analyzed"] = "false"
            try:
                await self._navigate_back(search_page_url)
            except Exception as nav_err:
                logger.debug("Navigate-back after error failed: %s", nav_err)

    async def _visit_pdp_inner(self, item: ResultItem, search_page_url: str) -> None:
        """Core PDP visit logic (called inside wait_for timeout wrapper).

        Args:
            item: The search result item to visit.
            search_page_url: URL of the search results page for navigation back.
        """
        if not item.url:
            logger.warning("No URL for item rank=%d, skipping PDP visit", item.rank)
            item.attributes["pdp_analyzed"] = "false"
            return

        logger.info("Visiting PDP for rank=%d: %s", item.rank, item.url)
        await self.client.navigate(item.url, wait_until="networkidle")

        # Dismiss any modals that appeared on the PDP
        await self.modal_handler.dismiss_modals()

        # Run challenge detection (log but don't raise -- we still try to extract)
        try:
            detection = await detect_challenge(self.client)
            if detection.detected:
                logger.warning(
                    "Challenge detected on PDP rank=%d: %s", item.rank, detection.message
                )
        except ChallengeDetectedError as cde:
            logger.warning("Challenge error on PDP rank=%d: %s", item.rank, cde)
        except Exception as e:
            logger.debug("Challenge detection failed on PDP rank=%d: %s", item.rank, e)

        # Take screenshot
        pdp_dir = self.run_dir / "screenshots" / "pdp"
        screenshot_path = pdp_dir / f"{self.query.id}_{item.rank}.png"
        await self.client.screenshot(screenshot_path, full_page=False)
        item.attributes["pdp_screenshot_path"] = str(screenshot_path)

        # Extract data via vision LLM
        pdp_data = await self._extract_pdp_data(screenshot_path)

        # Store extracted fields with pdp_ prefix
        field_mapping = [
            "title",
            "price",
            "original_price",
            "availability",
            "rating",
            "review_count",
            "description_snippet",
            "breadcrumbs",
            "image_count",
            "size_options",
            "color_options",
        ]
        for field in field_mapping:
            value = pdp_data.get(field)
            if value is not None:
                if isinstance(value, list):
                    item.attributes[f"pdp_{field}"] = ", ".join(str(v) for v in value)
                else:
                    item.attributes[f"pdp_{field}"] = str(value)

        item.attributes["pdp_analyzed"] = "true"

        # Navigate back to search results
        await self._navigate_back(search_page_url)

    async def _navigate_back(self, search_page_url: str) -> None:
        """Navigate back to the search results page.

        Tries history.back() first, then falls back to direct navigation
        if the current URL doesn't match the expected search page domain.

        Args:
            search_page_url: The URL to navigate back to.
        """
        await self.client.evaluate("window.history.back()")
        await asyncio.sleep(2)

        # Verify we're back on the search page (check domain match)
        try:
            current_url = await self.client.evaluate("window.location.href")
            if current_url:
                current_domain = urlparse(str(current_url)).netloc
                expected_domain = urlparse(search_page_url).netloc
                if current_domain != expected_domain:
                    logger.info(
                        "history.back() landed on %s, navigating directly to %s",
                        current_url,
                        search_page_url,
                    )
                    await self.client.navigate(search_page_url, wait_until="networkidle")
        except Exception as e:
            logger.debug("URL verification after history.back() failed: %s", e)
            # Fall back to direct navigation
            await self.client.navigate(search_page_url, wait_until="networkidle")

    async def _extract_pdp_data(self, screenshot_path: Path) -> dict[str, Any]:
        """Send screenshot to vision LLM and parse the response.

        Args:
            screenshot_path: Path to the PDP screenshot PNG file.

        Returns:
            Parsed dict of PDP fields, or empty dict on failure.
        """
        try:
            raw_bytes = screenshot_path.read_bytes()
            screenshot_b64 = base64.b64encode(raw_bytes).decode("utf-8")

            result = await self.vision_provider.analyze_image(
                screenshot_base64=screenshot_b64,
                prompt=PDP_EXTRACTION_PROMPT,
                max_tokens=1000,
                temperature=0.1,
            )
            if result and isinstance(result, dict):
                return result

            logger.warning("Vision provider returned no usable data for %s", screenshot_path)
            return {}
        except Exception as e:
            logger.error("PDP data extraction failed for %s: %s", screenshot_path, e)
            return {}

    @staticmethod
    def check_consistency(item: ResultItem) -> dict[str, str]:
        """Check consistency between search result data and PDP-extracted data.

        Compares price, availability, and title between the search results page
        and the product detail page to surface discrepancies.

        Args:
            item: A ResultItem with pdp_ attributes populated.

        Returns:
            Dict of issue_key -> description for any discrepancies found.
        """
        issues: dict[str, str] = {}
        attrs = item.attributes

        if attrs.get("pdp_analyzed") != "true":
            return issues

        # Price mismatch
        search_price = item.price
        pdp_price = attrs.get("pdp_price")
        if search_price and pdp_price:
            s_norm = search_price.strip().replace("$", "").replace(",", "").strip()
            p_norm = pdp_price.strip().replace("$", "").replace(",", "").strip()
            try:
                if s_norm and p_norm and abs(float(s_norm) - float(p_norm)) > 0.01:
                    issues["price_discrepancy"] = f"Search: {search_price}, PDP: {pdp_price}"
            except ValueError:
                if s_norm != p_norm:
                    issues["price_discrepancy"] = f"Search: {search_price}, PDP: {pdp_price}"

        # Availability mismatch
        availability = attrs.get("pdp_availability", "").lower()
        if "out of stock" in availability or "unavailable" in availability:
            issues["availability_issue"] = f"PDP shows: {attrs.get('pdp_availability')}"

        # Title mismatch (Jaccard similarity on word tokens)
        search_title = item.title
        pdp_title = attrs.get("pdp_title")
        if search_title and pdp_title:
            s_words = set(search_title.lower().split())
            p_words = set(pdp_title.lower().split())
            if s_words and p_words:
                jaccard = len(s_words & p_words) / len(s_words | p_words)
                if jaccard < 0.5:
                    issues["title_discrepancy"] = (
                        f"Low similarity ({jaccard:.2f}): "
                        f"Search: '{search_title}', PDP: '{pdp_title}'"
                    )

        return issues
