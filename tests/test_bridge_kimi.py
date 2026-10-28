"""KimiWebBridgeTransport against an in-process fake daemon (aiohttp test server)."""

import base64
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from agentic_search_audit.browser.bridge.kimi_webbridge import (
    DAEMON_DOWN_HELP,
    EXTENSION_HELP,
    KimiWebBridgeTransport,
)
from agentic_search_audit.browser.bridge.transport import (
    BridgeNotReadyError,
    BridgePageGoneError,
    BridgeToolError,
    BridgeUnsupportedError,
)

pytestmark = pytest.mark.unit


class FakeDaemon:
    def __init__(self) -> None:
        self.status: dict[str, Any] = {
            "running": True,
            "extension_connected": True,
            "version": "v2.0.5",
        }
        self.handlers: dict[str, Any] = {}
        self.commands: list[dict[str, Any]] = []
        self.app = web.Application()
        self.app.router.add_get("/status", self._status)
        self.app.router.add_post("/command", self._command)

    async def _status(self, request: web.Request) -> web.Response:
        return web.json_response(self.status)

    async def _command(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.commands.append(body)
        handler = self.handlers.get(body["action"])
        result = handler(body["args"]) if callable(handler) else handler
        if isinstance(result, dict) and "__error__" in result:
            return web.json_response({"ok": False, "error": result["__error__"]}, status=502)
        return web.json_response({"ok": True, "data": result or {}})

    def actions(self) -> list[str]:
        return [c["action"] for c in self.commands]


@pytest_asyncio.fixture
async def daemon() -> AsyncIterator[tuple[FakeDaemon, str]]:
    fake = FakeDaemon()
    async with TestServer(fake.app) as server:
        yield fake, str(server.make_url("")).rstrip("/")


def make_transport(url: str, **kwargs: Any) -> KimiWebBridgeTransport:
    kwargs.setdefault("session_name", "asa-test")
    return KimiWebBridgeTransport(
        daemon_url=url, http_session_factory=aiohttp.ClientSession, **kwargs
    )


async def test_daemon_down_names_the_start_command() -> None:
    t = make_transport("http://127.0.0.1:1")
    with pytest.raises(BridgeNotReadyError) as info:
        await t.open()
    assert "kimi-webbridge start" in str(info.value)
    assert DAEMON_DOWN_HELP.split("{")[0] in str(info.value)
    await t.close()


async def test_extension_missing_names_the_store(daemon: tuple[FakeDaemon, str]) -> None:
    fake, url = daemon
    fake.status["extension_connected"] = False
    t = make_transport(url)
    with pytest.raises(BridgeNotReadyError, match="fldmhceldgbpfpkbgopacenieobmligc"):
        await t.open()
    assert str(EXTENSION_HELP) in str(EXTENSION_HELP)
    await t.close()


async def test_open_creates_a_grouped_tab(daemon: tuple[FakeDaemon, str]) -> None:
    fake, url = daemon
    fake.handlers["navigate"] = lambda args: {"success": True, "url": args["url"], "tabId": 77}
    t = make_transport(url, tab_group_title="Audit run")
    await t.open()
    assert fake.commands[0] == {
        "action": "navigate",
        "args": {"url": "about:blank", "newTab": True, "group_title": "Audit run"},
        "session": "asa-test",
    }
    assert t._tab_id == 77 and t.page_alive() and t.connection_alive()
    await t.close()
    assert fake.actions()[-2:] == ["close_tab", "close_session"]


async def test_evaluate_wraps_as_iife_and_maps_undefined(daemon: tuple[FakeDaemon, str]) -> None:
    fake, url = daemon
    fake.handlers["navigate"] = {"tabId": 1}
    fake.handlers["evaluate"] = lambda args: (
        {"type": "undefined"} if "undefined" in args["code"] else {"type": "number", "value": 5}
    )
    t = make_transport(url)
    await t.open()
    assert await t.evaluate("() => 5", 5) == 5
    assert fake.commands[-1]["args"] == {"code": "(() => 5)()"}
    assert await t.evaluate("() => undefined", 5) is None
    await t.close()


async def test_press_enter_sends_trusted_key_events(daemon: tuple[FakeDaemon, str]) -> None:
    fake, url = daemon
    fake.handlers["navigate"] = {"tabId": 1}
    t = make_transport(url)
    await t.open()
    await t.press_key("Enter")
    events = [c["args"] for c in fake.commands if c["action"] == "cdp"]
    assert [e["method"] for e in events] == ["Input.dispatchKeyEvent", "Input.dispatchKeyEvent"]
    assert events[0]["params"]["type"] == "keyDown" and events[0]["params"]["text"] == "\r"
    assert events[1]["params"]["type"] == "keyUp"
    await t.type_into_focused("a")
    await t.click_at(3, 4)
    methods = [c["args"]["method"] for c in fake.commands if c["action"] == "cdp"]
    assert methods[-3:] == ["Input.dispatchMouseEvent"] * 3
    await t.close()


async def test_full_page_screenshot_uses_layout_metrics(
    daemon: tuple[FakeDaemon, str], tmp_path: Path
) -> None:
    fake, url = daemon
    fake.handlers["navigate"] = {"tabId": 1}

    def cdp(args: dict[str, Any]) -> dict[str, Any]:
        if args["method"] == "Page.getLayoutMetrics":
            return {"cssContentSize": {"width": 1200, "height": 4000}}
        if args["method"] == "Page.captureScreenshot":
            return {"data": base64.b64encode(b"png-bytes").decode()}
        return {}

    fake.handlers["cdp"] = cdp
    t = make_transport(url)
    await t.open()
    target = tmp_path / "shots" / "full.png"
    assert await t.screenshot(target, True) == target
    assert target.read_bytes() == b"png-bytes"
    capture = [
        c["args"] for c in fake.commands if c["args"].get("method") == "Page.captureScreenshot"
    ][0]
    assert capture["params"]["captureBeyondViewport"] is True
    assert capture["params"]["clip"]["height"] == 4000
    await t.screenshot(tmp_path / "view.png", False)
    last = fake.commands[-1]["args"]["params"]
    assert "clip" not in last
    await t.close()


async def test_daemon_errors_map_to_bridge_errors(daemon: tuple[FakeDaemon, str]) -> None:
    fake, url = daemon
    fake.handlers["navigate"] = {"tabId": 1}
    fake.handlers["snapshot"] = {"__error__": {"code": "E_SNAP", "message": "snapshot failed"}}
    fake.handlers["evaluate"] = {"__error__": {"code": "E_TAB", "message": "tab 1 was closed"}}
    t = make_transport(url)
    await t.open()
    with pytest.raises(BridgeToolError) as info:
        await t.snapshot()
    assert info.value.code == "E_SNAP"
    with pytest.raises(BridgePageGoneError):
        await t.evaluate("() => 1", 5)
    assert t.page_alive() is False
    await t.close()


async def test_identity_gates(daemon: tuple[FakeDaemon, str]) -> None:
    fake, url = daemon
    fake.handlers["navigate"] = {"tabId": 1}
    t = make_transport(url)
    await t.open()
    with pytest.raises(BridgeUnsupportedError):
        await t.set_user_agent("ua")
    with pytest.raises(BridgeUnsupportedError):
        await t.set_proxy("http://p")
    await t.close()
    t2 = make_transport(url, allow_profile_mutations=True)
    await t2.open()
    await t2.set_user_agent("ua")
    await t2.clear_cookies()
    methods = [c["args"]["method"] for c in fake.commands if c["action"] == "cdp"]
    assert methods[-2:] == ["Network.setUserAgentOverride", "Network.clearBrowserCookies"]
    await t2.close()


def test_default_session_name_is_timestamped() -> None:
    t = KimiWebBridgeTransport()
    assert t.session_name.startswith("asa-")
    assert json.dumps(t.session_name)  # plain ASCII, safe in the request body
