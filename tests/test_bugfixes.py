"""Regression tests for QA-discovered bugs."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from agentic_search_audit.core.types import BrowserBackend, RunConfig

# ---------------------------------------------------------------------------
# Bug #1 (Critical): JS ASI in UndetectedBrowserClient.evaluate()
# ---------------------------------------------------------------------------


class TestUndetectedEvaluateASI:
    """Ensure multiline and whitespace-padded expressions evaluate correctly."""

    @pytest.fixture()
    def connected_client(self):
        from agentic_search_audit.browser.undetected_client import UndetectedBrowserClient

        c = UndetectedBrowserClient(headless=True)
        c._driver = MagicMock()
        return c

    async def test_evaluate_strips_leading_newline(self, connected_client) -> None:
        """A leading newline would cause JS ASI to produce `return;`."""
        connected_client._driver.execute_script = MagicMock(return_value="42")
        result = await connected_client.evaluate("\n42")
        connected_client._driver.execute_script.assert_called_once_with("return 42")
        assert result == "42"

    async def test_evaluate_strips_trailing_whitespace(self, connected_client) -> None:
        connected_client._driver.execute_script = MagicMock(return_value="ok")
        result = await connected_client.evaluate("  'ok'  \n")
        connected_client._driver.execute_script.assert_called_once_with("return 'ok'")
        assert result == "ok"

    async def test_evaluate_multiline_expression(self, connected_client) -> None:
        """Multi-line expressions must be collapsed via strip()."""
        expr = "\ndocument.querySelector('input')\n"
        connected_client._driver.execute_script = MagicMock(return_value=None)
        await connected_client.evaluate(expr)
        connected_client._driver.execute_script.assert_called_once_with(
            "return document.querySelector('input')"
        )


# ---------------------------------------------------------------------------
# Bug #2 (High): Playwright stealth non-ImportError handling
# ---------------------------------------------------------------------------


class TestPlaywrightStealthFallback:
    """stealth_async() non-ImportError should fall back to built-in JS."""

    async def test_stealth_type_error_falls_back_to_builtin(self) -> None:
        from agentic_search_audit.browser.playwright_client import PlaywrightBrowserClient

        client = PlaywrightBrowserClient(headless=True)

        mock_page = AsyncMock()
        mock_page.set_default_timeout = MagicMock()
        mock_page.set_default_navigation_timeout = MagicMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.add_init_script = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_cm = AsyncMock()
        mock_cm.start = AsyncMock(return_value=mock_pw)

        # stealth_async raises TypeError (not ImportError)
        mock_stealth_mod = MagicMock()
        mock_stealth_mod.stealth_async = AsyncMock(side_effect=TypeError("bad arg"))

        with (
            patch(
                "agentic_search_audit.browser.playwright_client.async_playwright",
                return_value=mock_cm,
            ),
            patch.dict("sys.modules", {"playwright_stealth": mock_stealth_mod}),
        ):
            await client.connect()

        # Should have fallen back to add_init_script
        mock_context.add_init_script.assert_awaited_once()
        # Page should still be set (no half-init leak)
        assert client._page is mock_page


class TestCDPStealthFallback:
    """CDP stealth_async() non-ImportError should not crash connect()."""

    async def test_cdp_stealth_runtime_error_handled(self) -> None:
        from agentic_search_audit.browser.cdp_client import CDPBrowserClient

        client = CDPBrowserClient(cdp_endpoint="ws://localhost:9222")

        mock_page = AsyncMock()
        mock_page.set_default_timeout = MagicMock()
        mock_page.set_default_navigation_timeout = MagicMock()

        mock_context = AsyncMock()
        mock_context.pages = [mock_page]

        mock_browser = AsyncMock()
        mock_browser.contexts = [mock_context]

        mock_pw = AsyncMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

        mock_cm = AsyncMock()
        mock_cm.start = AsyncMock(return_value=mock_pw)

        mock_stealth_mod = MagicMock()
        mock_stealth_mod.stealth_async = AsyncMock(side_effect=RuntimeError("stealth broke"))

        with (
            patch(
                "agentic_search_audit.browser.cdp_client.async_playwright",
                return_value=mock_cm,
            ),
            patch.dict("sys.modules", {"playwright_stealth": mock_stealth_mod}),
        ):
            await client.connect()

        # Connection should succeed despite stealth failure
        assert client._page is mock_page


# ---------------------------------------------------------------------------
# Bug #3 (High): RunConfig extra="forbid"
# ---------------------------------------------------------------------------


class TestRunConfigExtraForbid:
    """RunConfig must reject unknown fields."""

    def test_typo_field_rejected(self) -> None:
        with pytest.raises(ValidationError, match="extra_field"):
            RunConfig(extra_field="oops")  # type: ignore[call-arg]

    def test_misspelled_browser_backend_rejected(self) -> None:
        with pytest.raises(ValidationError, match="browser_bakend"):
            RunConfig(browser_bakend="cdp")  # type: ignore[call-arg]

    def test_valid_fields_still_accepted(self) -> None:
        config = RunConfig(headless=False, top_k=5)
        assert config.headless is False
        assert config.top_k == 5


# ---------------------------------------------------------------------------
# Bug #4 (Medium): CDP disconnect context leak
# ---------------------------------------------------------------------------


class TestCDPContextOwnership:
    """CDP disconnect should close contexts it created, but not reused ones."""

    async def test_disconnect_closes_owned_context(self) -> None:
        from agentic_search_audit.browser.cdp_client import CDPBrowserClient

        client = CDPBrowserClient(cdp_endpoint="ws://localhost:9222")
        context = AsyncMock()
        pw = AsyncMock()

        client._page = AsyncMock()
        client._context = context
        client._owns_context = True
        client._browser = AsyncMock()
        client._playwright = pw

        await client.disconnect()

        context.close.assert_awaited_once()
        assert client._context is None
        assert client._owns_context is False

    async def test_disconnect_does_not_close_reused_context(self) -> None:
        from agentic_search_audit.browser.cdp_client import CDPBrowserClient

        client = CDPBrowserClient(cdp_endpoint="ws://localhost:9222")
        context = AsyncMock()
        pw = AsyncMock()

        client._page = AsyncMock()
        client._context = context
        client._owns_context = False
        client._browser = AsyncMock()
        client._playwright = pw

        await client.disconnect()

        context.close.assert_not_awaited()
        assert client._context is None

    async def test_connect_reuse_sets_owns_false(self) -> None:
        from agentic_search_audit.browser.cdp_client import CDPBrowserClient

        client = CDPBrowserClient(cdp_endpoint="ws://localhost:9222")

        mock_page = AsyncMock()
        mock_page.set_default_timeout = MagicMock()
        mock_page.set_default_navigation_timeout = MagicMock()

        mock_context = AsyncMock()
        mock_context.pages = [mock_page]

        mock_browser = AsyncMock()
        mock_browser.contexts = [mock_context]

        mock_pw = AsyncMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

        mock_cm = AsyncMock()
        mock_cm.start = AsyncMock(return_value=mock_pw)

        mock_stealth_mod = MagicMock()
        mock_stealth_mod.stealth_async = AsyncMock()

        with (
            patch(
                "agentic_search_audit.browser.cdp_client.async_playwright",
                return_value=mock_cm,
            ),
            patch.dict("sys.modules", {"playwright_stealth": mock_stealth_mod}),
        ):
            await client.connect()

        assert client._owns_context is False

    async def test_connect_new_context_sets_owns_true(self) -> None:
        from agentic_search_audit.browser.cdp_client import CDPBrowserClient

        client = CDPBrowserClient(cdp_endpoint="ws://localhost:9222")

        mock_page = AsyncMock()
        mock_page.set_default_timeout = MagicMock()
        mock_page.set_default_navigation_timeout = MagicMock()

        mock_context = AsyncMock()
        mock_context.pages = []
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.contexts = []  # no existing contexts
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        mock_pw = AsyncMock()
        mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

        mock_cm = AsyncMock()
        mock_cm.start = AsyncMock(return_value=mock_pw)

        mock_stealth_mod = MagicMock()
        mock_stealth_mod.stealth_async = AsyncMock()

        with (
            patch(
                "agentic_search_audit.browser.cdp_client.async_playwright",
                return_value=mock_cm,
            ),
            patch.dict("sys.modules", {"playwright_stealth": mock_stealth_mod}),
        ):
            await client.connect()

        assert client._owns_context is True


# ---------------------------------------------------------------------------
# Bug #5 (Medium): Factory ImportError guard for undetected
# ---------------------------------------------------------------------------


class TestFactoryUndetectedImportGuard:
    """Factory should raise ImportError when undetected-chromedriver is not installed."""

    def test_missing_uc_raises_import_error(self) -> None:
        from agentic_search_audit.browser.factory import create_browser_client

        config = RunConfig(browser_backend=BrowserBackend.UNDETECTED)
        with patch.dict("sys.modules", {"undetected_chromedriver": None}):
            with pytest.raises(ImportError, match="undetected-chromedriver not installed"):
                create_browser_client(config)


# ---------------------------------------------------------------------------
# Bug #6 (Medium): Whitespace CDP endpoint validation
# ---------------------------------------------------------------------------


class TestWhitespaceCDPValidation:
    """Whitespace-only cdp_endpoint should be normalised to None."""

    def test_whitespace_endpoint_with_cdp_backend_raises(self) -> None:
        with pytest.raises(ValidationError, match="cdp_endpoint.*browserbase_api_key"):
            RunConfig(browser_backend=BrowserBackend.CDP, cdp_endpoint="   ")

    def test_whitespace_endpoint_normalised_to_none(self) -> None:
        config = RunConfig(cdp_endpoint="   ")
        assert config.cdp_endpoint is None

    def test_whitespace_api_key_normalised_to_none(self) -> None:
        config = RunConfig(browserbase_api_key="  \t  ")
        assert config.browserbase_api_key is None

    def test_valid_endpoint_preserved(self) -> None:
        config = RunConfig(
            browser_backend=BrowserBackend.CDP,
            cdp_endpoint="ws://localhost:9222",
        )
        assert config.cdp_endpoint == "ws://localhost:9222"


# ---------------------------------------------------------------------------
# Bug #7 (Low): --cdp-endpoint auto-switches to CDP backend
# ---------------------------------------------------------------------------


class TestCLICdpEndpointAutoSwitch:
    """--cdp-endpoint without --browser should auto-switch to CDP backend."""

    def test_cdp_endpoint_auto_switches_backend(self) -> None:
        import sys

        with patch.object(
            sys,
            "argv",
            [
                "search-audit",
                "--site",
                "nike",
                "--cdp-endpoint",
                "ws://localhost:9222",
            ],
        ):
            from agentic_search_audit.cli.main import parse_args

            args = parse_args()
            assert args.cdp_endpoint == "ws://localhost:9222"
            assert args.browser is None  # user didn't specify --browser
