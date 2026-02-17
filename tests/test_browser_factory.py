"""Tests for browser client factory."""

from types import ModuleType
from unittest.mock import patch

import pytest

from agentic_search_audit.browser.factory import create_browser_client
from agentic_search_audit.browser.playwright_client import PlaywrightBrowserClient
from agentic_search_audit.core.types import BrowserBackend, RunConfig


class TestFactoryPlaywright:
    """Factory returns PlaywrightBrowserClient for the default backend."""

    def test_default_backend_returns_playwright(self) -> None:
        config = RunConfig()
        client = create_browser_client(config)
        assert isinstance(client, PlaywrightBrowserClient)

    def test_explicit_playwright_returns_playwright(self) -> None:
        config = RunConfig(browser_backend=BrowserBackend.PLAYWRIGHT)
        client = create_browser_client(config)
        assert isinstance(client, PlaywrightBrowserClient)

    def test_playwright_passes_config_values(self) -> None:
        config = RunConfig(
            browser_backend=BrowserBackend.PLAYWRIGHT,
            headless=False,
            viewport_width=1920,
            viewport_height=1080,
            click_timeout_ms=10000,
        )
        client = create_browser_client(config)
        assert isinstance(client, PlaywrightBrowserClient)
        assert client.headless is False
        assert client.viewport_width == 1920
        assert client.viewport_height == 1080
        assert client.click_timeout_ms == 10000


class TestFactoryCDP:
    """Factory returns CDPBrowserClient for CDP backend."""

    def test_cdp_with_endpoint(self) -> None:
        config = RunConfig(
            browser_backend=BrowserBackend.CDP,
            cdp_endpoint="ws://localhost:9222",
        )
        client = create_browser_client(config)
        from agentic_search_audit.browser.cdp_client import CDPBrowserClient

        assert isinstance(client, CDPBrowserClient)
        assert client.cdp_endpoint == "ws://localhost:9222"

    def test_cdp_without_endpoint_or_key_raises(self) -> None:
        with pytest.raises(ValueError, match="cdp_endpoint.*browserbase_api_key"):
            RunConfig(browser_backend=BrowserBackend.CDP)

    def test_cdp_with_browserbase_calls_get_endpoint(self) -> None:
        config = RunConfig(
            browser_backend=BrowserBackend.CDP,
            browserbase_api_key="bb_live_test",
        )
        with patch(
            "agentic_search_audit.browser.browserbase.get_browserbase_endpoint",
            return_value="wss://connect.browserbase.com/session123",
        ) as mock_get:
            client = create_browser_client(config)
            mock_get.assert_called_once_with(
                api_key="bb_live_test",
                project_id=None,
            )
            from agentic_search_audit.browser.cdp_client import CDPBrowserClient

            assert isinstance(client, CDPBrowserClient)
            assert client.cdp_endpoint == "wss://connect.browserbase.com/session123"


class TestFactoryUndetected:
    """Factory returns UndetectedBrowserClient for undetected backend."""

    @pytest.fixture(autouse=True)
    def _mock_uc_module(self) -> None:
        """Provide a fake undetected_chromedriver module so the probe import passes."""
        mock_uc = ModuleType("undetected_chromedriver")
        with patch.dict("sys.modules", {"undetected_chromedriver": mock_uc}):
            yield  # type: ignore[misc]

    def test_undetected_backend(self) -> None:
        config = RunConfig(browser_backend=BrowserBackend.UNDETECTED)
        client = create_browser_client(config)
        from agentic_search_audit.browser.undetected_client import UndetectedBrowserClient

        assert isinstance(client, UndetectedBrowserClient)
        assert client.headless is True

    def test_undetected_passes_config_values(self) -> None:
        config = RunConfig(
            browser_backend=BrowserBackend.UNDETECTED,
            headless=False,
            viewport_width=1920,
            viewport_height=1080,
            click_timeout_ms=8000,
        )
        client = create_browser_client(config)
        from agentic_search_audit.browser.undetected_client import UndetectedBrowserClient

        assert isinstance(client, UndetectedBrowserClient)
        assert client.headless is False
        assert client.viewport_width == 1920
        assert client.click_timeout_ms == 8000


class TestFactoryUnknownBackend:
    """Factory raises on unknown backend."""

    def test_unknown_backend_raises(self) -> None:
        config = RunConfig()
        config.browser_backend = "fake"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="Unknown browser backend"):
            create_browser_client(config)
