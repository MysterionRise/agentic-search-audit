"""chrome-devtools-mcp transport: Google's MCP server, attached to a Chrome.

Modes:
- ``autoconnect``: attach to the user's running Chrome (Chrome 144+; the user enables
  chrome://inspect/#remote-debugging once and approves a dialog on first connect).
- ``browser_url``: attach to a Chrome started with ``--remote-debugging-port`` and a
  non-default ``--user-data-dir`` (Chrome 136+ refuses the default profile directory).
- ``launch``: the server starts its own Chrome with a disposable profile.
"""

import logging
import os
from pathlib import Path
from typing import Any

from ...core.types import BridgeMode, BrowserCapabilities
from .capabilities import LAUNCH_CAPABILITIES, real_profile_capabilities
from .mcp_base import (
    McpStdioTransportBase,
    SessionFactory,
    parse_json_block,
    parse_selected_page_id,
)
from .node import check_node_version
from .transport import (
    BridgeNotReadyError,
    BridgePageGoneError,
    BridgeToolError,
    BridgeUnsupportedError,
)

logger = logging.getLogger(__name__)

AUTOCONNECT_HELP = (
    "Could not attach to Chrome via --autoConnect. In Chrome open "
    'chrome://inspect/#remote-debugging, enable "Allow remote debugging for this profile", '
    're-run, and click "Allow" in the Chrome dialog within the connect timeout. '
    "Requires Chrome 144 or newer{chrome_version}."
)
BROWSER_URL_HELP = (
    "Nothing is listening on {browser_url}. Start Chrome with: "
    '"<path to chrome>" --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-audit-profile" '
    "(Chrome 136+ refuses the default profile directory) and re-run."
)
LAUNCH_HELP = "chrome-devtools-mcp could not start Chrome; check that Chrome is installed."

NPM_PACKAGE = "chrome-devtools-mcp@latest"


def _chrome_version_note() -> str:
    try:
        from ..undetected_client import detect_chrome_version

        version = detect_chrome_version()
    except Exception:
        return ""
    return f" (detected: Chrome {version})" if version else ""


class ChromeDevtoolsMcpTransport(McpStdioTransportBase):
    """Drives Chrome through ``chrome-devtools-mcp`` over stdio."""

    name = "chrome_devtools_mcp"

    def __init__(
        self,
        *,
        mode: BridgeMode = BridgeMode.AUTOCONNECT,
        browser_url: str | None = None,
        headless: bool = True,
        isolated: bool = True,
        proxy_url: str | None = None,
        viewport: tuple[int, int] = (1366, 900),
        channel: str = "stable",
        server_command: str = "npx",
        server_args: list[str] | None = None,
        extra_server_args: list[str] | None = None,
        connect_timeout_s: float = 60.0,
        tool_timeout_s: float = 30.0,
        allow_profile_mutations: bool = False,
        experimental_vision_click: bool = False,
        close_tabs_on_disconnect: bool = True,
        session_factory: SessionFactory | None = None,
        node_check: bool = True,
    ) -> None:
        self.mode = mode
        self.browser_url = browser_url
        self.headless = headless
        self.isolated = isolated
        self.proxy_url = proxy_url
        self.viewport = viewport
        self.channel = channel
        self.extra_server_args = list(extra_server_args or [])
        self.allow_profile_mutations = allow_profile_mutations
        self.experimental_vision_click = experimental_vision_click
        self.close_tabs_on_disconnect = close_tabs_on_disconnect
        self._node_check = node_check
        self._page_id: int | None = None
        self._owned_page_ids: list[int] = []
        self._context_counter = 0
        env = {**os.environ, "CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS": "1"}
        super().__init__(
            server_command=server_command,
            server_args=list(server_args) if server_args is not None else [],
            env=env,
            connect_timeout_s=connect_timeout_s,
            tool_timeout_s=tool_timeout_s,
            session_factory=session_factory,
        )
        if server_args is None:
            self.server_args = self.build_server_args()

    # -- configuration -------------------------------------------------

    def build_server_args(self) -> list[str]:
        """The npx argv for the configured mode."""
        args = ["-y", NPM_PACKAGE, "--usageStatistics=false", "--categoryPerformance=false"]
        if self.mode == BridgeMode.AUTOCONNECT:
            args += ["--autoConnect", "--channel", self.channel]
        elif self.mode == BridgeMode.BROWSER_URL:
            args += ["--browserUrl", self.browser_url or "http://127.0.0.1:9222"]
        else:
            args += [
                "--viewport",
                f"{self.viewport[0]}x{self.viewport[1]}",
                "--channel",
                self.channel,
            ]
            if self.headless:
                args.append("--headless")
            if self.isolated:
                args.append("--isolated")
            if self.proxy_url:
                args += ["--proxyServer", self.proxy_url]
        if self.experimental_vision_click:
            args.append("--experimentalVision")
        return args + self.extra_server_args

    @property
    def capabilities(self) -> BrowserCapabilities:
        if self.mode == BridgeMode.LAUNCH:
            return LAUNCH_CAPABILITIES.model_copy(
                update={"trusted_click": self.experimental_vision_click}
            )
        return real_profile_capabilities(
            allow_profile_mutations=self.allow_profile_mutations,
            trusted_click=self.experimental_vision_click,
        )

    @property
    def not_ready_help(self) -> str:  # type: ignore[override]
        if self.mode == BridgeMode.AUTOCONNECT:
            return AUTOCONNECT_HELP.format(chrome_version=_chrome_version_note())
        if self.mode == BridgeMode.BROWSER_URL:
            return BROWSER_URL_HELP.format(browser_url=self.browser_url)
        return LAUNCH_HELP

    # -- lifecycle -----------------------------------------------------

    async def open(self) -> None:
        if self._node_check and self.server_command in ("npx", "node", "chrome-devtools-mcp"):
            await check_node_version()
        await self._start()
        try:
            # The server connects to Chrome lazily; in autoconnect mode the permission
            # dialog appears here, so this call gets the connect timeout.
            try:
                await self._call("list_pages", {}, self.connect_timeout_s)
            except BridgeToolError as exc:
                raise BridgeNotReadyError(f"{exc}\n{self.not_ready_help}") from exc
            await self._open_owned_page("about:blank")
        except BaseException:
            # Never leave the server running after a failed open: the session context
            # manager must be exited here, in this task.
            await self._stop()
            raise

    async def _open_owned_page(self, url: str, isolated_context: str | None = None) -> int:
        arguments: dict[str, Any] = {"url": url}
        if isolated_context:
            arguments["isolatedContext"] = isolated_context
        text = await self._call("new_page", arguments)
        page_id = parse_selected_page_id(text)
        if page_id is None:
            raise BridgeToolError(
                "new_page", f"could not read the new page id from: {text[:200]!r}"
            )
        previous = self._page_id
        self._page_id = page_id
        self._owned_page_ids.append(page_id)
        self._page_gone = False
        if previous is not None:
            await self._close_owned_page(previous)
        return page_id

    async def _close_owned_page(self, page_id: int) -> None:
        try:
            await self._call("close_page", {"pageId": page_id})
        except Exception as e:  # the last open page cannot be closed; not fatal
            logger.debug(f"{self.name}: could not close page {page_id}: {e}")
        if page_id in self._owned_page_ids:
            self._owned_page_ids.remove(page_id)

    async def close(self) -> None:
        if self._session is not None and self.close_tabs_on_disconnect:
            for page_id in list(self._owned_page_ids):
                await self._close_owned_page(page_id)
        self._page_id = None
        await self._stop()

    def page_alive(self) -> bool:
        return self._page_id is not None and not self._page_gone

    def _page_args(self, **arguments: Any) -> dict[str, Any]:
        """Arguments for a page-scoped tool: the server routes by pageId (on by default)."""
        if self._page_id is None:
            raise BridgePageGoneError(f"{self.name}: no page is open")
        return {"pageId": self._page_id, **arguments}

    # -- primitives ----------------------------------------------------

    async def navigate(self, url: str, timeout_ms: int) -> str:
        await self._call(
            "navigate_page",
            self._page_args(type="url", url=url, timeout=timeout_ms),
            timeout_ms / 1000 + 10,
        )
        return url

    async def evaluate(self, function_source: str, timeout_s: float) -> Any:
        text = await self._call(
            "evaluate_script", self._page_args(function=function_source), timeout_s
        )
        return parse_json_block(text)

    async def press_key(self, key: str) -> None:
        await self._call("press_key", self._page_args(key=key))

    async def type_into_focused(self, text: str) -> None:
        await self._call("type_text", self._page_args(text=text))

    async def click_at(self, x: float, y: float) -> None:
        if not self.experimental_vision_click:
            raise BridgeUnsupportedError(
                "click_at needs run.bridge.experimental_vision_click: true (--experimentalVision)"
            )
        await self._call("click_at", self._page_args(x=x, y=y))

    async def screenshot(self, output_path: Path, full_page: bool) -> Path:
        result = await self._call_raw(
            "take_screenshot",
            self._page_args(fullPage=full_page, format="png", filePath=str(output_path)),
            self.tool_timeout_s * 2,
        )
        if output_path.exists():
            return output_path
        # The server may refuse the path (workspace restriction) and return the image inline.
        for item in getattr(result, "content", None) or []:
            if getattr(item, "type", None) == "image" and getattr(item, "data", None):
                import base64

                output_path.write_bytes(base64.b64decode(item.data))
                return output_path
        raise BridgeToolError("take_screenshot", f"no file written to {output_path}")

    async def set_viewport(self, width: int, height: int) -> None:
        await self._call("resize_page", self._page_args(width=width, height=height))

    async def new_tab(self, url: str) -> None:
        await self._open_owned_page(url)

    async def snapshot(self) -> str:
        return await self._call("take_snapshot", self._page_args())

    async def set_user_agent(self, user_agent: str) -> None:
        if not self.capabilities.user_agent_override:
            raise BridgeUnsupportedError("user-agent override is off for a real profile")
        await self._call("emulate", self._page_args(userAgent=user_agent))

    async def clear_cookies(self) -> None:
        if not self.capabilities.clear_cookies:
            raise BridgeUnsupportedError("cookie clearing is off for a real profile")
        # The server has no cookie API; a fresh isolated context is a fresh cookie jar.
        self._context_counter += 1
        await self._open_owned_page("about:blank", isolated_context=f"asa-{self._context_counter}")

    async def set_proxy(self, proxy_url: str) -> None:
        if self.mode != BridgeMode.LAUNCH:
            raise BridgeUnsupportedError("proxies can only be set when the bridge launches Chrome")
        self.proxy_url = proxy_url
        self.server_args = self.build_server_args()
        await self.close()
        await self.open()
