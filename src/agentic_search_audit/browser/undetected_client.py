"""Undetected-chromedriver browser client (Selenium-based, async-wrapped)."""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from .stealth import (
    human_typing_delay,
    pre_action_delay,
    random_user_agent,
)

logger = logging.getLogger(__name__)


class UndetectedBrowserClient:
    """Browser client using undetected-chromedriver to bypass bot detection.

    All synchronous Selenium calls are wrapped with ``asyncio.to_thread()``
    so the client exposes the same async interface as the Playwright backends.
    """

    def __init__(
        self,
        headless: bool = True,
        viewport_width: int = 1366,
        viewport_height: int = 900,
        click_timeout_ms: int = 5000,
        locale: str = "en-US",
        proxy_url: str | None = None,
    ):
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.click_timeout_ms = click_timeout_ms
        self.locale = locale
        self.proxy_url = proxy_url
        self._driver: Any = None

    # -- lifecycle -----------------------------------------------------------

    async def __aenter__(self) -> "UndetectedBrowserClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Launch an undetected Chrome instance."""
        try:
            import undetected_chromedriver as uc  # type: ignore[import-untyped,import-not-found]
        except ImportError:
            raise ImportError(
                "undetected-chromedriver not installed. "
                "Install with: pip install 'agentic-search-audit[undetected]'"
            )

        locale = self.locale

        def _create_driver() -> Any:
            options = uc.ChromeOptions()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument(f"--window-size={self.viewport_width},{self.viewport_height}")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            options.add_argument("--disable-dev-shm-usage")
            # Set browser language / Accept-Language header
            options.add_argument(f"--lang={locale}")
            lang = locale.split("-")[0] if "-" in locale else locale
            accept_langs = f"{locale},{lang};q=0.9"
            if lang != "en":
                accept_langs += ",en;q=0.8"
            options.add_experimental_option("prefs", {"intl.accept_languages": accept_langs})
            if self.proxy_url:
                options.add_argument(f"--proxy-server={self.proxy_url}")
                logger.info("Using proxy: %s", self.proxy_url)
            ua = random_user_agent()
            options.add_argument(f"--user-agent={ua}")
            logger.debug("Selected user-agent: %s", ua)
            driver = uc.Chrome(options=options)
            driver.set_page_load_timeout(60)
            # Inject navigator.language overrides
            languages_js = json.dumps(
                [locale] + ([lang] if lang != locale else []) + (["en"] if lang != "en" else [])
            )
            driver.execute_script(f"""
                Object.defineProperty(navigator, 'language', {{
                    get: () => {json.dumps(locale)}
                }});
                Object.defineProperty(navigator, 'languages', {{
                    get: () => {languages_js}
                }});
            """)
            return driver

        logger.info("Launching undetected Chrome...")
        self._driver = await asyncio.to_thread(_create_driver)
        logger.info("Undetected Chrome launched")

    async def disconnect(self) -> None:
        """Quit the Chrome driver."""
        if self._driver:
            try:
                await asyncio.to_thread(self._driver.quit)
            except Exception as e:
                logger.warning(f"Failed to quit driver: {e}")
            finally:
                self._driver = None
        logger.info("Undetected Chrome closed")

    async def reconnect(self) -> None:
        """Quit and relaunch the driver."""
        logger.warning("Reconnecting undetected Chrome — full restart")
        await self.disconnect()
        await self.connect()

    # -- health checks -------------------------------------------------------

    def is_page_alive(self) -> bool:
        if not self._driver:
            return False
        try:
            _ = self._driver.current_url
            return True
        except Exception:
            return False

    def is_browser_alive(self) -> bool:
        if not self._driver:
            return False
        try:
            return bool(self._driver.service.is_connectable())
        except Exception:
            return False

    async def recover_page(self) -> None:
        """Open a new tab and switch to it."""
        if not self._driver:
            raise RuntimeError("Browser not connected")
        logger.warning("Recovering page — opening new tab")

        def _new_tab() -> None:
            self._driver.execute_script("window.open('about:blank', '_blank');")
            self._driver.switch_to.window(self._driver.window_handles[-1])

        await asyncio.to_thread(_new_tab)
        logger.info("Page recovered via new tab")

    # -- navigation ----------------------------------------------------------

    async def navigate(self, url: str, wait_until: str = "networkidle") -> str:
        if not self._driver:
            raise RuntimeError("Browser not connected")

        def _navigate() -> str:
            self._driver.get(url)
            # Wait for document ready state
            from selenium.webdriver.support.ui import (  # type: ignore[import-not-found]
                WebDriverWait,
            )

            WebDriverWait(self._driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            return str(self._driver.current_url)

        return await asyncio.to_thread(_navigate)

    # -- DOM methods ---------------------------------------------------------

    async def query_selector(self, selector: str) -> dict[str, Any] | None:
        if not self._driver:
            raise RuntimeError("Browser not connected")

        def _query() -> dict[str, Any] | None:
            from selenium.webdriver.common.by import (  # type: ignore[import-not-found]
                By,
            )

            elements = self._driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                return {"exists": True}
            return None

        return await asyncio.to_thread(_query)

    async def query_selector_all(self, selector: str) -> list[dict[str, Any]]:
        if not self._driver:
            raise RuntimeError("Browser not connected")

        def _query_all() -> list[dict[str, Any]]:
            from selenium.webdriver.common.by import (  # type: ignore[import-not-found]
                By,
            )

            elements = self._driver.find_elements(By.CSS_SELECTOR, selector)
            return [{"index": i} for i in range(len(elements))]

        return await asyncio.to_thread(_query_all)

    async def evaluate(self, expression: str) -> Any:
        if not self._driver:
            raise RuntimeError("Browser not connected")

        def _eval() -> Any:
            result = self._driver.execute_script(f"return {expression.strip()}")
            if result is None:
                return None
            return str(result) if not isinstance(result, str) else result

        try:
            return await asyncio.to_thread(_eval)
        except Exception as e:
            logger.debug(f"Evaluate failed: {e}")
            return None

    async def click(self, selector: str) -> None:
        if not self._driver:
            raise RuntimeError("Browser not connected")

        await asyncio.sleep(pre_action_delay())

        def _click() -> None:
            from selenium.webdriver.common.by import (  # type: ignore[import-not-found]
                By,
            )
            from selenium.webdriver.support import (  # type: ignore[import-untyped,import-not-found]
                expected_conditions as ec,
            )
            from selenium.webdriver.support.ui import (  # type: ignore[import-not-found]
                WebDriverWait,
            )

            timeout_s = self.click_timeout_ms / 1000
            element = WebDriverWait(self._driver, timeout_s).until(
                ec.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            element.click()

        await asyncio.to_thread(_click)

    async def type_text(self, selector: str, text: str, delay: int = 50) -> None:
        if not self._driver:
            raise RuntimeError("Browser not connected")

        await asyncio.sleep(pre_action_delay())

        def _type() -> None:
            from selenium.webdriver.common.by import (  # type: ignore[import-not-found]
                By,
            )

            element = self._driver.find_element(By.CSS_SELECTOR, selector)
            element.click()
            element.clear()
            for char in text:
                element.send_keys(char)
                time.sleep(human_typing_delay(delay) / 1000)

        await asyncio.to_thread(_type)

    async def press_key(self, key: str) -> None:
        if not self._driver:
            raise RuntimeError("Browser not connected")

        await asyncio.sleep(pre_action_delay())

        def _press() -> None:
            from selenium.webdriver.common.keys import (  # type: ignore[import-not-found]
                Keys,
            )

            key_map = {
                "Enter": Keys.ENTER,
                "Escape": Keys.ESCAPE,
                "Tab": Keys.TAB,
                "Backspace": Keys.BACKSPACE,
                "ArrowDown": Keys.ARROW_DOWN,
                "ArrowUp": Keys.ARROW_UP,
            }
            from selenium.webdriver.common.action_chains import (  # type: ignore[import-untyped,import-not-found]
                ActionChains,
            )

            actions = ActionChains(self._driver)
            actions.send_keys(key_map.get(key, key))
            actions.perform()

        await asyncio.to_thread(_press)

    async def screenshot(self, output_path: Path, full_page: bool = True) -> Path:
        if not self._driver:
            raise RuntimeError("Browser not connected")

        def _screenshot() -> Path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if full_page:
                # Resize window to capture full page
                total_height = self._driver.execute_script(
                    "return document.body.parentNode.scrollHeight"
                )
                self._driver.set_window_size(self.viewport_width, total_height)
                self._driver.save_screenshot(str(output_path))
                self._driver.set_window_size(self.viewport_width, self.viewport_height)
            else:
                self._driver.save_screenshot(str(output_path))
            return output_path

        return await asyncio.to_thread(_screenshot)

    async def get_html(self) -> str:
        if not self._driver:
            raise RuntimeError("Browser not connected")
        return await asyncio.to_thread(lambda: str(self._driver.page_source))

    async def wait_for_selector(
        self, selector: str, timeout: int = 5000, visible: bool = True
    ) -> bool:
        if not self._driver:
            raise RuntimeError("Browser not connected")

        def _wait() -> bool:
            from selenium.webdriver.common.by import (  # type: ignore[import-not-found]
                By,
            )
            from selenium.webdriver.support import (  # type: ignore[import-untyped,import-not-found]
                expected_conditions as ec,
            )
            from selenium.webdriver.support.ui import (  # type: ignore[import-not-found]
                WebDriverWait,
            )

            try:
                condition = (
                    ec.visibility_of_element_located((By.CSS_SELECTOR, selector))
                    if visible
                    else ec.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                WebDriverWait(self._driver, timeout / 1000).until(condition)
                return True
            except Exception:
                return False

        return await asyncio.to_thread(_wait)

    async def wait_for_network_idle(self, timeout: int = 2000) -> None:
        if not self._driver:
            raise RuntimeError("Browser not connected")

        def _wait_idle() -> None:
            deadline = time.time() + timeout / 1000
            while time.time() < deadline:
                pending = self._driver.execute_script("""
                    var entries = performance.getEntriesByType('resource');
                    var now = performance.now();
                    return entries.filter(e => !e.responseEnd || (now - e.responseEnd) < 500).length;
                    """)
                if pending == 0:
                    return
                time.sleep(0.25)

        try:
            await asyncio.to_thread(_wait_idle)
        except Exception as e:
            logger.debug(f"Network idle timeout: {e}")

    async def get_element_text(self, selector: str) -> str | None:
        if not self._driver:
            raise RuntimeError("Browser not connected")

        def _text() -> str | None:
            from selenium.webdriver.common.by import (  # type: ignore[import-not-found]
                By,
            )

            elements = self._driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                return elements[0].text or None
            return None

        return await asyncio.to_thread(_text)

    async def get_element_attribute(self, selector: str, attribute: str) -> str | None:
        if not self._driver:
            raise RuntimeError("Browser not connected")

        def _attr() -> str | None:
            from selenium.webdriver.common.by import (  # type: ignore[import-not-found]
                By,
            )

            elements = self._driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                val = elements[0].get_attribute(attribute)
                return str(val) if val is not None else None
            return None

        return await asyncio.to_thread(_attr)
