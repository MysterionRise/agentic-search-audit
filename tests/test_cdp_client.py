"""Tests for CDPBrowserClient."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from playwright.async_api import Error as PlaywrightError

from agentic_search_audit.browser.cdp_client import CDPBrowserClient


@pytest.fixture()
def client() -> CDPBrowserClient:
    return CDPBrowserClient(cdp_endpoint="ws://localhost:9222")


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


class TestCDPConnect:
    """Tests for CDP connect/disconnect lifecycle."""

    async def test_connect_calls_connect_over_cdp(self) -> None:
        client = CDPBrowserClient(cdp_endpoint="ws://localhost:9222")
        mock_page = AsyncMock()
        mock_page.set_default_timeout = MagicMock()
        mock_page.set_default_navigation_timeout = MagicMock()
        mock_page.is_closed.return_value = False

        mock_context = AsyncMock()
        mock_context.pages = [mock_page]

        mock_browser = AsyncMock()
        mock_browser.contexts = [mock_context]

        mock_pw = AsyncMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

        # async_playwright() returns an object whose .start() is awaitable
        mock_cm = AsyncMock()
        mock_cm.start = AsyncMock(return_value=mock_pw)

        with patch(
            "agentic_search_audit.browser.cdp_client.async_playwright",
            return_value=mock_cm,
        ):
            # Mock stealth module with an async stealth_async function
            mock_stealth_mod = MagicMock()
            mock_stealth_mod.stealth_async = AsyncMock()
            with patch.dict("sys.modules", {"playwright_stealth": mock_stealth_mod}):
                await client.connect()

            mock_pw.chromium.connect_over_cdp.assert_awaited_once_with("ws://localhost:9222")
            assert client._page is mock_page

    async def test_disconnect_does_not_close_browser(self, client: CDPBrowserClient) -> None:
        """Disconnect should NOT close the external browser, only the page."""
        page = AsyncMock()
        browser = AsyncMock()
        pw = AsyncMock()

        client._page = page
        client._browser = browser
        client._context = MagicMock()
        client._playwright = pw

        await client.disconnect()

        page.close.assert_awaited_once()
        # browser.close should NOT be called — it's an external process
        browser.close.assert_not_awaited()
        pw.stop.assert_awaited_once()
        assert client._page is None
        assert client._browser is None

    async def test_disconnect_noop_when_not_connected(self, client: CDPBrowserClient) -> None:
        await client.disconnect()  # should not raise


# ---------------------------------------------------------------------------
# Health Checks
# ---------------------------------------------------------------------------


class TestCDPHealthChecks:
    """Tests for CDP health check methods."""

    def test_is_page_alive_true(self, client: CDPBrowserClient) -> None:
        page = MagicMock()
        page.is_closed.return_value = False
        client._page = page
        assert client.is_page_alive() is True

    def test_is_page_alive_false_when_closed(self, client: CDPBrowserClient) -> None:
        page = MagicMock()
        page.is_closed.return_value = True
        client._page = page
        assert client.is_page_alive() is False

    def test_is_page_alive_false_when_none(self, client: CDPBrowserClient) -> None:
        client._page = None
        assert client.is_page_alive() is False

    def test_is_browser_alive_true(self, client: CDPBrowserClient) -> None:
        browser = MagicMock()
        browser.contexts = []
        client._browser = browser
        assert client.is_browser_alive() is True

    def test_is_browser_alive_false_when_none(self, client: CDPBrowserClient) -> None:
        client._browser = None
        assert client.is_browser_alive() is False

    def test_is_browser_alive_false_when_dead(self, client: CDPBrowserClient) -> None:
        browser = MagicMock()
        type(browser).contexts = PropertyMock(
            side_effect=PlaywrightError("Browser has been closed")
        )
        client._browser = browser
        assert client.is_browser_alive() is False


# ---------------------------------------------------------------------------
# Page Recovery
# ---------------------------------------------------------------------------


class TestCDPRecoverPage:
    """Tests for CDP page recovery."""

    async def test_recover_page_creates_new_page(self, client: CDPBrowserClient) -> None:
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

    async def test_recover_page_no_context_raises(self, client: CDPBrowserClient) -> None:
        client._context = None
        with pytest.raises(RuntimeError, match="Browser context not available"):
            await client.recover_page()


# ---------------------------------------------------------------------------
# Reconnect
# ---------------------------------------------------------------------------


class TestCDPReconnect:
    """Tests for CDP reconnect."""

    async def test_reconnect_calls_disconnect_then_connect(self) -> None:
        client = CDPBrowserClient(cdp_endpoint="ws://localhost:9222")

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
# DOM Methods
# ---------------------------------------------------------------------------


class TestCDPDOMMethods:
    """Tests that DOM methods delegate to the underlying page."""

    @pytest.fixture()
    def connected_client(self) -> CDPBrowserClient:
        c = CDPBrowserClient(cdp_endpoint="ws://localhost:9222")
        c._page = AsyncMock()
        return c

    async def test_navigate(self, connected_client: CDPBrowserClient) -> None:
        connected_client._page.goto = AsyncMock()
        connected_client._page.url = "https://example.com/page"
        result = await connected_client.navigate("https://example.com/page")
        connected_client._page.goto.assert_awaited_once()
        assert result == "https://example.com/page"

    async def test_query_selector_found(self, connected_client: CDPBrowserClient) -> None:
        mock_el = AsyncMock()
        connected_client._page.query_selector = AsyncMock(return_value=mock_el)
        result = await connected_client.query_selector("div.test")
        assert result == {"exists": True}

    async def test_query_selector_not_found(self, connected_client: CDPBrowserClient) -> None:
        connected_client._page.query_selector = AsyncMock(return_value=None)
        result = await connected_client.query_selector("div.test")
        assert result is None

    async def test_click_uses_timeout(self, connected_client: CDPBrowserClient) -> None:
        connected_client.click_timeout_ms = 7000
        await connected_client.click("button.submit")
        connected_client._page.click.assert_awaited_once_with("button.submit", timeout=7000)

    async def test_evaluate(self, connected_client: CDPBrowserClient) -> None:
        connected_client._page.evaluate = AsyncMock(return_value="hello")
        result = await connected_client.evaluate("'hello'")
        assert result == "hello"

    async def test_get_html(self, connected_client: CDPBrowserClient) -> None:
        connected_client._page.content = AsyncMock(return_value="<html></html>")
        result = await connected_client.get_html()
        assert result == "<html></html>"

    async def test_screenshot(self, connected_client: CDPBrowserClient, tmp_path: Path) -> None:
        out = tmp_path / "shot.png"
        connected_client._page.screenshot = AsyncMock()
        result = await connected_client.screenshot(out)
        assert result == out

    async def test_not_connected_raises(self) -> None:
        client = CDPBrowserClient(cdp_endpoint="ws://localhost:9222")
        with pytest.raises(RuntimeError, match="not connected"):
            await client.navigate("https://example.com")
