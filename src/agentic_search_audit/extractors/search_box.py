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

    async def _click_trigger(self) -> bool:
        """Click the trigger selector to reveal the search input (for overlay-style search).

        Returns:
            True if trigger was clicked and an input appeared, False on failure.
        """
        trigger = self.config.trigger_selector
        if not trigger:
            return True  # nothing to do

        try:
            safe_trigger = sanitize_css_selector(trigger)
        except ValueError as e:
            logger.error(f"Invalid trigger_selector: {e}")
            return False

        logger.info(f"Clicking search trigger: {safe_trigger}")
        try:
            await self.client.click(safe_trigger)
        except Exception as e:
            logger.error(f"Failed to click trigger_selector '{safe_trigger}': {e}")
            return False

        # Wait for at least one input selector to become visible
        for selector in self.config.input_selectors:
            try:
                appeared = await self.client.wait_for_selector(selector, timeout=5000, visible=True)
                if appeared:
                    logger.info(f"Search input appeared after trigger click: {selector}")
                    return True
            except Exception:
                continue

        logger.warning("No search input appeared after clicking trigger_selector")
        return True  # proceed anyway — find_search_box may still succeed

    async def submit_search(self, query_text: str) -> bool:
        """Find search box, enter query, and submit.

        Args:
            query_text: Text to search for

        Returns:
            True if successful, False otherwise
        """
        # Click trigger to reveal overlay search UI if configured
        if not await self._click_trigger():
            return False

        # Proactively hide any marketing/promo overlays that may block interaction
        # or prevent the search bar from rendering (e.g. Shutterfly marketing-popup)
        removed = await self._force_remove_overlays()
        if removed > 0:
            await asyncio.sleep(1.0)  # wait for page to render after overlay removal

        # Find search box
        search_selector = await self.find_search_box()
        if not search_selector and removed > 0:
            # Overlay was blocking — reload page (cookies may suppress popup now)
            logger.info("Search box not found after overlay removal — reloading page")
            await self.client.evaluate("location.reload()")
            await asyncio.sleep(3.0)
            await self._force_remove_overlays()
            await asyncio.sleep(0.5)
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
            try:
                await self.client.click(safe_selector)
            except Exception as click_err:
                if "element click intercepted" in str(click_err):
                    logger.warning(
                        "Click intercepted by overlay — force-removing overlays and retrying"
                    )
                    await self._force_remove_overlays()
                    await asyncio.sleep(0.5)
                    try:
                        await self.client.click(safe_selector)
                    except Exception as retry_err:
                        if "element click intercepted" in str(retry_err):
                            logger.warning(
                                "Click still intercepted — using JavaScript click as fallback"
                            )
                            await self.client.evaluate(
                                f'document.querySelector("{escaped_selector}").click()'
                            )
                        else:
                            raise
                else:
                    raise
            await asyncio.sleep(0.2)
            # Select all and delete using keyboard
            await self.client.evaluate(f'document.querySelector("{escaped_selector}").select()')
            await self.client.press_key("Backspace")
            await asyncio.sleep(0.2)

            # Type query
            try:
                await self.client.type_text(safe_selector, query_text, delay=30)
            except Exception as type_err:
                if "element click intercepted" in str(type_err):
                    logger.warning("type_text intercepted by overlay — using JS input fallback")
                    escaped_text = query_text.replace("\\", "\\\\").replace('"', '\\"')
                    await self.client.evaluate(f"""
                        (function() {{
                            var el = document.querySelector("{escaped_selector}");
                            if (el) {{
                                el.focus();
                                el.value = "{escaped_text}";
                                el.dispatchEvent(new Event("input", {{bubbles: true}}));
                                el.dispatchEvent(new Event("change", {{bubbles: true}}));
                            }}
                        }})()
                    """)
                else:
                    raise

            # Wait for autocomplete to load (many search boxes have autocomplete)
            await asyncio.sleep(1.0)

            # Dismiss autocomplete dropdown with Escape before submitting.
            # On sites like Sephora, Macys, Target the dropdown captures Enter
            # and navigates to the first suggestion instead of the typed query.
            await self.client.press_key("Escape")
            await asyncio.sleep(0.3)

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

    async def _force_remove_overlays(self) -> int:
        """Force-hide modal overlays blocking interaction via JavaScript.

        Uses display:none instead of remove() to avoid breaking page structure.
        Also removes any body scroll locks that overlays may have set.

        Returns:
            Number of overlays hidden
        """
        try:
            result = await self.client.evaluate("""
                (function() {
                    var hidden = 0;
                    // Target specific marketing/promo overlay patterns
                    var selectors = [
                        '.modal-overlay.marketing-popup',
                        '.modal-overlay.newsletter-popup',
                        '.modal-overlay.promo-popup',
                        '[class*="marketing-popup"]',
                        '[class*="newsletter-popup"]',
                        '[class*="promo-popup"]',
                        '[class*="signup-modal"]',
                        '[class*="email-capture"]',
                        '[class*="email-popup"]',
                        '[class*="popup-overlay"]',
                        '[class*="authDialog"]',
                        '[class*="auth-dialog"]',
                        '[class*="auth-modal"]',
                        '[class*="login-modal"]',
                        '[class*="signin-modal"]',
                        '[data-testid="modal-dialog"]',
                        '[data-testid="modal-overlay"]',
                        '[class*="controls-overlay"]'
                    ];
                    for (var i = 0; i < selectors.length; i++) {
                        var elements = document.querySelectorAll(selectors[i]);
                        for (var j = 0; j < elements.length; j++) {
                            var el = elements[j];
                            var rect = el.getBoundingClientRect();
                            if (rect.width > 200 && rect.height > 200) {
                                el.style.display = 'none';
                                hidden++;
                            }
                        }
                    }
                    // Also hide any generic .modal-overlay that has high z-index AND
                    // fixed/absolute position (require both to avoid false positives)
                    var overlays = document.querySelectorAll('.modal-overlay');
                    for (var k = 0; k < overlays.length; k++) {
                        var ov = overlays[k];
                        var style = window.getComputedStyle(ov);
                        var zIndex = parseInt(style.zIndex) || 0;
                        var isOverlay = zIndex > 100
                            && (style.position === 'fixed' || style.position === 'absolute');
                        if (isOverlay) {
                            ov.style.display = 'none';
                            hidden++;
                        }
                    }
                    // Hide any high-z-index fixed/absolute overlay blocking the page
                    // (catch-all for auth dialogs, signup prompts, etc.)
                    var allDivs = document.querySelectorAll('div[class]');
                    for (var m = 0; m < allDivs.length; m++) {
                        var d = allDivs[m];
                        if (d.style.display === 'none') continue;
                        var ds = window.getComputedStyle(d);
                        var dz = parseInt(ds.zIndex) || 0;
                        if (dz > 500
                            && (ds.position === 'fixed' || ds.position === 'absolute')
                            && d.getBoundingClientRect().width > 200
                            && d.getBoundingClientRect().height > 200) {
                            d.style.display = 'none';
                            hidden++;
                        }
                    }
                    // Only clear body scroll lock if we actually hid overlays
                    if (hidden > 0) {
                        document.body.style.overflow = '';
                        document.body.style.position = '';
                        document.documentElement.style.overflow = '';
                    }
                    return hidden;
                })()
            """)
            count = int(result) if result else 0
            if count > 0:
                logger.info(f"Force-hidden {count} blocking overlay(s)")
            return count
        except Exception as e:
            logger.debug(f"Force overlay removal failed: {e}")
            return 0

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
