"""Browser error types and classification for retry decisions."""

from enum import Enum
from typing import Literal

JsErrorKind = Literal[
    "script",  # the expression threw
    "syntax",  # the expression did not parse
    "serialization",  # the result could not be JSON-serialised (cyclic, etc.)
    "decode",  # the backend returned something other than the JSON envelope
    "payload_too_large",  # the serialised result exceeded the size cap
    "unsupported_promise",  # the expression returned a thenable
]


class BrowserScriptError(RuntimeError):
    """A JavaScript expression passed to ``BrowserClient.evaluate`` failed.

    The page and browser are still alive; the script itself is the problem. It is
    classified as ``PERMANENT`` (not retried) by ``classify_error``.
    """

    def __init__(
        self,
        kind: JsErrorKind | str,
        message: str,
        *,
        name: str = "Error",
        stack: str | None = None,
    ) -> None:
        self.kind = kind
        self.name = name
        self.message = message
        self.stack = stack
        prefix = f"{name}: " if name and name != "Error" else ""
        super().__init__(f"[{kind}] {prefix}{message}")


class BrowserErrorKind(str, Enum):
    """Classifies browser errors for retry decisions."""

    TIMEOUT = "timeout"
    PAGE_CLOSED = "page_closed"
    BROWSER_DEAD = "browser_dead"
    NOT_CONNECTED = "not_connected"
    TRANSIENT = "transient"
    PERMANENT = "permanent"


def classify_error(exc: BaseException) -> BrowserErrorKind:
    """Classify a browser exception into an error kind.

    Checks ``BrowserScriptError`` first, then Playwright and Selenium exception
    types, falling back to message parsing for closed-state errors.

    Args:
        exc: The exception to classify.

    Returns:
        The corresponding BrowserErrorKind.
    """
    # A failing script is a bug in our JavaScript, never a transient browser state.
    if isinstance(exc, BrowserScriptError):
        return BrowserErrorKind.PERMANENT

    # Import lazily to avoid hard dependency at module level
    try:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    except ImportError:
        return BrowserErrorKind.PERMANENT

    if isinstance(exc, PlaywrightTimeoutError):
        return BrowserErrorKind.TIMEOUT

    if isinstance(exc, PlaywrightError):
        msg = str(exc).lower()
        if "browser has been closed" in msg or "browser.newcontext" in msg:
            return BrowserErrorKind.BROWSER_DEAD
        if "context has been closed" in msg or "context.newpage" in msg:
            return BrowserErrorKind.BROWSER_DEAD
        if "page has been closed" in msg or "page closed" in msg:
            return BrowserErrorKind.PAGE_CLOSED
        if "target page, context or browser has been closed" in msg:
            return BrowserErrorKind.BROWSER_DEAD
        if "navigation" in msg or "net::" in msg:
            return BrowserErrorKind.TRANSIENT
        return BrowserErrorKind.PERMANENT

    if isinstance(exc, RuntimeError) and "not connected" in str(exc).lower():
        return BrowserErrorKind.NOT_CONNECTED

    # Selenium / undetected-chromedriver exceptions
    try:
        from selenium.common.exceptions import (  # type: ignore[import-not-found]
            InvalidSessionIdException,
            NoSuchWindowException,
            SessionNotCreatedException,
            TimeoutException,
            WebDriverException,
        )
    except ImportError:
        return BrowserErrorKind.PERMANENT

    if isinstance(exc, TimeoutException):
        return BrowserErrorKind.TIMEOUT
    if isinstance(exc, InvalidSessionIdException | SessionNotCreatedException):
        return BrowserErrorKind.BROWSER_DEAD
    if isinstance(exc, NoSuchWindowException):
        return BrowserErrorKind.PAGE_CLOSED
    if isinstance(exc, WebDriverException):
        msg = str(exc).lower()
        if "chrome not reachable" in msg or "unable to connect" in msg:
            return BrowserErrorKind.BROWSER_DEAD
        if "no such window" in msg or "window was already closed" in msg:
            return BrowserErrorKind.PAGE_CLOSED
        if "net::" in msg or "timeout" in msg or "connection" in msg:
            return BrowserErrorKind.TRANSIENT
        return BrowserErrorKind.PERMANENT

    return BrowserErrorKind.PERMANENT


def is_retryable(kind: BrowserErrorKind) -> bool:
    """Return True if the error kind is worth retrying.

    Args:
        kind: The classified error kind.

    Returns:
        True for TIMEOUT, PAGE_CLOSED, BROWSER_DEAD, and TRANSIENT.
    """
    return kind in {
        BrowserErrorKind.TIMEOUT,
        BrowserErrorKind.PAGE_CLOSED,
        BrowserErrorKind.BROWSER_DEAD,
        BrowserErrorKind.TRANSIENT,
    }
