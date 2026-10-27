"""A scripted BridgeTransport for unit tests of BridgeBrowserClient."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentic_search_audit.core.types import BrowserCapabilities


class FakeTransport:
    """Records every primitive call; ``evaluate`` answers through ``evaluate_handler``."""

    name = "fake"

    def __init__(
        self,
        capabilities: BrowserCapabilities | None = None,
        evaluate_handler: Callable[[str], Any] | None = None,
    ) -> None:
        self._capabilities = capabilities or BrowserCapabilities()
        self.evaluate_handler = evaluate_handler or (lambda source: None)
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.scripts: list[str] = []
        self.page_alive_value = True
        self.connection_alive_value = True
        self.opened = 0
        self.closed = 0

    @property
    def capabilities(self) -> BrowserCapabilities:
        return self._capabilities

    def _record(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    async def open(self) -> None:
        self.opened += 1
        self._record("open")

    async def close(self) -> None:
        self.closed += 1
        self._record("close")

    async def navigate(self, url: str, timeout_ms: int) -> str:
        self._record("navigate", url, timeout_ms)
        return url

    async def evaluate(self, function_source: str, timeout_s: float) -> Any:
        self._record("evaluate", function_source, timeout_s)
        self.scripts.append(function_source)
        return self.evaluate_handler(function_source)

    async def press_key(self, key: str) -> None:
        self._record("press_key", key)

    async def screenshot(self, output_path: Path, full_page: bool) -> Path:
        self._record("screenshot", output_path, full_page)
        output_path.write_bytes(b"png")
        return output_path

    async def set_viewport(self, width: int, height: int) -> None:
        self._record("set_viewport", width, height)

    async def new_tab(self, url: str) -> None:
        self._record("new_tab", url)
        self.page_alive_value = True

    def page_alive(self) -> bool:
        return self.page_alive_value

    def connection_alive(self) -> bool:
        return self.connection_alive_value

    async def snapshot(self) -> str:
        self._record("snapshot")
        return "- document"

    async def set_user_agent(self, user_agent: str) -> None:
        self._record("set_user_agent", user_agent)

    async def clear_cookies(self) -> None:
        self._record("clear_cookies")

    async def set_proxy(self, proxy_url: str) -> None:
        self._record("set_proxy", proxy_url)

    # TrustedInputTransport
    async def type_into_focused(self, text: str) -> None:
        self._record("type_into_focused", text)

    async def click_at(self, x: float, y: float) -> None:
        self._record("click_at", x, y)
