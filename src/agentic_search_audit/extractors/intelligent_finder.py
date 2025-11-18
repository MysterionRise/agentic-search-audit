"""Intelligent search box detection using LLM and vision."""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from ..mcp.client import MCPBrowserClient

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

    def __init__(self, client: MCPBrowserClient, llm_model: str = "gpt-4o-mini"):
        """Initialize intelligent finder.

        Args:
            client: MCP browser client
            llm_model: OpenAI model with vision capability
        """
        self.client = client
        self.llm_model = llm_model

        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        self.openai_client = AsyncOpenAI(api_key=api_key)

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

    async def _analyze_page(self, screenshot_base64: str, html_snippet: str) -> dict[str, Any] | None:
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

            # Call OpenAI with vision
            response = await self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{screenshot_base64}",
                                    "detail": "high",
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=1000,
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            # Parse response
            content = response.choices[0].message.content
            if not content:
                return None

            result = json.loads(content)
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
