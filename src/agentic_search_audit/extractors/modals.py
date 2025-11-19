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
        # First try common cookie consent framework selectors directly
        direct_selectors = [
            # OneTrust
            '#onetrust-accept-btn-handler',
            'button[id*="accept"]',
            # Cookiebot
            '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
            '.CybotCookiebotDialogBodyButton',
            # Cookie Consent
            '.cc-btn.cc-dismiss',
            '.cc-allow',
            # Generic cookie selectors
            '[data-testid*="cookie"][data-testid*="accept"]',
            '[class*="cookie"][class*="accept"]',
            '[id*="cookie"][id*="accept"]',
            'button[class*="consent"][class*="accept"]',
        ]

        for selector in direct_selectors:
            try:
                element = await self.client.query_selector(selector)
                if element:
                    # Verify it's visible
                    script = f"""
                    (function() {{
                        const el = document.querySelector('{selector}');
                        if (!el) return false;
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    }})()
                    """
                    is_visible = await self.client.evaluate(script)
                    if is_visible:
                        logger.debug(f"Found cookie button with direct selector: {selector}")
                        return selector
            except Exception as e:
                logger.debug(f"Error checking selector {selector}: {e}")
                continue

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
                            // Generate a unique ID if it doesn't have one
                            if (!el.id) {{
                                el.id = 'modal-close-' + Date.now() + '-' + i;
                            }}
                            return {{
                                id: el.id,
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
                    if data and data.get('id'):
                        # Use ID selector for reliability
                        selector = f"#{data['id']}"
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
