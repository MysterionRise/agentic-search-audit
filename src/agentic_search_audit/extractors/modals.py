"""Modal and popup handling."""

import asyncio
import logging

from ..core.types import ModalsConfig
from ..mcp.client import MCPBrowserClient

logger = logging.getLogger(__name__)


class ModalHandler:
    """Handles cookie consents, popups, and modals."""

    def __init__(self, client: MCPBrowserClient, config: ModalsConfig):
        """Initialize modal handler.

        Args:
            client: MCP browser client
            config: Modals configuration
        """
        self.client = client
        self.config = config

    async def dismiss_modals(self) -> int:
        """Attempt to dismiss any visible modals.

        Returns:
            Number of modals dismissed
        """
        logger.info("Checking for modals to dismiss...")
        dismissed_count = 0

        for attempt in range(self.config.max_auto_clicks):
            # Look for buttons/links with close text
            close_button = await self._find_close_button()

            if close_button:
                try:
                    logger.debug(f"Attempting to close modal (attempt {attempt + 1})")
                    await self.client.click(close_button)
                    await asyncio.sleep(self.config.wait_after_close_ms / 1000)
                    dismissed_count += 1
                except Exception as e:
                    logger.debug(f"Failed to click close button: {e}")
                    break
            else:
                logger.debug("No more modals found")
                break

        if dismissed_count > 0:
            logger.info(f"Dismissed {dismissed_count} modal(s)")

        return dismissed_count

    async def _find_close_button(self) -> str | None:
        """Find a close button for modals.

        Returns:
            CSS selector for close button, or None
        """
        # Build regex pattern from close text matches
        pattern = "|".join(self.config.close_text_matches)

        # Common modal close button selectors
        selectors = [
            "button",
            "a",
            '[role="button"]',
            ".modal-close",
            ".close",
            '[aria-label*="close" i]',
            '[aria-label*="dismiss" i]',
        ]

        for base_selector in selectors:
            # Find all matching elements
            script = f"""
            (function() {{
                const pattern = /{pattern}/i;
                const elements = Array.from(document.querySelectorAll('{base_selector}'));

                for (let i = 0; i < elements.length; i++) {{
                    const el = elements[i];
                    const text = el.textContent || el.getAttribute('aria-label') || '';

                    if (pattern.test(text)) {{
                        // Check if element is visible
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {{
                            // Return a unique selector
                            return {{
                                selector: '{base_selector}',
                                index: i,
                                text: text.trim()
                            }};
                        }}
                    }}
                }}
                return null;
            }})()
            """

            try:
                result = await self.client.evaluate(script)
                if result and isinstance(result, str):
                    import json

                    data = json.loads(result)
                    if data:
                        # Use nth-of-type selector
                        selector = f"{data['selector']}:nth-of-type({data['index'] + 1})"
                        logger.debug(f"Found close button: {selector} with text '{data['text']}'")
                        return selector
            except Exception as e:
                logger.debug(f"Error evaluating script for {base_selector}: {e}")
                continue

        return None

    async def wait_for_page_stable(self, timeout_ms: int = 3000) -> None:
        """Wait for page to stabilize (no new modals appearing).

        Args:
            timeout_ms: Maximum wait time in milliseconds
        """
        logger.debug("Waiting for page to stabilize...")

        # Wait a bit for any delayed modals
        await asyncio.sleep(1)

        # Dismiss any modals that appeared
        await self.dismiss_modals()

        # Wait for network idle
        try:
            await self.client.wait_for_network_idle(timeout=timeout_ms)
        except Exception as e:
            logger.debug(f"Network idle timeout: {e}")

        logger.debug("Page stabilized")
