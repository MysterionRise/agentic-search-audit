"""Proxy rotation for IP diversity.

Wires up the existing ``RunConfig.proxy_rotation_strategy`` and
``RunConfig.proxy_list`` fields that were defined but never used.
"""

import logging
import random
from collections import deque

from ..core.types import ProxyRotationStrategy

logger = logging.getLogger(__name__)


class ProxyRotator:
    """Rotate proxies based on configured strategy.

    Strategies:
        NONE: Always returns None (no proxy).
        PER_SITE: Picks one random proxy at init and returns it for every call.
        PER_QUERY: Round-robin through the proxy list.
    """

    def __init__(
        self,
        strategy: ProxyRotationStrategy,
        proxy_list: list[str] | None = None,
    ) -> None:
        self._strategy = strategy
        self._proxy_list = list(proxy_list) if proxy_list else []
        self._fixed_proxy: str | None = None
        self._queue: deque[str] = deque()

        if strategy == ProxyRotationStrategy.PER_SITE and self._proxy_list:
            self._fixed_proxy = random.choice(self._proxy_list)
            logger.info("ProxyRotator PER_SITE: fixed proxy selected")
        elif strategy == ProxyRotationStrategy.PER_QUERY and self._proxy_list:
            shuffled = list(self._proxy_list)
            random.shuffle(shuffled)
            self._queue = deque(shuffled)
            logger.info(
                "ProxyRotator PER_QUERY: %d proxies in rotation pool",
                len(self._queue),
            )

    def next_proxy(self) -> str | None:
        """Return the next proxy URL based on the configured strategy.

        Returns:
            Proxy URL string or None if strategy is NONE.
        """
        if self._strategy == ProxyRotationStrategy.NONE:
            return None

        if self._strategy == ProxyRotationStrategy.PER_SITE:
            return self._fixed_proxy

        if self._strategy == ProxyRotationStrategy.PER_QUERY:
            if not self._proxy_list:
                return None
            if not self._queue:
                # Refill and reshuffle when exhausted
                shuffled = list(self._proxy_list)
                random.shuffle(shuffled)
                self._queue = deque(shuffled)
            return self._queue.popleft()

        return None
