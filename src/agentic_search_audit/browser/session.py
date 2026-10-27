"""Per-run browser state: identity rotation, cookie clearing and recovery.

``BrowserSession`` owns the user-agent and proxy rotators and the cookie-clearing
counter, and consults the client's ``BrowserCapabilities`` before each step: a
backend driving a real, logged-in Chrome profile reports no UA override, no proxy
switching and no cookie clearing, and those steps are skipped (logged once) instead
of raising or mutating the user's profile.
"""

import logging

from ..core.types import (
    BrowserCapabilities,
    BrowserClient,
    ProxyRotationStrategy,
    RunConfig,
    get_capabilities,
)
from .errors import BrowserErrorKind
from .proxy import ProxyRotator
from .stealth import UserAgentRotator

logger = logging.getLogger(__name__)


class BrowserSession:
    """Wraps a ``BrowserClient`` with the per-query rotation and recovery policy."""

    def __init__(self, client: BrowserClient, run_config: RunConfig) -> None:
        self.client = client
        self.run = run_config
        self.capabilities: BrowserCapabilities = get_capabilities(client)
        self._ua_rotator = UserAgentRotator()
        self._proxy_rotator = ProxyRotator(
            strategy=run_config.proxy_rotation_strategy,
            proxy_list=run_config.proxy_list,
        )
        self._current_proxy: str | None = run_config.proxy_url
        self._queries_since_cookie_clear = 0
        self._skipped: set[str] = set()
        #: True when the next query must (re)load the site before searching.
        self.needs_navigation = True

    def _allowed(self, feature: str, ok: bool, why: str) -> bool:
        if ok:
            return True
        if feature not in self._skipped:
            logger.info(f"Skipping {feature}: {why}")
            self._skipped.add(feature)
        return False

    async def rotate_for_query(self, index: int) -> bool:
        """Apply the per-query identity policy. Returns True if browser state changed.

        Exceptions propagate so the retry loop can classify them (a challenge raised
        while re-navigating must not be logged away as "rotation failed").
        """
        changed = False

        if self.run.ua_rotation_strategy == ProxyRotationStrategy.PER_QUERY and self._allowed(
            "user-agent rotation",
            self.capabilities.user_agent_override,
            "this backend cannot override the user agent",
        ):
            await self.client.set_user_agent(self._ua_rotator.next())
            changed = True

        next_proxy = self._proxy_rotator.next_proxy()
        if (
            next_proxy
            and next_proxy != self._current_proxy
            and self._allowed(
                "proxy rotation", self.capabilities.proxy, "this backend cannot switch proxies"
            )
        ):
            await self.client.set_proxy(next_proxy)
            self._current_proxy = next_proxy
            changed = True

        if self.run.cookie_clear_interval > 0:
            self._queries_since_cookie_clear += 1
            if self._queries_since_cookie_clear >= self.run.cookie_clear_interval:
                self._queries_since_cookie_clear = 0
                if await self.clear_cookies_if_allowed("periodic"):
                    changed = True

        if changed:
            self.needs_navigation = True
        return changed

    async def clear_cookies_if_allowed(self, reason: str) -> bool:
        """Clear cookies when the backend owns a disposable profile. Never raises."""
        if not self._allowed(
            "cookie clearing",
            self.capabilities.clear_cookies and self.capabilities.isolated_profile,
            "this backend drives a real profile or cannot clear cookies",
        ):
            return False
        try:
            await self.client.clear_cookies()
        except Exception as e:
            logger.warning(f"Cookie clearing ({reason}) failed: {e}")
            return False
        logger.debug(f"Cookies cleared ({reason})")
        self.needs_navigation = True
        return True

    async def ensure_alive(self) -> None:
        """Recover the page or reconnect the browser if the page is dead."""
        if self.client.is_page_alive():
            return
        logger.warning("Page is dead before query -- recovering")
        if self.client.is_browser_alive():
            await self.client.recover_page()
        else:
            await self.client.reconnect()
        self.needs_navigation = True

    async def recover(self, kind: BrowserErrorKind) -> None:
        """Recover from a classified browser error (page recovery or full reconnect)."""
        if kind in (BrowserErrorKind.BROWSER_DEAD, BrowserErrorKind.NOT_CONNECTED):
            await self.client.reconnect()
        elif kind in (
            BrowserErrorKind.PAGE_CLOSED,
            BrowserErrorKind.TIMEOUT,
            BrowserErrorKind.TRANSIENT,
        ):
            if self.client.is_browser_alive():
                await self.client.recover_page()
            else:
                await self.client.reconnect()
        self.needs_navigation = True
