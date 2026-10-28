"""Bridge backends in config, factory and CLI."""

import sys
from unittest.mock import patch

import pytest

from agentic_search_audit.browser.bridge import BridgeBrowserClient
from agentic_search_audit.browser.factory import create_browser_client
from agentic_search_audit.cli.main import parse_args
from agentic_search_audit.core.types import (
    BRIDGE_BACKENDS,
    BridgeConfig,
    BridgeMode,
    BrowserBackend,
    RunConfig,
)

pytestmark = pytest.mark.unit


class TestConfig:
    def test_defaults(self) -> None:
        cfg = RunConfig(browser_backend="chrome_devtools_mcp")
        assert cfg.bridge.mode is BridgeMode.AUTOCONNECT
        assert cfg.bridge.allow_profile_mutations is False
        assert BrowserBackend.CHROME_DEVTOOLS_MCP in BRIDGE_BACKENDS

    def test_browser_url_mode_requires_url(self) -> None:
        with pytest.raises(ValueError, match="bridge.browser_url"):
            RunConfig(browser_backend="chrome_devtools_mcp", bridge={"mode": "browser_url"})
        RunConfig(
            browser_backend="chrome_devtools_mcp",
            bridge={"mode": "browser_url", "browser_url": "http://127.0.0.1:9222"},
        )

    def test_proxy_only_with_launch_mode(self) -> None:
        with pytest.raises(ValueError, match="launch"):
            RunConfig(browser_backend="chrome_devtools_mcp", proxy_url="http://p:1")
        RunConfig(
            browser_backend="chrome_devtools_mcp", proxy_url="http://p:1", bridge={"mode": "launch"}
        )

    def test_kimi_ignores_mode_rules(self) -> None:
        RunConfig(browser_backend="kimi_webbridge", bridge={"mode": "browser_url"})

    def test_unknown_bridge_key_rejected(self) -> None:
        with pytest.raises(ValueError):
            BridgeConfig(nope=1)  # type: ignore[call-arg]


class TestFactory:
    @pytest.mark.parametrize("backend", ["chrome_devtools_mcp", "kimi_webbridge", "playwright_mcp"])
    def test_bridge_backends_build_bridge_clients(self, backend: str) -> None:
        client = create_browser_client(RunConfig(browser_backend=backend))
        assert isinstance(client, BridgeBrowserClient)
        assert client.transport.name == backend
        assert client.capabilities.user_agent_override is False
        assert client.apply_viewport is False  # real profile: never resize the window

    def test_launch_mode_applies_viewport(self) -> None:
        client = create_browser_client(
            RunConfig(browser_backend="chrome_devtools_mcp", bridge={"mode": "launch"})
        )
        assert client.apply_viewport is True
        assert client.capabilities.isolated_profile is True


class TestCli:
    def _parse(self, *argv: str) -> object:
        with patch.object(sys, "argv", ["search-audit", "--site", "nike", *argv]):
            return parse_args()

    def test_browser_choices(self) -> None:
        args = self._parse("--browser", "kimi_webbridge")
        assert args.browser == "kimi_webbridge"  # type: ignore[attr-defined]

    def test_bridge_flags(self) -> None:
        args = self._parse(
            "--browser",
            "chrome_devtools_mcp",
            "--browser-url",
            "http://127.0.0.1:9222",
            "--bridge-session",
            "run-1",
            "--allow-profile-mutations",
        )
        assert args.browser_url == "http://127.0.0.1:9222"  # type: ignore[attr-defined]
        assert args.bridge_session == "run-1"  # type: ignore[attr-defined]
        assert args.allow_profile_mutations is True  # type: ignore[attr-defined]
        assert args.bridge_mode is None  # type: ignore[attr-defined]
