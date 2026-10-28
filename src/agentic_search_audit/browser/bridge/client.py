"""``BridgeBrowserClient``: the whole ``BrowserClient`` protocol over a ``BridgeTransport``.

Everything DOM-related is JavaScript (``js.py``) run through the transport's evaluate
primitive, so each bridge only has to provide navigation, evaluation, keys, screenshots
and tab lifecycle. Waits run *inside* the page as one call each, which keeps the number
of tool round trips low.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from ...core.types import BrowserCapabilities, JsValue
from .._js import decode_result, wrap_expression
from ..stealth import human_typing_delay, pre_action_delay
from . import js
from .transport import (
    BridgeToolError,
    BridgeTransport,
    BridgeUnsupportedError,
    TrustedInputTransport,
)

logger = logging.getLogger(__name__)


class BridgeBrowserClient:
    """A ``BrowserClient`` implemented once for every bridge transport."""

    def __init__(
        self,
        transport: BridgeTransport,
        *,
        viewport_width: int = 1366,
        viewport_height: int = 900,
        click_timeout_ms: int = 5000,
        network_idle_ms: int = 1200,
        apply_viewport: bool | None = None,
        tool_timeout_s: float = 30.0,
        navigation_timeout_ms: int = 60000,
    ) -> None:
        self._transport = transport
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.click_timeout_ms = click_timeout_ms
        self.network_idle_ms = network_idle_ms
        self.tool_timeout_s = tool_timeout_s
        self.navigation_timeout_ms = navigation_timeout_ms
        # Resizing a real profile's window is intrusive; only do it for disposable browsers
        # unless the user asked for it.
        self.apply_viewport = (
            apply_viewport
            if apply_viewport is not None
            else transport.capabilities.isolated_profile
        )
        self._connected = False

    @property
    def transport(self) -> BridgeTransport:
        return self._transport

    @property
    def capabilities(self) -> BrowserCapabilities:
        return self._transport.capabilities

    # -- lifecycle -----------------------------------------------------

    async def connect(self) -> None:
        await self._transport.open()
        try:
            if self.apply_viewport:
                try:
                    await self._transport.set_viewport(self.viewport_width, self.viewport_height)
                except BridgeUnsupportedError:
                    pass
        except BaseException:
            await self._transport.close()
            raise
        self._connected = True
        logger.info(f"{self._transport.name} bridge connected")

    async def disconnect(self) -> None:
        try:
            await self._transport.close()
        except Exception as e:
            logger.warning(f"{self._transport.name}: error on disconnect: {e}")
        self._connected = False

    async def __aenter__(self) -> "BridgeBrowserClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()

    def is_page_alive(self) -> bool:
        return self._connected and self._transport.page_alive()

    def is_browser_alive(self) -> bool:
        return self._connected and self._transport.connection_alive()

    async def recover_page(self) -> None:
        await self._transport.new_tab("about:blank")

    async def reconnect(self) -> None:
        await self.disconnect()
        await self.connect()

    # -- evaluation ----------------------------------------------------

    async def _run(self, function_source: str, timeout_s: float | None = None) -> Any:
        """Run a JS function through the transport (no envelope)."""
        return await self._transport.evaluate(function_source, timeout_s or self.tool_timeout_s)

    async def evaluate(self, expression: str) -> JsValue:
        """Evaluate a synchronous expression; see ``BrowserClient.evaluate``."""
        raw = await self._run(js.function_from_expression(wrap_expression(expression)))
        return decode_result(raw)

    # -- navigation and DOM -------------------------------------------

    async def navigate(self, url: str, wait_until: str = "networkidle") -> str:
        reported = await self._transport.navigate(url, self.navigation_timeout_ms)
        if wait_until in ("load", "networkidle"):
            await self._run(js.wait_ready_state(15000), 20)
        if wait_until == "networkidle":
            await self.wait_for_network_idle(self.network_idle_ms)
        current = await self._run(js.current_url())
        return current if isinstance(current, str) and current else reported

    async def query_selector(self, selector: str) -> dict[str, Any] | None:
        info = await self._run(js.query_selector_info(selector))
        return info if isinstance(info, dict) else None

    async def query_selector_all(self, selector: str) -> list[dict[str, Any]]:
        items = await self._run(js.query_selector_all_info(selector))
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    async def click(self, selector: str) -> None:
        await asyncio.sleep(pre_action_delay())
        rect = await self._run(js.element_center(selector))
        if not isinstance(rect, dict):
            raise BridgeToolError("click", f"element not found or not visible: {selector}")
        if self.capabilities.trusted_click and isinstance(self._transport, TrustedInputTransport):
            await self._transport.click_at(float(rect["x"]), float(rect["y"]))
            return
        clicked = await self._run(js.synthetic_click(selector))
        if clicked is not True:
            raise BridgeToolError("click", f"element disappeared before click: {selector}")

    async def type_text(self, selector: str, text: str, delay: int = 50) -> None:
        await self.click(selector)
        await self._run(js.clear_input(selector))
        trusted: TrustedInputTransport | None = None
        if self.capabilities.trusted_input and isinstance(self._transport, TrustedInputTransport):
            trusted = self._transport
        for char in text:
            if trusted is not None:
                await trusted.type_into_focused(char)
            else:
                await self._run(js.append_text(selector, char))
            await asyncio.sleep(human_typing_delay(delay) / 1000)

    async def press_key(self, key: str) -> None:
        await asyncio.sleep(pre_action_delay())
        await self._transport.press_key(key)

    async def screenshot(self, output_path: Path, full_page: bool = True) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return await self._transport.screenshot(output_path.resolve(), full_page)

    async def get_html(self) -> str:
        html = await self._run(js.document_html())
        return html if isinstance(html, str) else ""

    async def wait_for_selector(
        self, selector: str, timeout: int = 5000, visible: bool = True
    ) -> bool:
        found = await self._run(
            js.wait_for_selector(selector, timeout, visible), timeout / 1000 + 5
        )
        return found is True

    async def wait_for_network_idle(self, timeout: int = 2000) -> None:
        await self._run(js.wait_network_idle(timeout, 500), timeout / 1000 + 5)

    async def get_element_text(self, selector: str) -> str | None:
        text = await self._run(js.element_text(selector))
        return text if isinstance(text, str) else None

    async def get_element_attribute(self, selector: str, attribute: str) -> str | None:
        value = await self._run(js.element_attribute(selector, attribute))
        return value if isinstance(value, str) else None

    # -- identity (gated by capabilities; never raise) -----------------

    async def set_user_agent(self, ua: str) -> None:
        if not self.capabilities.user_agent_override:
            logger.info(f"{self._transport.name}: user-agent override skipped (real profile)")
            return
        await self._transport.set_user_agent(ua)

    async def set_proxy(self, proxy_url: str) -> None:
        if not self.capabilities.proxy:
            logger.info(f"{self._transport.name}: proxy switch skipped (not supported)")
            return
        await self._transport.set_proxy(proxy_url)

    async def clear_cookies(self) -> None:
        if not self.capabilities.clear_cookies:
            logger.info(f"{self._transport.name}: cookie clearing skipped (real profile)")
            return
        await self._transport.clear_cookies()
