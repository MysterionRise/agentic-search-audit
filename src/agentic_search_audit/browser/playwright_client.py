"""Playwright-based browser client for browser automation."""

import asyncio
import logging
from pathlib import Path
from typing import Any, Literal

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from .stealth import (
    build_stealth_js,
    human_typing_delay,
    pre_action_delay,
    random_user_agent,
    timezone_for_locale,
)

logger = logging.getLogger(__name__)


class PlaywrightBrowserClient:
    """Client for browser automation using Playwright.

    This class provides a clean interface for browser automation tasks
    like navigation, DOM querying, and screenshots using Playwright.
    """

    def __init__(
        self,
        headless: bool = True,
        viewport_width: int = 1366,
        viewport_height: int = 900,
        click_timeout_ms: int = 5000,
        locale: str = "en-US",
    ):
        """Initialize Playwright browser client.

        Args:
            headless: Run browser in headless mode
            viewport_width: Browser viewport width
            viewport_height: Browser viewport height
            click_timeout_ms: Timeout for click operations in ms
            locale: BCP-47 locale code (e.g. 'fr-FR', 'de-DE')
        """
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.click_timeout_ms = click_timeout_ms
        self.locale = locale
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> "PlaywrightBrowserClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """Launch browser and create page."""
        logger.info("Launching Playwright browser...")

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-dev-shm-usage",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-ipc-flooding-protection",
                "--metrics-recording-only",
                "--mute-audio",
                "--password-store=basic",
                "--use-mock-keychain",
            ],
        )
        ua = random_user_agent()
        tz = timezone_for_locale(self.locale)
        logger.debug("Selected user-agent: %s, timezone: %s", ua, tz)
        self._context = await self._browser.new_context(
            viewport={"width": self.viewport_width, "height": self.viewport_height},
            user_agent=ua,
            locale=self.locale,
            timezone_id=tz,
        )

        # Add stealth scripts to hide automation detection
        try:
            from playwright_stealth import stealth_async  # type: ignore[import-untyped]

            self._page = await self._context.new_page()
            try:
                await stealth_async(self._page)
            except Exception as stealth_err:
                logger.warning(f"playwright-stealth failed ({stealth_err}), using built-in JS")
                await self._context.add_init_script(build_stealth_js(self.locale))
        except ImportError:
            logger.warning("playwright-stealth not installed, using built-in stealth JS")
            await self._context.add_init_script(build_stealth_js(self.locale))
            self._page = await self._context.new_page()

        # Set higher default timeout for slow sites (60 seconds)
        self._page.set_default_timeout(60000)
        self._page.set_default_navigation_timeout(60000)

        logger.info("Playwright browser launched")

    async def disconnect(self) -> None:
        """Close browser and cleanup.

        Each resource is closed independently so a failure in one
        does not prevent cleanup of the others.
        """
        if self._page:
            try:
                await self._page.close()
            except Exception as e:
                logger.warning(f"Failed to close page: {e}")
            finally:
                self._page = None

        if self._context:
            try:
                await self._context.close()
            except Exception as e:
                logger.warning(f"Failed to close context: {e}")
            finally:
                self._context = None

        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.warning(f"Failed to close browser: {e}")
            finally:
                self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.warning(f"Failed to stop playwright: {e}")
            finally:
                self._playwright = None

        logger.info("Playwright browser closed")

    async def navigate(self, url: str, wait_until: str = "networkidle") -> str:
        """Navigate to a URL.

        Args:
            url: URL to navigate to
            wait_until: Wait condition (load, domcontentloaded, networkidle)

        Returns:
            Final URL after navigation
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        logger.info(f"Navigating to {url}")
        # Cast to the expected Literal type for Playwright
        wait_condition: Literal["commit", "domcontentloaded", "load", "networkidle"] = (
            wait_until if wait_until in ("commit", "domcontentloaded", "load", "networkidle") else "networkidle"  # type: ignore[assignment]
        )
        await self._page.goto(url, wait_until=wait_condition)
        current_url = self._page.url
        logger.info(f"Navigated to {current_url}")
        return current_url

    async def query_selector(self, selector: str) -> dict[str, Any] | None:
        """Query DOM for a single element.

        Args:
            selector: CSS selector

        Returns:
            Element info or None if not found
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        try:
            element = await self._page.query_selector(selector)
            if element:
                return {"exists": True}
            return None
        except (PlaywrightTimeoutError, PlaywrightError):
            raise
        except Exception as e:
            logger.debug(f"Selector {selector} not found: {e}")
            return None

    async def query_selector_all(self, selector: str) -> list[dict[str, Any]]:
        """Query DOM for all matching elements.

        Args:
            selector: CSS selector

        Returns:
            List of element info
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        try:
            elements = await self._page.query_selector_all(selector)
            return [{"index": i} for i in range(len(elements))]
        except (PlaywrightTimeoutError, PlaywrightError):
            raise
        except Exception as e:
            logger.debug(f"Selector {selector} returned no results: {e}")
            return []

    async def evaluate(self, expression: str) -> Any:
        """Evaluate JavaScript in the page context.

        Args:
            expression: JavaScript expression to evaluate

        Returns:
            Result of evaluation
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        try:
            result = await self._page.evaluate(expression)
            # Convert to string for compatibility with existing code
            if result is None:
                return None
            return str(result) if not isinstance(result, str) else result
        except (PlaywrightTimeoutError, PlaywrightError):
            raise
        except Exception as e:
            logger.debug(f"Evaluate failed: {e}")
            return None

    async def click(self, selector: str) -> None:
        """Click an element with a small human-like delay beforehand.

        Args:
            selector: CSS selector for element to click
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        await asyncio.sleep(pre_action_delay())
        logger.debug(f"Clicking {selector}")
        await self._page.click(selector, timeout=self.click_timeout_ms)

    async def type_text(self, selector: str, text: str, delay: int = 50) -> None:
        """Type text into an input element with human-like variable delays.

        Each keystroke uses a slightly different delay to mimic real typing
        cadence, including occasional longer pauses.

        Args:
            selector: CSS selector for input element
            text: Text to type
            delay: Base delay between keystrokes in ms (actual varies)
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        await asyncio.sleep(pre_action_delay())
        logger.debug(f"Typing '{text}' into {selector}")
        await self._page.click(selector)
        await self._page.fill(selector, "")
        # Type character-by-character with variable human-like delays
        for char in text:
            await self._page.keyboard.type(char, delay=0)
            await asyncio.sleep(human_typing_delay(delay) / 1000)

    async def press_key(self, key: str) -> None:
        """Press a keyboard key with a small human-like delay beforehand.

        Args:
            key: Key to press (e.g., 'Enter', 'Escape')
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        await asyncio.sleep(pre_action_delay())
        logger.debug(f"Pressing key: {key}")
        await self._page.keyboard.press(key)

    async def screenshot(self, output_path: Path, full_page: bool = True) -> Path:
        """Take a screenshot of the page.

        Args:
            output_path: Path to save screenshot
            full_page: Capture full scrollable page

        Returns:
            Path to saved screenshot
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        logger.debug(f"Taking screenshot: {output_path}")

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        await self._page.screenshot(path=str(output_path), full_page=full_page)

        logger.info(f"Screenshot saved to {output_path}")
        return output_path

    async def get_html(self) -> str:
        """Get current page HTML.

        Returns:
            Full page HTML
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        return await self._page.content()

    async def wait_for_selector(
        self, selector: str, timeout: int = 5000, visible: bool = True
    ) -> bool:
        """Wait for a selector to appear.

        Args:
            selector: CSS selector to wait for
            timeout: Timeout in milliseconds
            visible: Wait for element to be visible

        Returns:
            True if found, False if timeout
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        try:
            state: Literal["attached", "detached", "hidden", "visible"] = (
                "visible" if visible else "attached"
            )
            await self._page.wait_for_selector(selector, timeout=timeout, state=state)
            return True
        except Exception as e:
            logger.debug(f"Timeout waiting for {selector}: {e}")
            return False

    async def wait_for_network_idle(self, timeout: int = 2000) -> None:
        """Wait for network to be idle.

        Args:
            timeout: Timeout in milliseconds
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        try:
            await self._page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception as e:
            logger.debug(f"Network idle timeout: {e}")

    async def get_element_text(self, selector: str) -> str | None:
        """Get text content of an element.

        Args:
            selector: CSS selector

        Returns:
            Text content or None
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        try:
            element = await self._page.query_selector(selector)
            if element:
                return await element.text_content()
            return None
        except (PlaywrightTimeoutError, PlaywrightError):
            raise
        except Exception as e:
            logger.debug(f"Failed to get text for {selector}: {e}")
            return None

    def is_page_alive(self) -> bool:
        """Check whether the current page is still usable."""
        return self._page is not None and not self._page.is_closed()

    async def recover_page(self) -> None:
        """Create a fresh page in the existing browser context after a crash.

        Closes the old page first (if it still exists) to prevent memory leaks.
        """
        if not self._context:
            raise RuntimeError("Browser context not available for recovery")

        # Close old page to prevent memory leak
        if self._page:
            try:
                await self._page.close()
            except Exception as e:
                logger.debug(f"Old page already closed or failed to close: {e}")
            finally:
                self._page = None

        logger.warning("Recovering page -- creating new tab in existing context")
        self._page = await self._context.new_page()
        self._page.set_default_timeout(60000)
        self._page.set_default_navigation_timeout(60000)
        logger.info("Page recovered successfully")

    def is_browser_alive(self) -> bool:
        """Check whether the browser process is still running.

        Probes the browser's contexts property; if the process has died,
        accessing it will raise.
        """
        if not self._browser:
            return False
        try:
            _ = self._browser.contexts
            return True
        except Exception:
            return False

    async def reconnect(self) -> None:
        """Full browser restart: disconnect then connect."""
        logger.warning("Reconnecting browser -- full restart")
        await self.disconnect()
        await self.connect()

    async def wait_for_page_stable(self, timeout: int = 5000) -> None:
        """Wait for the page to be visually stable.

        Combines network idle waiting with a requestAnimationFrame callback
        to ensure the page has painted.
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        try:
            await self._page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            pass

        try:
            await self._page.evaluate(
                "new Promise(resolve => requestAnimationFrame(() => resolve()))"
            )
        except Exception:
            pass

    async def get_element_attribute(self, selector: str, attribute: str) -> str | None:
        """Get attribute value of an element.

        Args:
            selector: CSS selector
            attribute: Attribute name

        Returns:
            Attribute value or None
        """
        if not self._page:
            raise RuntimeError("Browser not connected")

        try:
            element = await self._page.query_selector(selector)
            if element:
                return await element.get_attribute(attribute)
            return None
        except (PlaywrightTimeoutError, PlaywrightError):
            raise
        except Exception as e:
            logger.debug(f"Failed to get attribute {attribute} for {selector}: {e}")
            return None
