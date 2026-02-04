"""Search box detection and interaction."""

import logging

from ..core.types import LLMConfig, SearchConfig
from ..mcp.client import MCPBrowserClient
from .intelligent_finder import IntelligentSearchBoxFinder

logger = logging.getLogger(__name__)


class SearchBoxFinder:
    """Finds and interacts with search input boxes."""

    def __init__(
        self,
        client: MCPBrowserClient,
        config: SearchConfig,
        llm_config: LLMConfig,
        use_intelligent_fallback: bool = True,
    ):
        """Initialize search box finder.

        Args:
            client: MCP browser client
            config: Search configuration
            llm_config: LLM configuration for vision-based detection
            use_intelligent_fallback: Use LLM-based detection if CSS selectors fail
        """
        self.client = client
        self.config = config
        self.llm_config = llm_config
        self.use_intelligent_fallback = use_intelligent_fallback
        self._intelligent_finder: IntelligentSearchBoxFinder | None = None

    async def find_search_box(self) -> str | None:
        """Find the search input box using configured selectors.

        First tries traditional CSS selectors, then falls back to LLM-based
        intelligent detection if enabled.

        Returns:
            CSS selector of found search box, or None if not found
        """
        logger.info("Searching for search input box...")

        # Try traditional CSS selectors first
        for selector in self.config.input_selectors:
            logger.debug(f"Trying selector: {selector}")

            # Try to find element
            element = await self.client.query_selector(selector)
            if element:
                logger.info(f"Found search box with selector: {selector}")
                return selector

        logger.warning("No search box found with configured selectors")

        # Fall back to intelligent detection
        if self.use_intelligent_fallback:
            logger.info("Falling back to intelligent LLM-based detection...")
            return await self._intelligent_find()

        return None

    async def _intelligent_find(self) -> str | None:
        """Use LLM to intelligently find the search box.

        Returns:
            CSS selector of found search box, or None if not found
        """
        try:
            # Initialize intelligent finder if needed
            if not self._intelligent_finder:
                self._intelligent_finder = IntelligentSearchBoxFinder(
                    self.client, llm_config=self.llm_config
                )

            # Find search box using LLM
            result = await self._intelligent_finder.find_search_box()

            if not result or not result.get("selectors"):
                return None

            # Validate and use the suggested selectors
            for selector in result["selectors"]:
                if await self._intelligent_finder.validate_selector(selector):
                    logger.info(f"LLM found valid search box: {selector}")

                    # Update config with discovered strategy
                    if result.get("submit_strategy"):
                        self.config.submit_strategy = result["submit_strategy"]
                    if result.get("submit_selector"):
                        self.config.submit_selector = result["submit_selector"]

                    return str(selector)

            logger.warning("LLM suggested selectors but none were valid")
            return None

        except Exception as e:
            logger.error(f"Intelligent search box detection failed: {e}")
            return None

    async def submit_search(self, query_text: str) -> bool:
        """Find search box, enter query, and submit.

        Args:
            query_text: Text to search for

        Returns:
            True if successful, False otherwise
        """
        # Find search box
        search_selector = await self.find_search_box()
        if not search_selector:
            logger.error("Could not find search box")
            return False

        try:
            # Clear any existing text
            await self.client.evaluate(f'document.querySelector("{search_selector}").value = ""')

            # Type query
            await self.client.type_text(search_selector, query_text, delay=30)

            # Submit based on strategy
            if self.config.submit_strategy == "enter":
                logger.debug("Submitting search with Enter key")
                await self.client.press_key("Enter")

            elif self.config.submit_strategy == "clickSelector" and self.config.submit_selector:
                logger.debug(f"Submitting search by clicking {self.config.submit_selector}")
                await self.client.click(self.config.submit_selector)

            else:
                logger.error(f"Invalid submit strategy: {self.config.submit_strategy}")
                return False

            logger.info(f"Successfully submitted search for: {query_text}")
            return True

        except Exception as e:
            logger.error(f"Failed to submit search: {e}")
            return False

    async def get_search_suggestions(self) -> list[str]:
        """Get search suggestions if available (for future use).

        Returns:
            List of suggestion texts
        """
        # Common selectors for search suggestions
        suggestion_selectors = [
            '[role="option"]',
            ".search-suggestion",
            '[data-testid*="suggestion"]',
            ".autocomplete-item",
        ]

        suggestions = []
        for selector in suggestion_selectors:
            elements = await self.client.query_selector_all(selector)
            if elements:
                for elem in elements:
                    text = await self.client.get_element_text(selector)
                    if text:
                        suggestions.append(text)
                break

        return suggestions
