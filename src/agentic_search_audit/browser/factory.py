"""Factory for creating browser clients based on configuration."""

import logging

from ..core.types import BrowserBackend, BrowserClient, RunConfig

logger = logging.getLogger(__name__)


def create_browser_client(config: RunConfig, locale: str = "en-US") -> BrowserClient:
    """Create a browser client based on the configured backend.

    Args:
        config: Runtime configuration with browser backend settings.
        locale: BCP-47 locale code from site config (e.g. 'fr-FR').

    Returns:
        A browser client implementing the ``BrowserClient`` protocol.

    Raises:
        ImportError: If optional dependencies for the chosen backend are missing.
        ValueError: If the backend is unknown or misconfigured.
    """
    backend = config.browser_backend

    if backend == BrowserBackend.PLAYWRIGHT:
        from .playwright_client import PlaywrightBrowserClient

        logger.info("Using Playwright browser backend (locale=%s)", locale)
        return PlaywrightBrowserClient(
            headless=config.headless,
            viewport_width=config.viewport_width,
            viewport_height=config.viewport_height,
            click_timeout_ms=config.click_timeout_ms,
            locale=locale,
            proxy_url=config.proxy_url,
        )

    if backend == BrowserBackend.CDP:
        from .cdp_client import CDPBrowserClient

        endpoint = config.cdp_endpoint
        if not endpoint and config.browserbase_api_key:
            from .browserbase import get_browserbase_endpoint

            endpoint = get_browserbase_endpoint(
                api_key=config.browserbase_api_key,
                project_id=config.browserbase_project_id,
            )
        if not endpoint:
            raise ValueError("CDP backend requires either 'cdp_endpoint' or 'browserbase_api_key'")

        if config.proxy_url:
            logger.warning(
                "Proxy URL is set but CDP backend connects to an external browser. "
                "Ensure the external browser was launched with proxy settings."
            )
        logger.info("Using CDP browser backend (endpoint: %s, locale=%s)", endpoint, locale)
        return CDPBrowserClient(
            cdp_endpoint=endpoint,
            viewport_width=config.viewport_width,
            viewport_height=config.viewport_height,
            click_timeout_ms=config.click_timeout_ms,
            locale=locale,
        )

    if backend == BrowserBackend.UNDETECTED:
        try:
            import undetected_chromedriver  # type: ignore[import-not-found,import-untyped]  # noqa: F401
        except ImportError:
            raise ImportError(
                "undetected-chromedriver not installed. "
                "Install with: pip install 'agentic-search-audit[undetected]'"
            )

        from .undetected_client import UndetectedBrowserClient

        logger.info("Using undetected-chromedriver browser backend (locale=%s)", locale)
        return UndetectedBrowserClient(
            headless=config.headless,
            viewport_width=config.viewport_width,
            viewport_height=config.viewport_height,
            click_timeout_ms=config.click_timeout_ms,
            locale=locale,
            proxy_url=config.proxy_url,
        )

    raise ValueError(f"Unknown browser backend: {backend}")
