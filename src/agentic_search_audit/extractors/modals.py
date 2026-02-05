"""Modal and popup handling."""

import asyncio
import logging

from ..core.types import ModalsConfig
from ..mcp.client import MCPBrowserClient

logger = logging.getLogger(__name__)

# Common cookie consent selectors for popular consent management platforms
COOKIE_CONSENT_SELECTORS = [
    # OneTrust
    "#onetrust-accept-btn-handler",
    ".onetrust-close-btn-handler",
    "#accept-recommended-btn-handler",
    # Cookiebot
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "#CybotCookiebotDialogBodyButtonAccept",
    # TrustArc/TrustE
    ".trustarc-agree-btn",
    ".call[data-accept]",
    # Quantcast
    ".qc-cmp2-summary-buttons button[mode='primary']",
    # Generic consent buttons (common patterns)
    "[data-testid='uc-accept-all-button']",
    "[data-testid='accept-all']",
    "[data-testid='cookie-accept']",
    "button[id*='accept']",
    "button[class*='accept']",
    "button[class*='consent']",
    "button[class*='cookie'][class*='accept']",
    # Zalando-specific (uses Usercentrics)
    "#uc-btn-accept-banner",
    "[data-testid='uc-accept-all-button']",
    "button[data-testid*='accept']",
    # Common aria labels
    "[aria-label*='Accept all' i]",
    "[aria-label*='Accept cookies' i]",
    "[aria-label*='Accept All' i]",
]


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

        # First, try common cookie consent selectors (most reliable)
        consent_dismissed = await self._try_cookie_consent_selectors()
        dismissed_count += consent_dismissed

        # Then try text-based matching for other modals
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

    async def _try_cookie_consent_selectors(self) -> int:
        """Try common cookie consent button selectors.

        Returns:
            Number of consent dialogs dismissed
        """
        dismissed = 0

        # First, try regular selectors
        for selector in COOKIE_CONSENT_SELECTORS:
            try:
                # Check if selector exists and is visible
                result = await self.client.query_selector(selector)
                if result:
                    logger.info(f"Found cookie consent button: {selector}")
                    await self.client.click(selector)
                    await asyncio.sleep(self.config.wait_after_close_ms / 1000)
                    dismissed += 1
                    # Usually only one consent dialog, but check for nested dialogs
                    break
            except Exception as e:
                logger.debug(f"Selector {selector} not found or failed: {e}")
                continue

        # If no consent found, try Usercentrics API and shadow DOM search
        if dismissed == 0:
            # Try Usercentrics consent API first (common on many EU sites)
            try:
                result = await self.client.evaluate("""
                    (function() {
                        // Try Usercentrics API
                        if (typeof UC_UI !== 'undefined' && UC_UI.acceptAllConsents) {
                            UC_UI.acceptAllConsents();
                            return 'uc_api';
                        }
                        // Try window.__ucCmp
                        if (window.__ucCmp && window.__ucCmp.acceptAllConsents) {
                            window.__ucCmp.acceptAllConsents();
                            return 'uc_cmp';
                        }
                        return false;
                    })()
                """)
                if result and result not in ["false", "undefined", "null"]:
                    logger.info(f"Dismissed consent via Usercentrics API: {result}")
                    await asyncio.sleep(self.config.wait_after_close_ms / 1000)
                    dismissed += 1
            except Exception as e:
                logger.debug(f"Usercentrics API consent failed: {e}")

        # Try clicking any visible button with accept-like text
        if dismissed == 0:
            try:
                result = await self.client.evaluate("""
                    (function() {
                        // Find all visible buttons and links with accept-like text
                        const acceptPatterns = /accept|agree|allow|consent/i;
                        const rejectPatterns = /reject|decline|deny|necessary only/i;

                        const candidates = Array.from(document.querySelectorAll(
                            'button, [role="button"], a[href="#"]'
                        ));

                        for (const el of candidates) {
                            const text = (el.textContent || el.innerText || '').trim();
                            const rect = el.getBoundingClientRect();

                            // Skip if not visible
                            if (rect.width === 0 || rect.height === 0) continue;
                            if (rect.bottom < 0 || rect.top > window.innerHeight) continue;

                            // Prefer "Accept All" type buttons, avoid reject buttons
                            if (acceptPatterns.test(text) && !rejectPatterns.test(text)) {
                                el.click();
                                return text.substring(0, 50);
                            }
                        }
                        return false;
                    })()
                """)
                if result and result not in ["false", "undefined", "null"]:
                    logger.info(f"Clicked consent button with text: {result}")
                    await asyncio.sleep(self.config.wait_after_close_ms / 1000)
                    dismissed += 1
            except Exception as e:
                logger.debug(f"Direct button click consent failed: {e}")

        # Try shadow DOM search if nothing worked
        if dismissed == 0:
            try:
                result = await self.client.evaluate("""
                    (function() {
                        // Try to find consent button by text in shadow DOMs
                        const acceptTexts = ['Accept All', 'Accept all', 'Agree', 'Accept'];

                        // Helper to search within element and its shadow DOM
                        function findButtonInElement(root) {
                            // Check buttons in this root
                            const buttons = root.querySelectorAll('button, [role="button"]');
                            for (const btn of buttons) {
                                const text = btn.textContent || btn.innerText || '';
                                for (const acceptText of acceptTexts) {
                                    if (text.includes(acceptText)) {
                                        return btn;
                                    }
                                }
                            }
                            // Check shadow roots
                            const elements = root.querySelectorAll('*');
                            for (const el of elements) {
                                if (el.shadowRoot) {
                                    const found = findButtonInElement(el.shadowRoot);
                                    if (found) return found;
                                }
                            }
                            return null;
                        }

                        const btn = findButtonInElement(document);
                        if (btn) {
                            btn.click();
                            return true;
                        }
                        return false;
                    })()
                """)
                if result == "true":
                    logger.info("Found and clicked consent button via shadow DOM search")
                    await asyncio.sleep(self.config.wait_after_close_ms / 1000)
                    dismissed += 1
            except Exception as e:
                logger.debug(f"Shadow DOM consent search failed: {e}")

        return dismissed

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
