"""Browser automation module."""

from .errors import BrowserErrorKind, classify_error, is_retryable
from .factory import create_browser_client
from .playwright_client import PlaywrightBrowserClient

__all__ = [
    "BrowserErrorKind",
    "PlaywrightBrowserClient",
    "classify_error",
    "create_browser_client",
    "is_retryable",
]

# Optional backends — available only when their dependencies are installed.
try:
    from .cdp_client import CDPBrowserClient  # noqa: F401

    __all__.append("CDPBrowserClient")
except ImportError:
    pass

try:
    from .undetected_client import UndetectedBrowserClient  # noqa: F401

    __all__.append("UndetectedBrowserClient")
except ImportError:
    pass
