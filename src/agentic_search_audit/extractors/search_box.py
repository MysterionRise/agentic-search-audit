"""Search box detection and interaction."""

import asyncio
import logging
import re

from ..core.types import BrowserClient, LLMConfig, SearchConfig
from .intelligent_finder import IntelligentSearchBoxFinder

logger = logging.getLogger(__name__)

# Pattern to validate CSS selectors - only allow safe characters
# This prevents JavaScript injection via malicious selectors
CSS_SELECTOR_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\[\]="\'\.#:,\s\*\(\)>+~^$|]+$')


def sanitize_css_selector(selector: str) -> str:
    """Sanitize a CSS selector to prevent JavaScript injection.

    Args:
        selector: CSS selector to sanitize

    Returns:
        Sanitized selector

    Raises:
        ValueError: If selector contains potentially dangerous characters
    """
    if not selector or not isinstance(selector, str):
        raise ValueError("Invalid selector: must be a non-empty string")

    # Remove any null bytes or control characters
    selector = selector.replace("\x00", "").strip()

    # Check against whitelist pattern
    if not CSS_SELECTOR_PATTERN.match(selector):
        raise ValueError(f"Invalid CSS selector: contains disallowed characters: {selector!r}")

    # Additional checks for potential injection patterns
    dangerous_patterns = [
        "javascript:",
        "data:",
        "<script",
        "</script",
        "onerror",
        "onload",
        "onclick",
        "onmouse",
        "onfocus",
        "onblur",
        "eval(",
        "expression(",
    ]

    selector_lower = selector.lower()
    for pattern in dangerous_patterns:
        if pattern in selector_lower:
            raise ValueError(f"Invalid CSS selector: contains dangerous pattern: {pattern}")

    return selector


class SearchBoxFinder:
    """Finds and interacts with search input boxes."""

    def __init__(
        self,
        client: BrowserClient,
        config: SearchConfig,
        llm_config: LLMConfig,
        use_intelligent_fallback: bool = True,
    ):
        """Initialize search box finder.

        Args:
            client: Browser client (Playwright or MCP)
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
            # Sanitize selector to prevent JavaScript injection
            try:
                safe_selector = sanitize_css_selector(search_selector)
            except ValueError as e:
                logger.error(f"Invalid search selector: {e}")
                return False

            # Escape selector for use in JavaScript string
            # Replace backslashes first, then quotes
            escaped_selector = safe_selector.replace("\\", "\\\\").replace('"', '\\"')

            # Clear any existing text using multiple approaches for reliability
            # 1. Set value to empty (works for simple inputs)
            await self.client.evaluate(f'document.querySelector("{escaped_selector}").value = ""')
            # 2. Also dispatch input event for React/Angular frameworks
            await self.client.evaluate(f"""
                (function() {{
                    const input = document.querySelector("{escaped_selector}");
                    if (input) {{
                        input.value = "";
                        input.dispatchEvent(new Event("input", {{ bubbles: true }}));
                        input.dispatchEvent(new Event("change", {{ bubbles: true }}));
                    }}
                }})()
            """)
            # 3. Click to focus and use keyboard shortcuts as fallback
            await self.client.click(safe_selector)
            await asyncio.sleep(0.2)
            # Select all and delete using keyboard
            await self.client.evaluate(f'document.querySelector("{escaped_selector}").select()')
            await self.client.press_key("Backspace")
            await asyncio.sleep(0.2)

            # Type query
            await self.client.type_text(safe_selector, query_text, delay=30)

            # Wait for autocomplete to load (many search boxes have autocomplete)
            await asyncio.sleep(1.0)

            # Submit based on strategy
            if self.config.submit_strategy == "enter":
                logger.debug("Submitting search with Enter key")
                # Focus the input element first
                await self.client.evaluate(f"""
                    (function() {{
                        const input = document.querySelector("{escaped_selector}");
                        if (input) {{
                            input.focus();
                            return true;
                        }}
                        return false;
                    }})()
                """)
                await asyncio.sleep(0.3)
                # Use native MCP press_key for Enter
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
