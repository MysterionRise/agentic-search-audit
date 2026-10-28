"""Shared plumbing for bridges that are MCP servers spoken to over stdio.

Salvaged from the old chrome-devtools-mcp client: the stdio session setup and the
markdown-with-a-JSON-block response parsing, now returning decoded values.
"""

import json
import logging
import re
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import timedelta
from typing import Any, NoReturn, Protocol

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError

from .transport import (
    BridgeConnectionError,
    BridgeEnvironmentError,
    BridgeNotReadyError,
    BridgePageGoneError,
    BridgeTimeoutError,
    BridgeToolError,
)

logger = logging.getLogger(__name__)


class McpSessionLike(Protocol):
    """The slice of ``mcp.ClientSession`` the transports use (fakes implement this)."""

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        read_timeout_seconds: timedelta | None = None,
    ) -> Any: ...


#: (command, args, env, init_timeout_s) -> context manager yielding an initialised session.
#: Entered and exited in the SAME task: the SDK's context managers own anyio cancel
#: scopes, which cannot be exited from another task (so never ``asyncio.wait_for`` them).
SessionFactory = Callable[
    [str, list[str], dict[str, str] | None, float],
    AbstractAsyncContextManager[McpSessionLike],
]

_PAGE_GONE_MARKERS = (
    "has been closed",
    "target closed",
    "no page selected",
    "page not found",
    "detached frame",
    "session closed",
    "no such page",
)
_NOT_READY_MARKERS = ("could not connect", "failed to connect", "could not find chrome")
_TIMEOUT_MARKERS = ("timed out", "timeout waiting", "request timeout")


@asynccontextmanager
async def stdio_session(
    command: str, args: list[str], env: dict[str, str] | None, init_timeout_s: float
) -> AsyncIterator[McpSessionLike]:
    """Spawn an MCP server over stdio and yield an initialised session."""
    params = StdioServerParameters(command=command, args=args, env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            with anyio.fail_after(init_timeout_s):
                await session.initialize()
            yield session


def result_is_error(result: Any) -> bool:
    """``CallToolResult.isError`` (mcp 1.x) or ``is_error`` (mcp 2.x)."""
    return bool(getattr(result, "isError", None) or getattr(result, "is_error", None))


def result_text(result: Any) -> str:
    """Concatenate the text content items of a tool result."""
    parts = []
    for item in getattr(result, "content", None) or []:
        if getattr(item, "type", None) == "text":
            parts.append(str(getattr(item, "text", "")))
    return "\n".join(parts)


def parse_json_block(text: str, *, tool: str = "evaluate_script") -> Any:
    """Decode the first ```json fenced block of a tool response.

    ``JSON.stringify(undefined)`` renders the literal ``undefined``, which becomes None.
    """
    match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if not match:
        raise BridgeToolError(tool, f"no JSON block in response: {text[:200]!r}")
    body = match.group(1).strip()
    if body == "undefined" or body == "":
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise BridgeToolError(tool, f"JSON block is not valid JSON: {body[:200]!r}") from exc


def parse_selected_page_id(text: str) -> int | None:
    """Read the ``<id>: ... [selected]`` line of a ``## Pages`` listing."""
    match = re.search(r"^\s*(\d+):.*\[selected\]", text, re.MULTILINE)
    return int(match.group(1)) if match else None


class McpStdioTransportBase:
    """Lifecycle and error handling for stdio MCP bridges."""

    name = "mcp"
    not_ready_help = "The MCP server could not reach a browser."

    def __init__(
        self,
        *,
        server_command: str,
        server_args: list[str],
        env: dict[str, str] | None = None,
        connect_timeout_s: float = 60.0,
        tool_timeout_s: float = 30.0,
        session_factory: SessionFactory | None = None,
    ) -> None:
        self.server_command = server_command
        self.server_args = server_args
        self._env = env
        self.connect_timeout_s = connect_timeout_s
        self.tool_timeout_s = tool_timeout_s
        self._session_factory = session_factory
        self._session: McpSessionLike | None = None
        self._session_cm: AbstractAsyncContextManager[McpSessionLike] | None = None
        self._connection_broken = False
        self._page_gone = False

    async def _start(self) -> None:
        factory = self._session_factory or stdio_session
        cm = factory(self.server_command, self.server_args, self._env, self.connect_timeout_s)
        logger.info(f"Starting {self.name}: {self.server_command} {' '.join(self.server_args)}")
        try:
            self._session = await cm.__aenter__()
        except TimeoutError as exc:
            raise BridgeTimeoutError(
                f"{self.name} did not initialise within {self.connect_timeout_s:.0f}s"
            ) from exc
        except FileNotFoundError as exc:
            raise BridgeEnvironmentError(
                f"cannot start {self.name}: '{self.server_command}' not found ({exc})"
            ) from exc
        self._session_cm = cm
        self._connection_broken = False

    async def _stop(self) -> None:
        cm, self._session_cm, self._session = self._session_cm, None, None
        if cm is not None:
            try:
                await cm.__aexit__(None, None, None)
            except Exception as e:  # the process is going away anyway
                logger.debug(f"{self.name}: error while stopping the server: {e}")

    async def _call_raw(
        self, name: str, arguments: dict[str, Any], timeout_s: float | None = None
    ) -> Any:
        """Call a tool and return the raw result; errors become bridge exceptions."""
        if self._session is None:
            raise BridgeConnectionError(f"{self.name}: not connected")
        timeout = timeout_s or self.tool_timeout_s
        logger.debug(f"{self.name}: {name} {arguments}")
        try:
            # The SDK's own timeout keeps the call in this task (see SessionFactory).
            result = await self._session.call_tool(
                name, arguments, read_timeout_seconds=timedelta(seconds=timeout)
            )
        except McpError as exc:
            message = str(exc)
            if any(marker in message.lower() for marker in _TIMEOUT_MARKERS):
                raise BridgeTimeoutError(f"{name} timed out after {timeout:.0f}s") from exc
            self._raise_for_message(name, message)
        except (anyio.BrokenResourceError, anyio.ClosedResourceError, OSError) as exc:
            self._connection_broken = True
            raise BridgeConnectionError(
                f"{self.name}: connection lost during {name}: {exc}"
            ) from exc
        if result_is_error(result):
            self._raise_for_message(name, result_text(result))
        return result

    async def _call(
        self, name: str, arguments: dict[str, Any], timeout_s: float | None = None
    ) -> str:
        """Call a tool and return its text."""
        return result_text(await self._call_raw(name, arguments, timeout_s))

    def _raise_for_message(self, name: str, message: str) -> NoReturn:
        lower = message.lower()
        if any(marker in lower for marker in _PAGE_GONE_MARKERS):
            self._page_gone = True
            raise BridgePageGoneError(f"{name}: {message}")
        if any(marker in lower for marker in _NOT_READY_MARKERS):
            raise BridgeNotReadyError(f"{message}\n{self.not_ready_help}")
        raise BridgeToolError(name, message)

    def connection_alive(self) -> bool:
        return self._session is not None and not self._connection_broken
