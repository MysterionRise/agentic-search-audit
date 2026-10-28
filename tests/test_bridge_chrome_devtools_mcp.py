"""ChromeDevtoolsMcpTransport against a fake MCP session (no Node, no Chrome)."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import types
from mcp.shared.exceptions import McpError

from agentic_search_audit.browser.bridge.chrome_devtools_mcp import (
    AUTOCONNECT_HELP,
    ChromeDevtoolsMcpTransport,
)
from agentic_search_audit.browser.bridge.transport import (
    BridgeConnectionError,
    BridgeNotReadyError,
    BridgePageGoneError,
    BridgeTimeoutError,
    BridgeToolError,
    BridgeUnsupportedError,
)
from agentic_search_audit.browser.errors import BrowserErrorKind, classify_error
from agentic_search_audit.core.types import BridgeMode

pytestmark = pytest.mark.unit

PAGES_ONE = "## Pages\n1: Shop (https://shop.example/) [selected]\n"


def text_result(text: str, is_error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)], isError=is_error
    )


def pages(selected: int, *ids: int) -> str:
    lines = ["## Pages"]
    for page_id in ids or (selected,):
        tag = " [selected]" if page_id == selected else ""
        lines.append(f"{page_id}: about:blank (about:blank){tag}")
    return "\n".join(lines) + "\n"


class FakeMcpSession:
    """Answers tool calls from a dict of handlers; records every call."""

    def __init__(self, handlers: dict[str, Any]) -> None:
        self.handlers = handlers
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._new_page_counter = 1

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        read_timeout_seconds: timedelta | None = None,
    ) -> Any:
        arguments = arguments or {}
        self.calls.append((name, arguments))
        handler = self.handlers.get(name)
        if handler is None and name == "new_page":
            self._new_page_counter += 1
            return text_result(pages(self._new_page_counter, 1, self._new_page_counter))
        if handler is None:
            return text_result("ok")
        value = handler(arguments) if callable(handler) else handler
        if asyncio.iscoroutine(value):
            try:
                value = await asyncio.wait_for(
                    value, read_timeout_seconds.total_seconds() if read_timeout_seconds else None
                )
            except asyncio.TimeoutError:
                # What the real SDK raises when read_timeout_seconds expires
                raise McpError(
                    types.ErrorData(
                        code=-32001,  # REQUEST_TIMEOUT
                        message="Timed out while waiting for response to ClientRequest.",
                    )
                ) from None
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, types.CallToolResult):
            return value
        return text_result(str(value))

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


def make_factory(session: FakeMcpSession) -> tuple[Callable[..., Any], dict[str, Any]]:
    seen: dict[str, Any] = {}

    @asynccontextmanager
    async def factory(
        command: str, args: list[str], env: dict[str, str] | None, init_timeout_s: float
    ) -> AsyncIterator[FakeMcpSession]:
        seen["command"], seen["args"], seen["env"] = command, args, env
        seen["init_timeout_s"] = init_timeout_s
        yield session

    return factory, seen


def transport(
    session: FakeMcpSession, **kwargs: Any
) -> tuple[ChromeDevtoolsMcpTransport, dict[str, Any]]:
    factory, seen = make_factory(session)
    kwargs.setdefault("mode", BridgeMode.AUTOCONNECT)
    t = ChromeDevtoolsMcpTransport(session_factory=factory, node_check=False, **kwargs)
    return t, seen


class TestServerArgs:
    def test_autoconnect(self) -> None:
        t = ChromeDevtoolsMcpTransport(mode=BridgeMode.AUTOCONNECT, node_check=False)
        assert t.build_server_args() == [
            "-y",
            "chrome-devtools-mcp@latest",
            "--usageStatistics=false",
            "--performanceCrux=false",
            "--categoryPerformance=false",
            "--autoConnect",
            "--channel",
            "stable",
        ]

    def test_browser_url(self) -> None:
        t = ChromeDevtoolsMcpTransport(
            mode=BridgeMode.BROWSER_URL, browser_url="http://127.0.0.1:9222", node_check=False
        )
        assert "--browserUrl" in t.build_server_args()
        assert "http://127.0.0.1:9222" in t.build_server_args()
        assert "--autoConnect" not in t.build_server_args()

    def test_launch(self) -> None:
        t = ChromeDevtoolsMcpTransport(
            mode=BridgeMode.LAUNCH,
            headless=True,
            proxy_url="http://p:1",
            viewport=(800, 600),
            experimental_vision_click=True,
            extra_server_args=["--chromeArg=--foo"],
            node_check=False,
        )
        args = t.build_server_args()
        assert "--headless" in args and "--isolated" in args
        assert args[args.index("--viewport") + 1] == "800x600"
        assert args[args.index("--proxyServer") + 1] == "http://p:1"
        assert "--experimentalVision" in args and args[-1] == "--chromeArg=--foo"

    def test_explicit_server_args_override(self) -> None:
        t = ChromeDevtoolsMcpTransport(server_args=["custom"], node_check=False)
        assert t.server_args == ["custom"]

    def test_capabilities_by_mode(self) -> None:
        real = ChromeDevtoolsMcpTransport(node_check=False).capabilities
        assert not real.user_agent_override and not real.clear_cookies and not real.isolated_profile
        allowed = ChromeDevtoolsMcpTransport(
            allow_profile_mutations=True, node_check=False
        ).capabilities
        assert (
            allowed.user_agent_override and allowed.clear_cookies and not allowed.isolated_profile
        )
        launch = ChromeDevtoolsMcpTransport(mode=BridgeMode.LAUNCH, node_check=False).capabilities
        assert launch.isolated_profile and launch.clear_cookies and not launch.trusted_click


class TestLifecycle:
    async def test_open_attaches_and_owns_a_new_page(self) -> None:
        session = FakeMcpSession({"list_pages": PAGES_ONE})
        t, seen = transport(session)
        await t.open()
        assert seen["env"]["CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS"] == "1"
        assert session.names() == ["list_pages", "new_page"]
        assert session.calls[1][1] == {"url": "about:blank"}  # new_page is not page-scoped
        assert t._page_id == 2 and t.page_alive() and t.connection_alive()

    async def test_open_not_ready_names_the_fix(self) -> None:
        session = FakeMcpSession(
            {"list_pages": text_result("Could not connect to Chrome. Check chrome://inspect", True)}
        )
        t, _ = transport(session)
        with pytest.raises(BridgeNotReadyError) as info:
            await t.open()
        assert "chrome://inspect/#remote-debugging" in str(info.value)
        assert AUTOCONNECT_HELP.split("{")[0] in str(info.value)

    async def test_close_closes_only_owned_pages_and_tolerates_errors(self) -> None:
        session = FakeMcpSession(
            {
                "list_pages": PAGES_ONE,
                "close_page": text_result("The last open page cannot be closed", True),
            }
        )
        t, _ = transport(session)
        await t.open()
        await t.close()
        closes = [args for name, args in session.calls if name == "close_page"]
        assert closes == [{"pageId": 2}]
        assert t.page_alive() is False and t.connection_alive() is False

    async def test_new_tab_replaces_the_owned_page(self) -> None:
        session = FakeMcpSession({"list_pages": PAGES_ONE})
        t, _ = transport(session)
        await t.open()
        await t.new_tab("https://x/")
        assert t._page_id == 3
        assert ("close_page", {"pageId": 2}) in session.calls
        assert t._owned_page_ids == [3]


class TestPrimitives:
    async def _open(
        self, handlers: dict[str, Any], **kwargs: Any
    ) -> tuple[ChromeDevtoolsMcpTransport, FakeMcpSession]:
        session = FakeMcpSession({"list_pages": PAGES_ONE, **handlers})
        t, _ = transport(session, **kwargs)
        await t.open()
        session.calls.clear()
        return t, session

    async def test_evaluate_parses_the_json_block(self) -> None:
        t, session = await self._open(
            {
                "evaluate_script": lambda a: 'Script ran on page and returned:\n```json\n{"a": 1}\n```'
            }
        )
        assert await t.evaluate("() => ({a: 1})", 5) == {"a": 1}
        assert session.calls[0] == ("evaluate_script", {"pageId": 2, "function": "() => ({a: 1})"})

    async def test_evaluate_undefined_is_none(self) -> None:
        t, _ = await self._open(
            {"evaluate_script": "Script ran on page and returned:\n```json\nundefined\n```"}
        )
        assert await t.evaluate("() => undefined", 5) is None

    async def test_navigate_press_type_viewport_snapshot(self) -> None:
        t, session = await self._open({"take_snapshot": "- document\n  - link"})
        assert await t.navigate("https://x/", 30000) == "https://x/"
        await t.press_key("Enter")
        await t.type_into_focused("ab")
        await t.set_viewport(1000, 700)
        assert await t.snapshot() == "- document\n  - link"
        assert session.calls[0] == (
            "navigate_page",
            {"pageId": 2, "type": "url", "url": "https://x/", "timeout": 30000},
        )
        assert ("press_key", {"pageId": 2, "key": "Enter"}) in session.calls
        assert ("type_text", {"pageId": 2, "text": "ab"}) in session.calls
        assert ("resize_page", {"pageId": 2, "width": 1000, "height": 700}) in session.calls
        assert ("take_snapshot", {"pageId": 2}) in session.calls

    async def test_click_at_requires_vision(self) -> None:
        t, _ = await self._open({})
        with pytest.raises(BridgeUnsupportedError):
            await t.click_at(1, 2)
        t2, session2 = await self._open({}, experimental_vision_click=True)
        await t2.click_at(1, 2)
        assert ("click_at", {"pageId": 2, "x": 1, "y": 2}) in session2.calls

    async def test_screenshot_is_taken_inline_and_written_locally(self, tmp_path: Path) -> None:
        inline = types.CallToolResult(
            content=[types.ImageContent(type="image", data="cG5n", mimeType="image/png")]
        )
        t, session = await self._open({"take_screenshot": inline})
        target = tmp_path / "shots" / "a.png"
        assert await t.screenshot(target, True) == target and target.read_bytes() == b"png"
        # no filePath: the server only writes inside its own workspace
        assert session.calls[0][1] == {"pageId": 2, "fullPage": True, "format": "png"}

    async def test_large_screenshot_is_copied_from_the_server_temp_file(
        self, tmp_path: Path
    ) -> None:
        server_file = tmp_path / "server-tmp" / "screenshot.png"
        server_file.parent.mkdir()
        server_file.write_bytes(b"big-png")
        message = f"Took a screenshot of the full current page.\nSaved screenshot to {server_file}."
        t, _ = await self._open({"take_screenshot": message})
        target = tmp_path / "out" / "big.png"
        assert await t.screenshot(target, True) == target
        assert target.read_bytes() == b"big-png"
        assert not server_file.exists()  # the temporary file is cleaned up

    async def test_screenshot_without_image_raises(self, tmp_path: Path) -> None:
        t, _ = await self._open({"take_screenshot": "nothing"})
        with pytest.raises(BridgeToolError):
            await t.screenshot(tmp_path / "c.png", True)

    async def test_identity_gates(self) -> None:
        t, _ = await self._open({})
        with pytest.raises(BridgeUnsupportedError):
            await t.set_user_agent("ua")
        with pytest.raises(BridgeUnsupportedError):
            await t.clear_cookies()
        with pytest.raises(BridgeUnsupportedError):
            await t.set_proxy("http://p")

    async def test_clear_cookies_in_launch_mode_rotates_an_isolated_context(self) -> None:
        t, session = await self._open({}, mode=BridgeMode.LAUNCH)
        await t.clear_cookies()
        assert session.calls[0] == ("new_page", {"url": "about:blank", "isolatedContext": "asa-1"})
        assert ("close_page", {"pageId": 2}) in session.calls

    async def test_user_agent_when_allowed(self) -> None:
        t, session = await self._open({}, allow_profile_mutations=True)
        await t.set_user_agent("ua-x")
        assert ("emulate", {"pageId": 2, "userAgent": "ua-x"}) in session.calls


class TestErrors:
    async def _open(
        self, handlers: dict[str, Any], **kwargs: Any
    ) -> tuple[ChromeDevtoolsMcpTransport, FakeMcpSession]:
        session = FakeMcpSession({"list_pages": PAGES_ONE, **handlers})
        t, _ = transport(session, **kwargs)
        await t.open()
        return t, session

    async def test_page_gone_flips_page_alive(self) -> None:
        t, _ = await self._open(
            {"evaluate_script": text_result("Target page has been closed", True)}
        )
        with pytest.raises(BridgePageGoneError) as info:
            await t.evaluate("() => 1", 5)
        assert t.page_alive() is False
        assert classify_error(info.value) is BrowserErrorKind.PAGE_CLOSED

    async def test_broken_stream_flips_connection_alive(self) -> None:
        t, _ = await self._open({"evaluate_script": anyio.ClosedResourceError()})
        with pytest.raises(BridgeConnectionError) as info:
            await t.evaluate("() => 1", 5)
        assert t.connection_alive() is False
        assert classify_error(info.value) is BrowserErrorKind.BROWSER_DEAD

    async def test_tool_timeout(self) -> None:
        async def slow(args: dict[str, Any]) -> str:
            await asyncio.sleep(1)
            return "late"

        t, _ = await self._open({"evaluate_script": slow}, tool_timeout_s=0.05)
        with pytest.raises(BridgeTimeoutError) as info:
            await t.evaluate("() => 1", 0.05)
        assert classify_error(info.value) is BrowserErrorKind.TIMEOUT

    async def test_other_tool_errors(self) -> None:
        t, _ = await self._open(
            {"evaluate_script": text_result("Navigation timeout of 30000 ms", True)}
        )
        with pytest.raises(BridgeToolError) as info:
            await t.evaluate("() => 1", 5)
        assert classify_error(info.value) is BrowserErrorKind.TRANSIENT
        t2, _ = await self._open({"evaluate_script": text_result("Unknown tool", True)})
        with pytest.raises(BridgeToolError) as info2:
            await t2.evaluate("() => 1", 5)
        assert classify_error(info2.value) is BrowserErrorKind.PERMANENT
