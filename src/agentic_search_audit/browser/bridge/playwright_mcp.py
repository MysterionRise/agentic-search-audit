"""Playwright MCP transport (experimental outline).

``@playwright/mcp --extension`` attaches to the user's tabs through the official
"Playwright MCP Chrome Extension"; ``--cdp-endpoint`` attaches over CDP; otherwise the
server launches its own browser. Tool names and the evaluate response format are
mapped here but have not been exercised end to end yet (see docs/BROWSER_BACKENDS.md).
"""

import logging
import os
from pathlib import Path
from typing import Any

from ...core.types import BridgeMode, BrowserCapabilities
from .capabilities import LAUNCH_CAPABILITIES, real_profile_capabilities
from .mcp_base import McpStdioTransportBase, SessionFactory, parse_json_block
from .transport import BridgeToolError, BridgeUnsupportedError

logger = logging.getLogger(__name__)

NPM_PACKAGE = "@playwright/mcp@latest"

TOOL_MAP = {
    "navigate": "browser_navigate",
    "evaluate": "browser_evaluate",
    "press_key": "browser_press_key",
    "screenshot": "browser_take_screenshot",
    "resize": "browser_resize",
    "tabs": "browser_tabs",
    "snapshot": "browser_snapshot",
}


class PlaywrightMcpTransport(McpStdioTransportBase):
    """Drives a browser through ``@playwright/mcp`` over stdio (experimental)."""

    name = "playwright_mcp"
    not_ready_help = (
        "Playwright MCP could not reach a browser. For --extension install the "
        '"Playwright MCP Chrome Extension" and keep Chrome open; for a CDP endpoint start '
        "Chrome with --remote-debugging-port and a non-default --user-data-dir."
    )

    def __init__(
        self,
        *,
        mode: BridgeMode = BridgeMode.AUTOCONNECT,
        cdp_endpoint: str | None = None,
        headless: bool = True,
        server_command: str = "npx",
        server_args: list[str] | None = None,
        extra_server_args: list[str] | None = None,
        connect_timeout_s: float = 60.0,
        tool_timeout_s: float = 30.0,
        allow_profile_mutations: bool = False,
        session_factory: SessionFactory | None = None,
    ) -> None:
        self.mode = mode
        self.cdp_endpoint = cdp_endpoint
        self.headless = headless
        self.extra_server_args = list(extra_server_args or [])
        self.allow_profile_mutations = allow_profile_mutations
        self._page_open = False
        super().__init__(
            server_command=server_command,
            server_args=list(server_args) if server_args is not None else [],
            env=dict(os.environ),
            connect_timeout_s=connect_timeout_s,
            tool_timeout_s=tool_timeout_s,
            session_factory=session_factory,
        )
        if server_args is None:
            self.server_args = self.build_server_args()

    def build_server_args(self) -> list[str]:
        args = ["-y", NPM_PACKAGE]
        if self.mode == BridgeMode.AUTOCONNECT:
            args.append("--extension")
        elif self.mode == BridgeMode.BROWSER_URL:
            args += ["--cdp-endpoint", self.cdp_endpoint or "http://127.0.0.1:9222"]
        elif self.headless:
            args.append("--headless")
        return args + self.extra_server_args

    @property
    def capabilities(self) -> BrowserCapabilities:
        if self.mode == BridgeMode.LAUNCH:
            return LAUNCH_CAPABILITIES
        return real_profile_capabilities(allow_profile_mutations=self.allow_profile_mutations)

    async def open(self) -> None:
        await self._start()
        try:
            await self._call(TOOL_MAP["navigate"], {"url": "about:blank"}, self.connect_timeout_s)
        except BaseException:
            await self._stop()
            raise
        self._page_open = True
        self._page_gone = False

    async def close(self) -> None:
        self._page_open = False
        await self._stop()

    def page_alive(self) -> bool:
        return self._page_open and not self._page_gone

    async def navigate(self, url: str, timeout_ms: int) -> str:
        await self._call(TOOL_MAP["navigate"], {"url": url}, timeout_ms / 1000 + 10)
        return url

    async def evaluate(self, function_source: str, timeout_s: float) -> Any:
        text = await self._call(TOOL_MAP["evaluate"], {"function": function_source}, timeout_s)
        # TODO(spike): confirm the response shape; it is expected to carry a ```json block.
        return parse_json_block(text, tool=TOOL_MAP["evaluate"])

    async def press_key(self, key: str) -> None:
        await self._call(TOOL_MAP["press_key"], {"key": key})

    async def type_into_focused(self, text: str) -> None:
        for char in text:
            await self._call(TOOL_MAP["press_key"], {"key": char})

    async def click_at(self, x: float, y: float) -> None:
        raise BridgeUnsupportedError("playwright_mcp clicks by snapshot ref, not coordinates")

    async def screenshot(self, output_path: Path, full_page: bool) -> Path:
        result = await self._call_raw(
            TOOL_MAP["screenshot"],
            {"fullPage": full_page, "type": "png", "filename": str(output_path)},
            self.tool_timeout_s * 2,
        )
        if output_path.exists():
            return output_path
        for item in getattr(result, "content", None) or []:
            if getattr(item, "type", None) == "image" and getattr(item, "data", None):
                import base64

                output_path.write_bytes(base64.b64decode(item.data))
                return output_path
        raise BridgeToolError(TOOL_MAP["screenshot"], f"no file written to {output_path}")

    async def set_viewport(self, width: int, height: int) -> None:
        await self._call(TOOL_MAP["resize"], {"width": width, "height": height})

    async def new_tab(self, url: str) -> None:
        await self._call(TOOL_MAP["tabs"], {"action": "new"})
        await self.navigate(url, 30000)
        self._page_gone = False

    async def snapshot(self) -> str:
        return await self._call(TOOL_MAP["snapshot"], {})

    async def set_user_agent(self, user_agent: str) -> None:
        raise BridgeUnsupportedError("playwright_mcp cannot override the user agent")

    async def clear_cookies(self) -> None:
        raise BridgeUnsupportedError("playwright_mcp cookie clearing is not wired")

    async def set_proxy(self, proxy_url: str) -> None:
        raise BridgeUnsupportedError("playwright_mcp proxies are set on the server command line")
