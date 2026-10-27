"""Kimi WebBridge transport: the user's real Chrome through a local HTTP daemon.

Protocol (daemon v2): ``POST {daemon_url}/command`` with ``{"action", "args", "session"}``
returns ``{"ok": true, "data": {...}}`` or HTTP 502 ``{"ok": false, "error": {code, message}}``;
``GET /status`` reports ``running`` and ``extension_connected``. Input goes through the
raw ``cdp`` action so clicks and keys are trusted (the daemon's own ``click``/``fill``
dispatch synthetic events). The daemon sends usage telemetry to Moonshot; see docs.
"""

import asyncio
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp

from ...core.types import BrowserCapabilities
from .capabilities import real_profile_capabilities
from .kimi_keys import char_events, click_events, key_events
from .transport import (
    BridgeConnectionError,
    BridgeNotReadyError,
    BridgePageGoneError,
    BridgeTimeoutError,
    BridgeToolError,
    BridgeUnsupportedError,
)

logger = logging.getLogger(__name__)

DAEMON_DOWN_HELP = (
    "Kimi WebBridge daemon is not running at {daemon_url}. Start it with "
    "`~/.kimi-webbridge/bin/kimi-webbridge start` (install: https://www.kimi.com/features/webbridge)."
)
EXTENSION_HELP = (
    "Kimi WebBridge daemon is running but its Chrome extension is not connected. Install "
    "it from the Chrome Web Store (id fldmhceldgbpfpkbgopacenieobmligc), keep Chrome open, "
    "then re-run."
)

_TAB_GONE_MARKERS = ("closed", "not found", "no tab", "gone", "detached", "no such tab")


class KimiWebBridgeTransport:
    """Drives the user's Chrome through the Kimi WebBridge daemon."""

    name = "kimi_webbridge"

    def __init__(
        self,
        *,
        daemon_url: str = "http://127.0.0.1:10086",
        session_name: str | None = None,
        tab_group_title: str = "Search Audit",
        request_timeout_s: float = 30.0,
        allow_profile_mutations: bool = False,
        close_tabs_on_disconnect: bool = True,
        http_session_factory: Any = None,
    ) -> None:
        self.daemon_url = daemon_url.rstrip("/")
        self.session_name = session_name or f"asa-{datetime.now():%Y%m%d-%H%M%S}"
        self.tab_group_title = tab_group_title
        self.request_timeout_s = request_timeout_s
        self.close_tabs_on_disconnect = close_tabs_on_disconnect
        self._capabilities: BrowserCapabilities = real_profile_capabilities(
            allow_profile_mutations=allow_profile_mutations, trusted_click=True
        )
        self._http_session_factory = http_session_factory or aiohttp.ClientSession
        self._http: aiohttp.ClientSession | None = None
        self._tab_id: Any = None
        self._tab_gone = False
        self._daemon_ok = False

    @property
    def capabilities(self) -> BrowserCapabilities:
        return self._capabilities

    # -- HTTP ----------------------------------------------------------

    async def _command(
        self, action: str, args: dict[str, Any], timeout_s: float | None = None
    ) -> dict[str, Any]:
        if self._http is None:
            raise BridgeConnectionError(f"{self.name}: not connected")
        timeout = aiohttp.ClientTimeout(total=timeout_s or self.request_timeout_s)
        body = {"action": action, "args": args, "session": self.session_name}
        logger.debug(f"{self.name}: {action} {args}")
        try:
            async with self._http.post(
                f"{self.daemon_url}/command", json=body, timeout=timeout
            ) as response:
                status = response.status
                payload = await response.json(content_type=None)
        except asyncio.TimeoutError as exc:
            raise BridgeTimeoutError(f"{action} timed out after {timeout.total}s") from exc
        except aiohttp.ClientConnectionError as exc:
            self._daemon_ok = False
            raise BridgeConnectionError(
                f"{self.name}: daemon unreachable during {action}: {exc}"
            ) from exc

        if isinstance(payload, dict) and payload.get("ok") is True:
            data = payload.get("data")
            return data if isinstance(data, dict) else {}

        error = payload.get("error") if isinstance(payload, dict) else None
        error = error if isinstance(error, dict) else {}
        code = str(error.get("code") or status)
        message = str(error.get("message") or payload)
        lower = message.lower()
        if "tab" in lower and any(marker in lower for marker in _TAB_GONE_MARKERS):
            self._tab_gone = True
            raise BridgePageGoneError(f"{action}: {message}")
        raise BridgeToolError(action, message, code)

    async def _cdp(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return await self._command("cdp", {"method": method, "params": params})

    async def status(self) -> dict[str, Any]:
        """``GET /status``; raises ``BridgeNotReadyError`` when the daemon is down."""
        if self._http is None:
            raise BridgeConnectionError(f"{self.name}: not connected")
        try:
            async with self._http.get(
                f"{self.daemon_url}/status", timeout=aiohttp.ClientTimeout(total=3)
            ) as response:
                payload = await response.json(content_type=None)
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as exc:
            raise BridgeNotReadyError(DAEMON_DOWN_HELP.format(daemon_url=self.daemon_url)) from exc
        return payload if isinstance(payload, dict) else {}

    # -- lifecycle -----------------------------------------------------

    async def open(self) -> None:
        self._http = self._http_session_factory()
        status = await self.status()
        if status.get("running") is False:
            raise BridgeNotReadyError(DAEMON_DOWN_HELP.format(daemon_url=self.daemon_url))
        if not status.get("extension_connected"):
            raise BridgeNotReadyError(EXTENSION_HELP)
        self._daemon_ok = True
        data = await self._command(
            "navigate",
            {"url": "about:blank", "newTab": True, "group_title": self.tab_group_title},
        )
        self._tab_id = data.get("tabId")
        self._tab_gone = False
        logger.info(f"{self.name}: session {self.session_name!r} opened tab {self._tab_id}")

    async def close(self) -> None:
        try:
            if self._http is not None and self._daemon_ok and self.close_tabs_on_disconnect:
                for action in ("close_tab", "close_session"):
                    try:
                        await self._command(action, {})
                    except Exception as e:
                        logger.debug(f"{self.name}: {action} failed: {e}")
        finally:
            if self._http is not None:
                await self._http.close()
            self._http = None
            self._tab_id = None

    def page_alive(self) -> bool:
        return self._tab_id is not None and not self._tab_gone

    def connection_alive(self) -> bool:
        return self._http is not None and self._daemon_ok

    # -- primitives ----------------------------------------------------

    async def navigate(self, url: str, timeout_ms: int) -> str:
        data = await self._command("navigate", {"url": url}, timeout_ms / 1000 + 10)
        return str(data.get("url") or url)

    async def evaluate(self, function_source: str, timeout_s: float) -> Any:
        data = await self._command("evaluate", {"code": f"({function_source})()"}, timeout_s)
        if data.get("type") == "undefined":
            return None
        return data.get("value")

    async def press_key(self, key: str) -> None:
        for method, params in key_events(key):
            await self._cdp(method, params)

    async def type_into_focused(self, text: str) -> None:
        for char in text:
            for method, params in char_events(char):
                await self._cdp(method, params)

    async def click_at(self, x: float, y: float) -> None:
        for method, params in click_events(x, y):
            await self._cdp(method, params)

    async def screenshot(self, output_path: Path, full_page: bool) -> Path:
        params: dict[str, Any] = {"format": "png"}
        if full_page:
            metrics = await self._cdp("Page.getLayoutMetrics", {})
            size = metrics.get("cssContentSize") or metrics.get("contentSize") or {}
            width, height = size.get("width"), size.get("height")
            if isinstance(width, int | float) and isinstance(height, int | float):
                params["captureBeyondViewport"] = True
                params["clip"] = {"x": 0, "y": 0, "width": width, "height": height, "scale": 1}
        data = await self._cdp("Page.captureScreenshot", params)
        encoded = data.get("data")
        if not isinstance(encoded, str) or not encoded:
            raise BridgeToolError("screenshot", "Page.captureScreenshot returned no data")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(encoded))
        return output_path

    async def set_viewport(self, width: int, height: int) -> None:
        await self._cdp(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 0, "mobile": False},
        )

    async def new_tab(self, url: str) -> None:
        data = await self._command("navigate", {"url": url, "newTab": True})
        self._tab_id = data.get("tabId")
        self._tab_gone = False

    async def snapshot(self) -> str:
        data = await self._command("snapshot", {})
        return str(data.get("tree") or "")

    async def set_user_agent(self, user_agent: str) -> None:
        if not self.capabilities.user_agent_override:
            raise BridgeUnsupportedError("user-agent override is off for a real profile")
        await self._cdp("Network.setUserAgentOverride", {"userAgent": user_agent})

    async def clear_cookies(self) -> None:
        if not self.capabilities.clear_cookies:
            raise BridgeUnsupportedError("cookie clearing is off for a real profile")
        await self._cdp("Network.clearBrowserCookies", {})

    async def set_proxy(self, proxy_url: str) -> None:
        raise BridgeUnsupportedError("Kimi WebBridge drives the user's Chrome; set the proxy there")
