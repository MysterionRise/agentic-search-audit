"""Bridge backends: drive a real, already-running Chrome through a local bridge.

Transports: ``chrome_devtools_mcp`` (Google's MCP server), ``kimi_webbridge`` (Moonshot's
local daemon) and ``playwright_mcp`` (experimental). One ``BridgeBrowserClient``
implements the ``BrowserClient`` protocol over any of them.
"""

import logging

from ...core.types import BrowserBackend, RunConfig
from .client import BridgeBrowserClient
from .transport import (
    BridgeConnectionError,
    BridgeEnvironmentError,
    BridgeError,
    BridgeNotReadyError,
    BridgePageGoneError,
    BridgeTimeoutError,
    BridgeToolError,
    BridgeTransport,
    BridgeUnsupportedError,
    TrustedInputTransport,
)

logger = logging.getLogger(__name__)

__all__ = [
    "BridgeBrowserClient",
    "BridgeConnectionError",
    "BridgeEnvironmentError",
    "BridgeError",
    "BridgeNotReadyError",
    "BridgePageGoneError",
    "BridgeTimeoutError",
    "BridgeToolError",
    "BridgeTransport",
    "BridgeUnsupportedError",
    "TrustedInputTransport",
    "build_bridge_client",
]


def build_bridge_client(config: RunConfig, locale: str = "en-US") -> BridgeBrowserClient:
    """Build the bridge client selected by ``config.browser_backend``."""
    bridge = config.bridge
    backend = config.browser_backend
    transport: BridgeTransport

    if backend == BrowserBackend.CHROME_DEVTOOLS_MCP:
        from .chrome_devtools_mcp import ChromeDevtoolsMcpTransport

        transport = ChromeDevtoolsMcpTransport(
            mode=bridge.mode,
            browser_url=bridge.browser_url,
            headless=config.headless,
            proxy_url=config.proxy_url,
            viewport=(config.viewport_width, config.viewport_height),
            channel=bridge.chrome_channel,
            server_command=bridge.server_command,
            server_args=bridge.server_args,
            extra_server_args=bridge.extra_server_args,
            connect_timeout_s=bridge.connect_timeout_s,
            tool_timeout_s=bridge.tool_timeout_s,
            allow_profile_mutations=bridge.allow_profile_mutations,
            experimental_vision_click=bridge.experimental_vision_click,
            close_tabs_on_disconnect=bridge.close_tabs_on_disconnect,
        )
    elif backend == BrowserBackend.KIMI_WEBBRIDGE:
        from .kimi_webbridge import KimiWebBridgeTransport

        transport = KimiWebBridgeTransport(
            daemon_url=bridge.daemon_url,
            session_name=bridge.session_name,
            tab_group_title=bridge.tab_group_title,
            request_timeout_s=bridge.tool_timeout_s,
            allow_profile_mutations=bridge.allow_profile_mutations,
            close_tabs_on_disconnect=bridge.close_tabs_on_disconnect,
        )
    elif backend == BrowserBackend.PLAYWRIGHT_MCP:
        from .playwright_mcp import PlaywrightMcpTransport

        logger.warning(
            "playwright_mcp bridge is experimental and has not been exercised end to end"
        )
        transport = PlaywrightMcpTransport(
            mode=bridge.mode,
            cdp_endpoint=bridge.browser_url,
            headless=config.headless,
            server_command=bridge.server_command,
            server_args=bridge.server_args,
            extra_server_args=bridge.extra_server_args,
            connect_timeout_s=bridge.connect_timeout_s,
            tool_timeout_s=bridge.tool_timeout_s,
            allow_profile_mutations=bridge.allow_profile_mutations,
        )
    else:
        raise ValueError(f"{backend} is not a bridge backend")

    logger.debug(f"Bridge locale {locale!r} is inherited from the real browser profile")
    return BridgeBrowserClient(
        transport,
        viewport_width=config.viewport_width,
        viewport_height=config.viewport_height,
        click_timeout_ms=config.click_timeout_ms,
        network_idle_ms=config.network_idle_ms,
        apply_viewport=bridge.apply_viewport,
        tool_timeout_s=bridge.tool_timeout_s,
    )
