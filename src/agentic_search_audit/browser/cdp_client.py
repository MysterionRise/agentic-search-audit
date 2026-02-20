"""CDP browser client — connects to an external Chrome via DevTools Protocol."""

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

logger = logging.getLogger(__name__)


class CDPBrowserClient:
    """Client connecting to an external browser over CDP.

    Use this when the target site blocks headless Playwright but works in a
    real Chrome instance (launched with ``--remote-debugging-port``) or a
    cloud browser service like Browserbase / Browserless.

    Unlike ``PlaywrightBrowserClient``, ``disconnect()`` does **not** close
    the external browser process — it only detaches the Playwright connection.
    """

    def __init__(
        self,
        cdp_endpoint: str,
        viewport_width: int = 1366,
        viewport_height: int = 900,
        click_timeout_ms: int = 5000,
        locale: str = "en-US",
    ):
        self.cdp_endpoint = cdp_endpoint
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.click_timeout_ms = click_timeout_ms
        self.locale = locale
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._owns_context: bool = False

    # -- lifecycle -----------------------------------------------------------

    async def __aenter__(self) -> "CDPBrowserClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Connect to an external browser via CDP."""
        logger.info(f"Connecting to CDP endpoint: {self.cdp_endpoint}")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_endpoint)

        # Reuse existing context if available, otherwise create one
        contexts = self._browser.contexts
        if contexts:
            self._context = contexts[0]
            self._owns_context = False
            logger.info("Reusing existing browser context")
        else:
            self._context = await self._browser.new_context(
                viewport={"width": self.viewport_width, "height": self.viewport_height},
                locale=self.locale,
            )
            self._owns_context = True

        # Reuse existing page or create one
        pages = self._context.pages
        if pages:
            self._page = pages[0]
        else:
            self._page = await self._context.new_page()

        # Apply stealth
        try:
            from playwright_stealth import stealth_async  # type: ignore[import-untyped]

            try:
                await stealth_async(self._page)
            except Exception as stealth_err:
                logger.warning(f"playwright-stealth failed ({stealth_err}), skipping stealth")
        except ImportError:
            logger.warning("playwright-stealth not installed, skipping stealth for CDP")

        self._page.set_default_timeout(60000)
        self._page.set_default_navigation_timeout(60000)
        logger.info("CDP connection established")

    async def disconnect(self) -> None:
        """Detach from the external browser (does NOT kill it)."""
        if self._page:
            try:
                await self._page.close()
            except Exception as e:
                logger.warning(f"Failed to close page: {e}")
            finally:
                self._page = None

        # Close context only if we created it; external contexts belong to the browser.
        if self._context and self._owns_context:
            try:
                await self._context.close()
            except Exception as e:
                logger.warning(f"Failed to close context: {e}")

        self._context = None
        self._owns_context = False
        self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.warning(f"Failed to stop playwright: {e}")
            finally:
                self._playwright = None

        logger.info("CDP connection closed")

    async def reconnect(self) -> None:
        """Disconnect and reconnect to the same CDP endpoint."""
        logger.warning("Reconnecting CDP — detaching and re-connecting")
        await self.disconnect()
        await self.connect()

    # -- health checks -------------------------------------------------------

    def is_page_alive(self) -> bool:
        """Check whether the current page is still usable."""
        return self._page is not None and not self._page.is_closed()

    def is_browser_alive(self) -> bool:
        """Check whether the CDP connection is still alive."""
        if not self._browser:
            return False
        try:
            _ = self._browser.contexts
            return True
        except Exception:
            return False

    async def recover_page(self) -> None:
        """Create a fresh page in the existing browser context."""
        if not self._context:
            raise RuntimeError("Browser context not available for recovery")

        if self._page:
            try:
                await self._page.close()
            except Exception as e:
                logger.debug(f"Old page already closed: {e}")
            finally:
                self._page = None

        logger.warning("Recovering page — creating new tab in CDP context")
        self._page = await self._context.new_page()
        self._page.set_default_timeout(60000)
        self._page.set_default_navigation_timeout(60000)
        logger.info("CDP page recovered")

    # -- navigation ----------------------------------------------------------

    async def navigate(self, url: str, wait_until: str = "networkidle") -> str:
        if not self._page:
            raise RuntimeError("Browser not connected")
        wait_condition: Literal["commit", "domcontentloaded", "load", "networkidle"] = (
            wait_until if wait_until in ("commit", "domcontentloaded", "load", "networkidle") else "networkidle"  # type: ignore[assignment]
        )
        await self._page.goto(url, wait_until=wait_condition)
        return self._page.url

    # -- DOM methods ---------------------------------------------------------

    async def query_selector(self, selector: str) -> dict[str, Any] | None:
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
        if not self._page:
            raise RuntimeError("Browser not connected")
        try:
            result = await self._page.evaluate(expression)
            if result is None:
                return None
            return str(result) if not isinstance(result, str) else result
        except (PlaywrightTimeoutError, PlaywrightError):
            raise
        except Exception as e:
            logger.debug(f"Evaluate failed: {e}")
            return None

    async def click(self, selector: str) -> None:
        if not self._page:
            raise RuntimeError("Browser not connected")
        await self._page.click(selector, timeout=self.click_timeout_ms)

    async def type_text(self, selector: str, text: str, delay: int = 50) -> None:
        if not self._page:
            raise RuntimeError("Browser not connected")
        await self._page.click(selector)
        await self._page.fill(selector, "")
        await self._page.type(selector, text, delay=delay)

    async def press_key(self, key: str) -> None:
        if not self._page:
            raise RuntimeError("Browser not connected")
        await self._page.keyboard.press(key)

    async def screenshot(self, output_path: Path, full_page: bool = True) -> Path:
        if not self._page:
            raise RuntimeError("Browser not connected")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await self._page.screenshot(path=str(output_path), full_page=full_page)
        return output_path

    async def get_html(self) -> str:
        if not self._page:
            raise RuntimeError("Browser not connected")
        return await self._page.content()

    async def wait_for_selector(
        self, selector: str, timeout: int = 5000, visible: bool = True
    ) -> bool:
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
        if not self._page:
            raise RuntimeError("Browser not connected")
        try:
            await self._page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception as e:
            logger.debug(f"Network idle timeout: {e}")

    async def get_element_text(self, selector: str) -> str | None:
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

    async def get_element_attribute(self, selector: str, attribute: str) -> str | None:
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
