"""Error classification for Playwright browser automation."""

from enum import Enum


class BrowserErrorKind(str, Enum):
    """Classifies browser errors for retry decisions."""

    TIMEOUT = "timeout"
    PAGE_CLOSED = "page_closed"
    BROWSER_DEAD = "browser_dead"
    NOT_CONNECTED = "not_connected"
    TRANSIENT = "transient"
    PERMANENT = "permanent"


def classify_error(exc: BaseException) -> BrowserErrorKind:
    """Classify a Playwright exception into an error kind.

    Uses isinstance checks against Playwright exception types first,
    then falls back to message parsing for closed-state errors.

    Args:
        exc: The exception to classify.

    Returns:
        The corresponding BrowserErrorKind.
    """
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
