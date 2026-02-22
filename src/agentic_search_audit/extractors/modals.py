"""Modal and popup handling."""

import asyncio
import logging

from ..core.types import BrowserClient, LocationConfig, ModalsConfig

logger = logging.getLogger(__name__)

# Common location/region/shipping modal selectors for US retailers
LOCATION_MODAL_SELECTORS = [
    # Generic location/shipping modals
    '[data-testid="location-modal"]',
    '[data-testid="ship-to-modal"]',
    '[data-testid="geo-modal"]',
    '[data-testid="store-selector-modal"]',
    '[data-test="locationModal"]',
    '[data-test="geoModal"]',
    # Common class patterns
    '[class*="location-modal"]',
    '[class*="ship-to"]',
    '[class*="geo-restriction"]',
    '[class*="geo-modal"]',
    '[class*="country-selector"]',
    '[class*="region-selector"]',
    '[class*="store-selector"]',
    '[class*="zipcode-modal"]',
    # Aria patterns
    '[aria-label*="location" i]',
    '[aria-label*="ship to" i]',
    '[aria-label*="choose your country" i]',
    '[aria-label*="select country" i]',
    '[aria-label*="select your location" i]',
    # Common id patterns
    '[id*="location-modal"]',
    '[id*="ship-to"]',
    '[id*="geo-modal"]',
    '[id*="country-select"]',
    '[id*="zipcode-modal"]',
    '[id*="store-locator-modal"]',
    # Walmart-specific
    '[data-automation-id="fulfillment-modal"]',
    '[data-tl-id="GlobalLocationSelector"]',
    # Target-specific
    '[data-test="@web/ZipCodeModalContent"]',
    '[data-test="storeIdModal"]',
    # Nike-specific
    '[data-testid="geolocation-modal"]',
    # Best Buy-specific
    '[class*="change-store"]',
    '[data-testid="store-selector"]',
]

# Common cookie consent selectors for popular consent management platforms
COOKIE_CONSENT_SELECTORS = [
    # OneTrust
    "#onetrust-accept-btn-handler",
    ".onetrust-close-btn-handler",
    "#accept-recommended-btn-handler",
    # OneTrust reject/necessary only
    "#onetrust-reject-all-handler",
    # Cookiebot
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "#CybotCookiebotDialogBodyButtonAccept",
    "#CybotCookiebotDialogBodyButtonDecline",
    # TrustArc/TrustE
    ".trustarc-agree-btn",
    ".call[data-accept]",
    # Quantcast
    ".qc-cmp2-summary-buttons button[mode='primary']",
    ".qc-cmp2-summary-buttons button[mode='secondary']",
    # John Lewis specific
    "[data-test='cookie-accept-all']",
    "[data-test='cookie-reject-all']",
    "[data-testid='cookie-banner-accept']",
    "[data-testid='cookie-banner-reject']",
    "button[class*='CookieBanner']",
    # Generic consent buttons (common patterns)
    "[data-testid='uc-accept-all-button']",
    "[data-testid='uc-deny-all-button']",
    "[data-testid='accept-all']",
    "[data-testid='reject-all']",
    "[data-testid='cookie-accept']",
    "[data-testid='cookie-reject']",
    "button[id*='accept']",
    "button[id*='reject']",
    "button[class*='accept']",
    "button[class*='reject']",
    "button[class*='consent']",
    "button[class*='cookie'][class*='accept']",
    "button[class*='cookie'][class*='reject']",
    # Zalando-specific (uses Usercentrics)
    "#uc-btn-accept-banner",
    "#uc-btn-deny-banner",
    "[data-testid='uc-accept-all-button']",
    "[data-testid='uc-deny-all-button']",
    "button[data-testid*='accept']",
    "button[data-testid*='deny']",
    # Didomi (Le Monde, 20 Minutes, and other French/EU sites)
    "#didomi-notice-agree-button",
    ".didomi-popup-notice-buttons button",
    ".didomi-consent-popup-actions button.didomi-components-button--color",
    # Axeptio (French sites)
    "#axeptio_btn_acceptAll",
    ".axeptio-widget button[aria-label*='accept' i]",
    # Iubenda (Italian sites)
    ".iubenda-cs-accept-btn",
    "#iubenda-cs-banner .iubenda-cs-accept-btn",
    ".iubenda-cs-reject-btn",
    # Common aria labels
    "[aria-label*='Accept all' i]",
    "[aria-label*='Accept cookies' i]",
    "[aria-label*='Accept All' i]",
    "[aria-label*='Reject all' i]",
    "[aria-label*='Reject cookies' i]",
    "[aria-label*='Decline' i]",
]


class ModalHandler:
    """Handles cookie consents, popups, and modals."""

    def __init__(self, client: BrowserClient, config: ModalsConfig):
        """Initialize modal handler.

        Args:
            client: Browser client (Playwright or MCP)
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

        # Try location/region modals (common on US retailers)
        if self.config.location.enabled:
            location_dismissed = await self._try_location_modals()
            dismissed_count += location_dismissed

        # Then try text-based matching for other modals
        for attempt in range(self.config.max_auto_clicks):
            # Look for buttons/links with close text
            close_button = await self._find_close_button()

            if close_button:
                base_selector, index = close_button
                try:
                    logger.debug(f"Attempting to close modal (attempt {attempt + 1})")
                    click_script = f"""
                    (function() {{
                        var el = document.querySelectorAll('{base_selector}')[{index}];
                        if (el) {{ el.click(); return true; }}
                        return false;
                    }})()
                    """
                    await self.client.evaluate(click_script)
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
                        // Try Didomi API
                        if (typeof Didomi !== 'undefined' && Didomi.setUserAgreeToAll) {
                            Didomi.setUserAgreeToAll();
                            return 'didomi_api';
                        }
                        if (window.didomiOnReady) {
                            window.didomiOnReady.push(function(Didomi) {
                                Didomi.setUserAgreeToAll();
                            });
                            return 'didomi_ready';
                        }
                        // Try Axeptio API
                        if (window._axcb) {
                            window._axcb.push(function(axeptio) {
                                axeptio.acceptAll();
                            });
                            return 'axeptio_api';
                        }
                        // Try Iubenda API
                        if (typeof _iub !== 'undefined' && _iub.cs && _iub.cs.api) {
                            _iub.cs.api.acceptAll();
                            return 'iubenda_api';
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

        # Try clicking any visible button with accept-like text (or reject as fallback)
        if dismissed == 0:
            try:
                result = await self.client.evaluate("""
                    (function() {
                        // Find all visible buttons and links with consent-related text
                        const acceptPatterns = /accept|agree|allow|consent|got it|continue/i;
                        const rejectPatterns = /reject|decline|deny|necessary only|only essential/i;

                        const candidates = Array.from(document.querySelectorAll(
                            'button, [role="button"], a[href="#"], a[class*="cookie"], a[class*="consent"]'
                        ));

                        let acceptButton = null;
                        let rejectButton = null;

                        for (const el of candidates) {
                            const text = (el.textContent || el.innerText || '').trim();
                            const rect = el.getBoundingClientRect();

                            // Skip if not visible
                            if (rect.width === 0 || rect.height === 0) continue;
                            if (rect.bottom < 0 || rect.top > window.innerHeight) continue;

                            // Track accept and reject buttons separately
                            if (acceptPatterns.test(text) && !rejectPatterns.test(text)) {
                                acceptButton = { el, text };
                            } else if (rejectPatterns.test(text)) {
                                rejectButton = { el, text };
                            }
                        }

                        // Prefer accept button, but use reject if no accept found
                        const target = acceptButton || rejectButton;
                        if (target) {
                            target.el.click();
                            return target.text.substring(0, 50);
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

    async def _try_location_modals(self) -> int:
        """Try to dismiss location/region/shipping modals.

        Looks for common location prompt patterns (country selectors,
        ZIP code inputs, "Ship to" dialogs) and dismisses them by
        clicking confirm/close or entering a default ZIP code.

        Returns:
            Number of location modals dismissed
        """
        dismissed = 0
        location_config = self.config.location

        # Step 1: Try known CSS selectors for location modals
        for selector in LOCATION_MODAL_SELECTORS:
            try:
                result = await self.client.query_selector(selector)
                if result:
                    logger.info(f"Found location modal element: {selector}")
                    # Found a location modal container — try to dismiss it
                    dismissed += await self._dismiss_location_dialog(location_config)
                    if dismissed > 0:
                        return dismissed
            except Exception as e:
                logger.debug(f"Location selector {selector} not found or failed: {e}")
                continue

        # Step 2: Text-based detection for location prompts
        try:
            result = await self.client.evaluate("""
                (function() {
                    const locationPatterns = /ship\\s*to|your\\s*location|choose\\s*(?:your\\s*)?country|select\\s*(?:your\\s*)?(?:country|region|location)|enter\\s*(?:your\\s*)?(?:zip|postal)\\s*code|where\\s*do\\s*you\\s*want\\s*(?:items|your\\s*order)\\s*(?:delivered|shipped)|deliver(?:y)?\\s*(?:to|location)|set\\s*(?:your\\s*)?store|find\\s*(?:a\\s*)?store|update\\s*(?:your\\s*)?location|confirm\\s*(?:your\\s*)?location/i;

                    // Check visible text in overlay/modal containers
                    const containers = document.querySelectorAll(
                        '[role="dialog"], [role="alertdialog"], [class*="modal"], ' +
                        '[class*="overlay"], [class*="popup"], [class*="drawer"]'
                    );

                    for (const container of containers) {
                        const rect = container.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;

                        const text = (container.textContent || '').substring(0, 500);
                        if (locationPatterns.test(text)) {
                            return true;
                        }
                    }
                    return false;
                })()
            """)
            if result and result not in ["false", "undefined", "null"]:
                logger.info("Detected location modal via text pattern matching")
                dismissed += await self._dismiss_location_dialog(location_config)
        except Exception as e:
            logger.debug(f"Location text pattern detection failed: {e}")

        return dismissed

    async def _dismiss_location_dialog(self, location_config: LocationConfig) -> int:
        """Dismiss a detected location/region dialog.

        Tries multiple strategies:
        1. Fill ZIP code input if configured and present
        2. Click confirm/continue/close buttons
        3. Click country/region selection if visible

        Returns:
            1 if dismissed, 0 otherwise
        """

        # Strategy 1: If a ZIP code input is visible and we have a default, fill it
        if location_config.default_zip_code:
            try:
                result = await self.client.evaluate(f"""
                    (function() {{
                        const zipPatterns = /zip|postal|postcode/i;
                        const inputs = document.querySelectorAll(
                            'input[type="text"], input[type="tel"], input[type="number"], ' +
                            'input:not([type])'
                        );
                        for (const input of inputs) {{
                            const rect = input.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0) continue;

                            const label = input.getAttribute('aria-label') || '';
                            const placeholder = input.getAttribute('placeholder') || '';
                            const name = input.getAttribute('name') || '';
                            const id = input.getAttribute('id') || '';
                            const combined = label + ' ' + placeholder + ' ' + name + ' ' + id;

                            if (zipPatterns.test(combined)) {{
                                input.focus();
                                input.value = '{location_config.default_zip_code}';
                                input.dispatchEvent(new Event('input', {{bubbles: true}}));
                                input.dispatchEvent(new Event('change', {{bubbles: true}}));
                                return true;
                            }}
                        }}
                        return false;
                    }})()
                """)
                if result and result not in ["false", "undefined", "null"]:
                    logger.info(f"Entered ZIP code: {location_config.default_zip_code}")
                    await asyncio.sleep(0.3)
            except Exception as e:
                logger.debug(f"ZIP code entry failed: {e}")

        # Strategy 2: Click confirm/continue/submit/close button in the dialog
        try:
            result = await self.client.evaluate("""
                (function() {
                    const confirmPatterns = /^(confirm|continue|save|submit|update|apply|done|ok|yes|shop now|start shopping|got it|close|×|✕)$/i;
                    const broadPatterns = /confirm|continue|save|submit|update|apply|done|shop\\s*now|start\\s*shopping/i;

                    // Search within modal/dialog containers first
                    const containers = document.querySelectorAll(
                        '[role="dialog"], [role="alertdialog"], [class*="modal"], ' +
                        '[class*="overlay"], [class*="popup"], [class*="drawer"]'
                    );

                    for (const container of containers) {
                        const rect = container.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;

                        const buttons = container.querySelectorAll(
                            'button, [role="button"], a[href="#"], input[type="submit"]'
                        );

                        // First pass: exact text match
                        for (const btn of buttons) {
                            const text = (btn.textContent || btn.innerText || '').trim();
                            const btnRect = btn.getBoundingClientRect();
                            if (btnRect.width === 0 || btnRect.height === 0) continue;
                            if (confirmPatterns.test(text)) {
                                btn.click();
                                return text.substring(0, 50);
                            }
                        }
                        // Second pass: broader match
                        for (const btn of buttons) {
                            const text = (btn.textContent || btn.innerText || '').trim();
                            const btnRect = btn.getBoundingClientRect();
                            if (btnRect.width === 0 || btnRect.height === 0) continue;
                            if (broadPatterns.test(text)) {
                                btn.click();
                                return text.substring(0, 50);
                            }
                        }

                        // Third pass: close/dismiss button (X icon, aria-label)
                        const closeBtn = container.querySelector(
                            '[aria-label*="close" i], [aria-label*="dismiss" i], ' +
                            'button[class*="close"], .close, .modal-close'
                        );
                        if (closeBtn) {
                            closeBtn.click();
                            return 'close-button';
                        }
                    }
                    return false;
                })()
            """)
            if result and result not in ["false", "undefined", "null"]:
                logger.info(f"Dismissed location modal by clicking: {result}")
                await asyncio.sleep(self.config.wait_after_close_ms / 1000)
                return 1
        except Exception as e:
            logger.debug(f"Location modal confirm click failed: {e}")

        return 0

    async def _find_close_button(self) -> tuple[str, int] | None:
        """Find a close button for modals.

        Returns:
            Tuple of (base_selector, index) for querySelectorAll indexing, or None.
            Uses querySelectorAll indexing to reliably access the nth match,
            avoiding nth-of-type which counts siblings of the same tag type
            rather than matches of the CSS selector.
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
                        logger.debug(
                            f"Found close button: {data['selector']}[{data['index']}]"
                            f" with text '{data['text']}'"
                        )
                        return (data["selector"], data["index"])
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
