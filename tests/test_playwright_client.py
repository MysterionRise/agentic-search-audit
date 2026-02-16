"""Tests for PlaywrightBrowserClient and browser error classification."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from agentic_search_audit.browser.errors import BrowserErrorKind, classify_error, is_retryable
from agentic_search_audit.browser.playwright_client import PlaywrightBrowserClient

# ---------------------------------------------------------------------------
# Error Classification
# ---------------------------------------------------------------------------


class TestBrowserErrorClassification:
    """Tests for classify_error and is_retryable."""

    def test_classify_timeout_error(self) -> None:
        exc = PlaywrightTimeoutError("Timeout 30000ms exceeded")
        assert classify_error(exc) == BrowserErrorKind.TIMEOUT

    def test_classify_page_closed(self) -> None:
        exc = PlaywrightError("Page has been closed")
        assert classify_error(exc) == BrowserErrorKind.PAGE_CLOSED

    def test_classify_page_closed_variant(self) -> None:
        exc = PlaywrightError("page closed")
        assert classify_error(exc) == BrowserErrorKind.PAGE_CLOSED

    def test_classify_browser_dead(self) -> None:
        exc = PlaywrightError("Browser has been closed")
        assert classify_error(exc) == BrowserErrorKind.BROWSER_DEAD

    def test_classify_context_closed_as_browser_dead(self) -> None:
        exc = PlaywrightError("Context has been closed")
        assert classify_error(exc) == BrowserErrorKind.BROWSER_DEAD

    def test_classify_target_closed(self) -> None:
        exc = PlaywrightError("Target page, context or browser has been closed")
        assert classify_error(exc) == BrowserErrorKind.BROWSER_DEAD

    def test_classify_navigation_error_as_transient(self) -> None:
        exc = PlaywrightError("net::ERR_CONNECTION_RESET")
        assert classify_error(exc) == BrowserErrorKind.TRANSIENT

    def test_classify_navigation_keyword_as_transient(self) -> None:
        exc = PlaywrightError("navigation failed because page was closed")
        # "navigation" keyword matches before "page closed" in classify_error
        assert classify_error(exc) == BrowserErrorKind.TRANSIENT

    def test_classify_unknown_playwright_error_as_permanent(self) -> None:
        exc = PlaywrightError("Element is not an input")
        assert classify_error(exc) == BrowserErrorKind.PERMANENT

    def test_classify_runtime_not_connected(self) -> None:
        exc = RuntimeError("Browser not connected")
        assert classify_error(exc) == BrowserErrorKind.NOT_CONNECTED

    def test_classify_generic_exception_as_permanent(self) -> None:
        exc = ValueError("unexpected value")
        assert classify_error(exc) == BrowserErrorKind.PERMANENT

    def test_is_retryable_timeout(self) -> None:
        assert is_retryable(BrowserErrorKind.TIMEOUT) is True

    def test_is_retryable_page_closed(self) -> None:
        assert is_retryable(BrowserErrorKind.PAGE_CLOSED) is True

    def test_is_retryable_browser_dead(self) -> None:
        assert is_retryable(BrowserErrorKind.BROWSER_DEAD) is True

    def test_is_retryable_transient(self) -> None:
        assert is_retryable(BrowserErrorKind.TRANSIENT) is True

    def test_is_retryable_permanent(self) -> None:
        assert is_retryable(BrowserErrorKind.PERMANENT) is False

    def test_is_retryable_not_connected(self) -> None:
        assert is_retryable(BrowserErrorKind.NOT_CONNECTED) is False


# ---------------------------------------------------------------------------
# Page Recovery
# ---------------------------------------------------------------------------


class TestPlaywrightClientPageRecovery:
    """Tests for recover_page behavior."""

    @pytest.fixture()
    def client(self) -> PlaywrightBrowserClient:
        c = PlaywrightBrowserClient(headless=True)
        return c

    async def test_recover_page_closes_old_page(self, client: PlaywrightBrowserClient) -> None:
        old_page = AsyncMock()
        new_page = AsyncMock()
        new_page.set_default_timeout = MagicMock()
        new_page.set_default_navigation_timeout = MagicMock()

        context = AsyncMock()
        context.new_page = AsyncMock(return_value=new_page)

        client._page = old_page
        client._context = context

        await client.recover_page()

        old_page.close.assert_awaited_once()
        context.new_page.assert_awaited_once()
        assert client._page is new_page

    async def test_recover_page_handles_already_closed(
        self, client: PlaywrightBrowserClient
    ) -> None:
        old_page = AsyncMock()
        old_page.close = AsyncMock(side_effect=PlaywrightError("Page has been closed"))
        new_page = AsyncMock()
        new_page.set_default_timeout = MagicMock()
        new_page.set_default_navigation_timeout = MagicMock()

        context = AsyncMock()
        context.new_page = AsyncMock(return_value=new_page)

        client._page = old_page
        client._context = context

        # Should not raise even though old_page.close() fails
        await client.recover_page()

        assert client._page is new_page

    async def test_recover_page_no_context_raises(self, client: PlaywrightBrowserClient) -> None:
        client._context = None
        with pytest.raises(RuntimeError, match="Browser context not available"):
            await client.recover_page()


# ---------------------------------------------------------------------------
# Disconnect Safety
# ---------------------------------------------------------------------------


class TestPlaywrightClientDisconnect:
    """Tests that disconnect cleans up all resources independently."""

    @pytest.fixture()
    def client(self) -> PlaywrightBrowserClient:
        c = PlaywrightBrowserClient(headless=True)
        return c

    async def test_disconnect_closes_all_resources(self, client: PlaywrightBrowserClient) -> None:
        page = AsyncMock()
        context = AsyncMock()
        browser = AsyncMock()
        pw = AsyncMock()

        client._page = page
        client._context = context
        client._browser = browser
        client._playwright = pw

        await client.disconnect()

        page.close.assert_awaited_once()
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()
        pw.stop.assert_awaited_once()

        assert client._page is None
        assert client._context is None
        assert client._browser is None
        assert client._playwright is None

    async def test_disconnect_continues_on_page_failure(
        self, client: PlaywrightBrowserClient
    ) -> None:
        page = AsyncMock()
        page.close = AsyncMock(side_effect=RuntimeError("page already dead"))
        context = AsyncMock()
        browser = AsyncMock()
        pw = AsyncMock()

        client._page = page
        client._context = context
        client._browser = browser
        client._playwright = pw

        await client.disconnect()

        # All resources should still be cleaned up
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()
        pw.stop.assert_awaited_once()
        assert client._page is None

    async def test_disconnect_continues_on_context_failure(
        self, client: PlaywrightBrowserClient
    ) -> None:
        context = AsyncMock()
        context.close = AsyncMock(side_effect=RuntimeError("context dead"))
        browser = AsyncMock()
        pw = AsyncMock()

        client._page = None
        client._context = context
        client._browser = browser
        client._playwright = pw

        await client.disconnect()

        browser.close.assert_awaited_once()
        pw.stop.assert_awaited_once()
        assert client._context is None

    async def test_disconnect_noop_when_nothing_set(self, client: PlaywrightBrowserClient) -> None:
        # Should not raise when all refs are None
        await client.disconnect()


# ---------------------------------------------------------------------------
# Browser Health
# ---------------------------------------------------------------------------


class TestPlaywrightClientBrowserHealth:
    """Tests for is_browser_alive and is_page_alive."""

    @pytest.fixture()
    def client(self) -> PlaywrightBrowserClient:
        return PlaywrightBrowserClient(headless=True)

    def test_is_browser_alive_true(self, client: PlaywrightBrowserClient) -> None:
        browser = MagicMock()
        browser.contexts = []
        client._browser = browser
        assert client.is_browser_alive() is True

    def test_is_browser_alive_false_when_no_browser(self, client: PlaywrightBrowserClient) -> None:
        client._browser = None
        assert client.is_browser_alive() is False

    def test_is_browser_alive_false_when_dead(self, client: PlaywrightBrowserClient) -> None:
        browser = MagicMock()
        type(browser).contexts = PropertyMock(
            side_effect=PlaywrightError("Browser has been closed")
        )
        client._browser = browser
        assert client.is_browser_alive() is False

    def test_is_page_alive_true(self, client: PlaywrightBrowserClient) -> None:
        page = MagicMock()
        page.is_closed.return_value = False
        client._page = page
        assert client.is_page_alive() is True

    def test_is_page_alive_false_when_closed(self, client: PlaywrightBrowserClient) -> None:
        page = MagicMock()
        page.is_closed.return_value = True
        client._page = page
        assert client.is_page_alive() is False

    def test_is_page_alive_false_when_none(self, client: PlaywrightBrowserClient) -> None:
        client._page = None
        assert client.is_page_alive() is False


# ---------------------------------------------------------------------------
# Click Timeout
# ---------------------------------------------------------------------------


class TestPlaywrightClientClickTimeout:
    """Tests for configurable click timeout."""

    def test_default_click_timeout(self) -> None:
        client = PlaywrightBrowserClient()
        assert client.click_timeout_ms == 5000

    def test_custom_click_timeout(self) -> None:
        client = PlaywrightBrowserClient(click_timeout_ms=10000)
        assert client.click_timeout_ms == 10000

    async def test_click_uses_configured_timeout(self) -> None:
        client = PlaywrightBrowserClient(click_timeout_ms=7000)
        page = AsyncMock()
        client._page = page

        await client.click("button.submit")

        page.click.assert_awaited_once_with("button.submit", timeout=7000)


# ---------------------------------------------------------------------------
# Error Propagation
# ---------------------------------------------------------------------------


class TestPlaywrightClientErrorPropagation:
    """Tests that Playwright errors are re-raised instead of swallowed."""

    @pytest.fixture()
    def client(self) -> PlaywrightBrowserClient:
        c = PlaywrightBrowserClient(headless=True)
        c._page = AsyncMock()
        return c

    async def test_query_selector_reraises_playwright_error(
        self, client: PlaywrightBrowserClient
    ) -> None:
        client._page.query_selector = AsyncMock(side_effect=PlaywrightError("Page has been closed"))
        with pytest.raises(PlaywrightError):
            await client.query_selector("div")

    async def test_query_selector_reraises_timeout(self, client: PlaywrightBrowserClient) -> None:
        client._page.query_selector = AsyncMock(
            side_effect=PlaywrightTimeoutError("Timeout 5000ms exceeded")
        )
        with pytest.raises(PlaywrightTimeoutError):
            await client.query_selector("div")

    async def test_evaluate_reraises_playwright_error(
        self, client: PlaywrightBrowserClient
    ) -> None:
        client._page.evaluate = AsyncMock(side_effect=PlaywrightError("Page has been closed"))
        with pytest.raises(PlaywrightError):
            await client.evaluate("1+1")

    async def test_query_selector_all_reraises_playwright_error(
        self, client: PlaywrightBrowserClient
    ) -> None:
        client._page.query_selector_all = AsyncMock(
            side_effect=PlaywrightError("Page has been closed")
        )
        with pytest.raises(PlaywrightError):
            await client.query_selector_all("div")

    async def test_get_element_text_reraises_playwright_error(
        self, client: PlaywrightBrowserClient
    ) -> None:
        client._page.query_selector = AsyncMock(side_effect=PlaywrightError("Page has been closed"))
        with pytest.raises(PlaywrightError):
            await client.get_element_text("div")

    async def test_get_element_attribute_reraises_playwright_error(
        self, client: PlaywrightBrowserClient
    ) -> None:
        client._page.query_selector = AsyncMock(side_effect=PlaywrightError("Page has been closed"))
        with pytest.raises(PlaywrightError):
            await client.get_element_attribute("div", "href")

    async def test_query_selector_swallows_non_playwright_exception(
        self, client: PlaywrightBrowserClient
    ) -> None:
        client._page.query_selector = AsyncMock(side_effect=ValueError("weird"))
        result = await client.query_selector("div")
        assert result is None

    async def test_evaluate_swallows_non_playwright_exception(
        self, client: PlaywrightBrowserClient
    ) -> None:
        client._page.evaluate = AsyncMock(side_effect=ValueError("weird"))
        result = await client.evaluate("1+1")
        assert result is None


# ---------------------------------------------------------------------------
# Reconnect
# ---------------------------------------------------------------------------


class TestPlaywrightClientReconnect:
    """Tests for reconnect method."""

    async def test_reconnect_calls_disconnect_then_connect(self) -> None:
        client = PlaywrightBrowserClient(headless=True)

        call_order: list[str] = []

        async def mock_disconnect() -> None:
            call_order.append("disconnect")

        async def mock_connect() -> None:
            call_order.append("connect")

        client.disconnect = mock_disconnect  # type: ignore[assignment]
        client.connect = mock_connect  # type: ignore[assignment]

        await client.reconnect()

        assert call_order == ["disconnect", "connect"]


# ---------------------------------------------------------------------------
# Selenium Error Classification
# ---------------------------------------------------------------------------


class TestSeleniumErrorClassification:
    """Tests for classify_error with Selenium exception types."""

    @pytest.fixture(autouse=True)
    def _setup_selenium_mocks(self) -> None:
        """Ensure mock selenium modules exist in sys.modules."""
        import importlib
        import sys
        from types import ModuleType

        # Check if we need to inject mocks
        try:
            from selenium.common.exceptions import TimeoutException  # noqa: F401

            return  # Real selenium installed — no mocking needed
        except (ImportError, AttributeError):
            pass

        # Create mock exception classes (must be done once and reused)
        if not hasattr(self.__class__, "_selenium_exc_classes"):

            class TimeoutException(Exception):  # noqa: N818
                pass

            class InvalidSessionIdException(Exception):  # noqa: N818
                pass

            class SessionNotCreatedException(Exception):  # noqa: N818
                pass

            class NoSuchWindowException(Exception):  # noqa: N818
                pass

            class WebDriverException(Exception):  # noqa: N818
                pass

            self.__class__._selenium_exc_classes = {  # type: ignore[attr-defined]
                "TimeoutException": TimeoutException,
                "InvalidSessionIdException": InvalidSessionIdException,
                "SessionNotCreatedException": SessionNotCreatedException,
                "NoSuchWindowException": NoSuchWindowException,
                "WebDriverException": WebDriverException,
            }

        classes = self.__class__._selenium_exc_classes  # type: ignore[attr-defined]

        mock_exc = ModuleType("selenium.common.exceptions")
        for name, cls in classes.items():
            setattr(mock_exc, name, cls)

        for mod_name in [
            "selenium",
            "selenium.common",
            "selenium.common.exceptions",
        ]:
            if mod_name not in sys.modules or not isinstance(sys.modules[mod_name], ModuleType):
                sys.modules[mod_name] = ModuleType(mod_name)

        sys.modules["selenium.common.exceptions"] = mock_exc

        # Reload errors module to pick up our mock
        import agentic_search_audit.browser.errors

        importlib.reload(agentic_search_audit.browser.errors)

    def _make_selenium_exc(self, cls_name: str, msg: str = "") -> BaseException:
        """Create a mock Selenium exception of the given class name."""
        classes = self.__class__._selenium_exc_classes  # type: ignore[attr-defined]
        return classes[cls_name](msg)

    def test_selenium_timeout(self) -> None:
        exc = self._make_selenium_exc("TimeoutException", "timed out")
        assert classify_error(exc) == BrowserErrorKind.TIMEOUT

    def test_selenium_invalid_session(self) -> None:
        exc = self._make_selenium_exc("InvalidSessionIdException", "invalid session")
        assert classify_error(exc) == BrowserErrorKind.BROWSER_DEAD

    def test_selenium_session_not_created(self) -> None:
        exc = self._make_selenium_exc("SessionNotCreatedException", "cannot create")
        assert classify_error(exc) == BrowserErrorKind.BROWSER_DEAD

    def test_selenium_no_such_window(self) -> None:
        exc = self._make_selenium_exc("NoSuchWindowException", "no such window")
        assert classify_error(exc) == BrowserErrorKind.PAGE_CLOSED

    def test_selenium_webdriver_chrome_not_reachable(self) -> None:
        exc = self._make_selenium_exc("WebDriverException", "chrome not reachable")
        assert classify_error(exc) == BrowserErrorKind.BROWSER_DEAD

    def test_selenium_webdriver_net_error_transient(self) -> None:
        exc = self._make_selenium_exc("WebDriverException", "net::ERR_CONNECTION_RESET")
        assert classify_error(exc) == BrowserErrorKind.TRANSIENT

    def test_selenium_webdriver_unknown_permanent(self) -> None:
        exc = self._make_selenium_exc("WebDriverException", "element not interactable")
        assert classify_error(exc) == BrowserErrorKind.PERMANENT
