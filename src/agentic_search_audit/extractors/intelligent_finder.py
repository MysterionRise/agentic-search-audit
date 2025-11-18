"""Intelligent search box detection using LLM and vision."""

import base64
import logging
from pathlib import Path
from typing import Any

from ..core.types import LLMConfig
from ..mcp.client import MCPBrowserClient
from .vision_provider import create_vision_provider, VisionProvider

logger = logging.getLogger(__name__)


SEARCH_BOX_FINDER_PROMPT = """You are a web automation expert. Analyze this webpage screenshot and HTML to find the search input box.

Your task:
1. Identify the main search input field on the page
2. Provide CSS selectors that can uniquely identify this element
3. Suggest the best way to submit the search (pressing Enter or clicking a button)

Return your response as JSON with this structure:
{
  "selectors": ["selector1", "selector2", "selector3"],
  "submit_strategy": "enter" or "clickSelector",
  "submit_selector": "button selector if applicable, else null",
  "confidence": "high", "medium", or "low",
  "reasoning": "Brief explanation of your selection"
}

Provide multiple selector options ordered by reliability (most reliable first).
Consider:
- input[type="search"]
- input elements with search-related aria-labels
- input elements with search-related names, IDs, or classes
- input elements with search-related placeholders

Be specific and use attributes that are unlikely to change (data-testid, aria-label, etc. are better than generic classes).

HTML snippet:
{html_snippet}
"""


class IntelligentSearchBoxFinder:
    """Uses LLM with vision to intelligently find search boxes."""

    def __init__(self, client: MCPBrowserClient, llm_config: LLMConfig):
        """Initialize intelligent finder.

        Args:
            client: MCP browser client
            llm_config: LLM configuration including provider and model
        """
        self.client = client
        self.llm_config = llm_config

        # Initialize vision provider based on config
        self.vision_provider: VisionProvider = create_vision_provider(llm_config)

    async def find_search_box(self) -> dict[str, Any] | None:
        """Use LLM to find the search box on the current page.

        Returns:
            Dictionary with selectors and strategy, or None if not found
        """
        logger.info("Using intelligent search box detection...")

        try:
            # Get screenshot
            screenshot_path = Path("/tmp/search_detection.png")
            await self.client.screenshot(screenshot_path, full_page=False)

            # Get HTML
            html_content = await self.client.get_html()

            # Prepare HTML snippet (first 5000 chars to include header/nav area)
            html_snippet = html_content[:5000]

            # Read screenshot as base64
            with open(screenshot_path, "rb") as f:
                screenshot_base64 = base64.b64encode(f.read()).decode("utf-8")

            # Call LLM with vision
            result = await self._analyze_page(screenshot_base64, html_snippet)

            if result and result.get("confidence") in ["high", "medium"]:
                logger.info(
                    f"Found search box with {result['confidence']} confidence: "
                    f"{result['selectors'][0] if result['selectors'] else 'none'}"
                )
                logger.info(f"Reasoning: {result.get('reasoning', 'N/A')}")
                return result
            else:
                logger.warning("LLM could not find search box with sufficient confidence")
                return None

        except Exception as e:
            logger.error(f"Intelligent search box detection failed: {e}", exc_info=True)
            return None

    async def _analyze_page(
        self, screenshot_base64: str, html_snippet: str
    ) -> dict[str, Any] | None:
        """Analyze page with LLM vision.

        Args:
            screenshot_base64: Base64-encoded screenshot
            html_snippet: HTML snippet of the page

        Returns:
            Analysis result or None
        """
        try:
            # Build prompt
            prompt = SEARCH_BOX_FINDER_PROMPT.format(html_snippet=html_snippet)

            # Use vision provider to analyze
            result = await self.vision_provider.analyze_image(
                screenshot_base64=screenshot_base64,
                prompt=prompt,
                max_tokens=self.llm_config.max_tokens,
                temperature=self.llm_config.temperature,
            )

            return result

        except Exception as e:
            logger.error(f"Failed to analyze page with LLM: {e}")
            return None

    async def validate_selector(self, selector: str) -> bool:
        """Validate that a selector exists on the page.

        Args:
            selector: CSS selector to validate

        Returns:
            True if selector is valid and element exists
        """
        try:
            element = await self.client.query_selector(selector)
            return element is not None
        except Exception as e:
            logger.debug(f"Selector validation failed for {selector}: {e}")
            return False
