"""Tests for UndetectedBrowserClient."""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from agentic_search_audit.browser.undetected_client import UndetectedBrowserClient


def _ensure_selenium_mocks() -> None:
    """Inject mock selenium modules into sys.modules if not installed.

    Must be called before any test that triggers a lazy
    ``from selenium.webdriver.common.by import By`` inside
    ``UndetectedBrowserClient``.  The mock hierarchy needs to cover every
    sub-package that the production code imports.
    """
    # Check if real selenium is installed and usable
    try:
        from selenium.webdriver.common.by import By  # noqa: F401

        return  # Real selenium is available — nothing to do
    except (ImportError, AttributeError, ModuleNotFoundError):
        pass

    # Build a complete mock hierarchy so lazy imports inside to_thread work.
    mod_names = [
        "selenium",
        "selenium.common",
        "selenium.common.exceptions",
        "selenium.webdriver",
        "selenium.webdriver.common",
        "selenium.webdriver.common.by",
        "selenium.webdriver.common.keys",
        "selenium.webdriver.common.action_chains",
        "selenium.webdriver.support",
        "selenium.webdriver.support.ui",
        "selenium.webdriver.support.expected_conditions",
    ]
    for mod_name in mod_names:
        if mod_name not in sys.modules or not isinstance(sys.modules[mod_name], ModuleType):
            sys.modules[mod_name] = ModuleType(mod_name)

    # Wire up By.CSS_SELECTOR
    by_mod = sys.modules["selenium.webdriver.common.by"]
    if not hasattr(by_mod, "By"):
        mock_by = MagicMock()
        mock_by.CSS_SELECTOR = "css selector"
        by_mod.By = mock_by  # type: ignore[attr-defined]

    # Wire up WebDriverWait
    ui_mod = sys.modules["selenium.webdriver.support.ui"]
    if not hasattr(ui_mod, "WebDriverWait"):
        ui_mod.WebDriverWait = MagicMock()  # type: ignore[attr-defined]


@pytest.fixture()
def client() -> UndetectedBrowserClient:
    return UndetectedBrowserClient(headless=True)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


class TestUndetectedConnect:
    """Tests for undetected-chromedriver connect/disconnect."""

    async def test_connect_creates_driver(self) -> None:
        client = UndetectedBrowserClient(headless=True, viewport_width=1920, viewport_height=1080)

        mock_driver = MagicMock()
        mock_chrome_cls = MagicMock(return_value=mock_driver)
        mock_options_cls = MagicMock()

        mock_uc = MagicMock()
        mock_uc.Chrome = mock_chrome_cls
        mock_uc.ChromeOptions = mock_options_cls

        with patch.dict("sys.modules", {"undetected_chromedriver": mock_uc}):
            await client.connect()

        assert client._driver is mock_driver
        mock_driver.set_page_load_timeout.assert_called_once_with(60)

    async def test_connect_raises_if_not_installed(self) -> None:
        client = UndetectedBrowserClient()
        with (
            patch.dict("sys.modules", {"undetected_chromedriver": None}),
            pytest.raises(ImportError, match="undetected-chromedriver not installed"),
        ):
            await client.connect()

    async def test_disconnect_calls_quit(self, client: UndetectedBrowserClient) -> None:
        mock_driver = MagicMock()
        client._driver = mock_driver

        await client.disconnect()

        mock_driver.quit.assert_called_once()
        assert client._driver is None

    async def test_disconnect_noop_when_not_connected(
        self, client: UndetectedBrowserClient
    ) -> None:
        await client.disconnect()  # should not raise


# ---------------------------------------------------------------------------
# Health Checks
# ---------------------------------------------------------------------------


class TestUndetectedHealthChecks:
    """Tests for health check methods."""

    def test_is_page_alive_true(self, client: UndetectedBrowserClient) -> None:
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com"
        client._driver = mock_driver
        assert client.is_page_alive() is True

    def test_is_page_alive_false_when_driver_none(self, client: UndetectedBrowserClient) -> None:
        client._driver = None
        assert client.is_page_alive() is False

    def test_is_page_alive_false_on_exception(self, client: UndetectedBrowserClient) -> None:
        mock_driver = MagicMock()
        type(mock_driver).current_url = property(lambda self: (_ for _ in ()).throw(Exception()))
        client._driver = mock_driver
        assert client.is_page_alive() is False

    def test_is_browser_alive_true(self, client: UndetectedBrowserClient) -> None:
        mock_driver = MagicMock()
        mock_driver.service.is_connectable.return_value = True
        client._driver = mock_driver
        assert client.is_browser_alive() is True

    def test_is_browser_alive_false_when_none(self, client: UndetectedBrowserClient) -> None:
        client._driver = None
        assert client.is_browser_alive() is False

    def test_is_browser_alive_false_on_exception(self, client: UndetectedBrowserClient) -> None:
        mock_driver = MagicMock()
        mock_driver.service.is_connectable.side_effect = Exception("dead")
        client._driver = mock_driver
        assert client.is_browser_alive() is False


# ---------------------------------------------------------------------------
# Page Recovery
# ---------------------------------------------------------------------------


class TestUndetectedRecoverPage:
    """Tests for page recovery via new tab."""

    async def test_recover_page_opens_new_tab(self, client: UndetectedBrowserClient) -> None:
        mock_driver = MagicMock()
        mock_driver.window_handles = ["tab1", "tab2"]
        client._driver = mock_driver

        await client.recover_page()

        mock_driver.execute_script.assert_called_once_with("window.open('about:blank', '_blank');")
        mock_driver.switch_to.window.assert_called_once_with("tab2")

    async def test_recover_page_no_driver_raises(self, client: UndetectedBrowserClient) -> None:
        client._driver = None
        with pytest.raises(RuntimeError, match="not connected"):
            await client.recover_page()


# ---------------------------------------------------------------------------
# Reconnect
# ---------------------------------------------------------------------------


class TestUndetectedReconnect:
    """Tests for reconnect method."""

    async def test_reconnect_calls_disconnect_then_connect(self) -> None:
        client = UndetectedBrowserClient()

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


class TestUndetectedDOMMethods:
    """Tests that DOM methods wrap Selenium calls correctly."""

    @pytest.fixture(autouse=True)
    def _setup_selenium_mocks(self) -> None:
        _ensure_selenium_mocks()

    @pytest.fixture()
    def connected_client(self) -> UndetectedBrowserClient:
        c = UndetectedBrowserClient(headless=True, click_timeout_ms=5000)
        c._driver = MagicMock()
        return c

    async def test_navigate(self, connected_client: UndetectedBrowserClient) -> None:
        connected_client._driver.current_url = "https://example.com"
        connected_client._driver.execute_script = MagicMock(return_value="complete")
        result = await connected_client.navigate("https://example.com")
        connected_client._driver.get.assert_called_once_with("https://example.com")
        assert result == "https://example.com"

    async def test_query_selector_found(self, connected_client: UndetectedBrowserClient) -> None:
        mock_el = MagicMock()
        connected_client._driver.find_elements = MagicMock(return_value=[mock_el])
        result = await connected_client.query_selector("div.test")
        assert result == {"exists": True}

    async def test_query_selector_not_found(
        self, connected_client: UndetectedBrowserClient
    ) -> None:
        connected_client._driver.find_elements = MagicMock(return_value=[])
        result = await connected_client.query_selector("div.missing")
        assert result is None

    async def test_evaluate(self, connected_client: UndetectedBrowserClient) -> None:
        connected_client._driver.execute_script = MagicMock(return_value="hello")
        result = await connected_client.evaluate("'hello'")
        assert result == "hello"

    async def test_evaluate_returns_none(self, connected_client: UndetectedBrowserClient) -> None:
        connected_client._driver.execute_script = MagicMock(return_value=None)
        result = await connected_client.evaluate("void 0")
        assert result is None

    async def test_get_html(self, connected_client: UndetectedBrowserClient) -> None:
        connected_client._driver.page_source = "<html></html>"
        result = await connected_client.get_html()
        assert result == "<html></html>"

    async def test_screenshot(
        self, connected_client: UndetectedBrowserClient, tmp_path: Path
    ) -> None:
        out = tmp_path / "shot.png"
        connected_client._driver.execute_script = MagicMock(return_value=800)
        result = await connected_client.screenshot(out, full_page=False)
        assert result == out
        connected_client._driver.save_screenshot.assert_called_once_with(str(out))

    async def test_not_connected_raises(self) -> None:
        client = UndetectedBrowserClient()
        with pytest.raises(RuntimeError, match="not connected"):
            await client.navigate("https://example.com")

    async def test_get_element_text(self, connected_client: UndetectedBrowserClient) -> None:
        mock_el = MagicMock()
        mock_el.text = "Hello World"
        connected_client._driver.find_elements = MagicMock(return_value=[mock_el])
        result = await connected_client.get_element_text("h1")
        assert result == "Hello World"

    async def test_get_element_attribute(self, connected_client: UndetectedBrowserClient) -> None:
        mock_el = MagicMock()
        mock_el.get_attribute = MagicMock(return_value="https://example.com")
        connected_client._driver.find_elements = MagicMock(return_value=[mock_el])
        result = await connected_client.get_element_attribute("a", "href")
        assert result == "https://example.com"
