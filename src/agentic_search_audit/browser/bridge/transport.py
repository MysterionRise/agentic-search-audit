"""The minimal primitive set a bridge transport provides, and the bridge error types.

A *transport* talks to one bridge (chrome-devtools-mcp, Kimi WebBridge, Playwright MCP).
``BridgeBrowserClient`` implements the whole ``BrowserClient`` protocol on top of these
few primitives, so each new bridge is a small class.
"""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ...core.types import BrowserCapabilities


class BridgeError(RuntimeError):
    """Base class for bridge failures."""


class BridgeEnvironmentError(BridgeError):
    """Node too old, npx missing, daemon binary missing: fix the machine, then retry."""


class BridgeNotReadyError(BridgeError):
    """The bridge is installed but Chrome, the dialog or the extension is not ready."""


class BridgeConnectionError(BridgeError):
    """The server or daemon died or the stream closed (classified BROWSER_DEAD)."""


class BridgePageGoneError(BridgeError):
    """The tab this run owned was closed (classified PAGE_CLOSED)."""


class BridgeTimeoutError(BridgeError):
    """A tool call exceeded its timeout (classified TIMEOUT)."""


class BridgeToolError(BridgeError):
    """A tool call reported an error."""

    def __init__(self, tool: str, message: str, code: str | None = None) -> None:
        self.tool = tool
        self.code = code
        prefix = f"{tool} ({code})" if code else tool
        super().__init__(f"{prefix}: {message}")


class BridgeUnsupportedError(BridgeError):
    """The transport cannot do this (its capability flag is False)."""


@runtime_checkable
class BridgeTransport(Protocol):
    """What a bridge must provide. Everything else is JavaScript on top."""

    name: str

    @property
    def capabilities(self) -> BrowserCapabilities: ...

    async def open(self) -> None:
        """Start the server / verify the daemon and open ONE dedicated tab for this run."""
        ...

    async def close(self) -> None:
        """Close the tab(s) this run opened and stop the server. Never touch user tabs."""
        ...

    async def navigate(self, url: str, timeout_ms: int) -> str:
        """Load ``url`` in the run's tab; return the URL the transport reports."""
        ...

    async def evaluate(self, function_source: str, timeout_s: float) -> Any:
        """Run a JavaScript *function* (``() => {...}``, may be async) and return its
        JSON-decoded result (``undefined`` becomes None)."""
        ...

    async def press_key(self, key: str) -> None:
        """Press a key ("Enter", "Escape", "Backspace", "Tab" or a single character)."""
        ...

    async def screenshot(self, output_path: Path, full_page: bool) -> Path:
        """Write a PNG to ``output_path`` and return it."""
        ...

    async def set_viewport(self, width: int, height: int) -> None: ...

    async def new_tab(self, url: str) -> None:
        """Open a fresh tab for the run (page recovery) and make it current."""
        ...

    def page_alive(self) -> bool: ...

    def connection_alive(self) -> bool: ...

    async def snapshot(self) -> str:
        """Accessibility-tree text of the current page (used by the spike for token sizing)."""
        ...

    async def set_user_agent(self, user_agent: str) -> None: ...

    async def clear_cookies(self) -> None: ...

    async def set_proxy(self, proxy_url: str) -> None: ...


@runtime_checkable
class TrustedInputTransport(Protocol):
    """Optional: transports that can generate ``isTrusted`` input events."""

    async def type_into_focused(self, text: str) -> None:
        """Trusted keystrokes into the focused element."""
        ...

    async def click_at(self, x: float, y: float) -> None:
        """Trusted mouse click at viewport coordinates."""
        ...
