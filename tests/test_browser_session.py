"""Tests for BrowserSession: capability-gated rotation and recovery."""

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentic_search_audit.browser.errors import BrowserErrorKind
from agentic_search_audit.browser.session import BrowserSession
from agentic_search_audit.core.types import BrowserCapabilities, ProxyRotationStrategy, RunConfig

pytestmark = pytest.mark.unit


def _client(caps: BrowserCapabilities | None = None, **attrs: Any) -> MagicMock:
    client = MagicMock()
    if caps is not None:
        client.capabilities = caps
    else:
        del client.capabilities  # a client without the attribute is treated as all-capable
    client.set_user_agent = AsyncMock()
    client.set_proxy = AsyncMock()
    client.clear_cookies = AsyncMock()
    client.recover_page = AsyncMock()
    client.reconnect = AsyncMock()
    client.is_page_alive = MagicMock(return_value=True)
    client.is_browser_alive = MagicMock(return_value=True)
    for key, value in attrs.items():
        setattr(client, key, value)
    return client


async def test_client_without_capabilities_is_all_capable() -> None:
    client = _client()
    session = BrowserSession(
        client, RunConfig(ua_rotation_strategy=ProxyRotationStrategy.PER_QUERY)
    )
    assert session.capabilities == BrowserCapabilities()
    assert await session.rotate_for_query(1) is True
    client.set_user_agent.assert_awaited_once()
    assert session.needs_navigation is True


async def test_ua_rotation_is_skipped_by_default_strategy() -> None:
    client = _client()
    session = BrowserSession(client, RunConfig())
    session.needs_navigation = False
    assert await session.rotate_for_query(1) is False
    client.set_user_agent.assert_not_awaited()
    assert session.needs_navigation is False


async def test_ua_rotation_skipped_when_backend_cannot_override(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _client(BrowserCapabilities(user_agent_override=False))
    session = BrowserSession(
        client, RunConfig(ua_rotation_strategy=ProxyRotationStrategy.PER_QUERY)
    )
    with caplog.at_level(logging.INFO, logger="agentic_search_audit.browser.session"):
        for index in range(1, 4):
            assert await session.rotate_for_query(index) is False
    client.set_user_agent.assert_not_awaited()
    skips = [r for r in caplog.records if "Skipping user-agent rotation" in r.getMessage()]
    assert len(skips) == 1  # logged once, not per query


async def test_cookie_clearing_skipped_on_real_profile() -> None:
    client = _client(BrowserCapabilities(clear_cookies=False, isolated_profile=False))
    session = BrowserSession(client, RunConfig(cookie_clear_interval=1))
    assert await session.rotate_for_query(1) is False
    assert await session.clear_cookies_if_allowed("challenge") is False
    client.clear_cookies.assert_not_awaited()


async def test_cookie_clearing_every_n_queries_on_disposable_profile() -> None:
    client = _client()
    session = BrowserSession(client, RunConfig(cookie_clear_interval=2))
    assert await session.rotate_for_query(1) is False
    assert await session.rotate_for_query(2) is True
    assert await session.rotate_for_query(3) is False
    assert await session.rotate_for_query(4) is True
    assert client.clear_cookies.await_count == 2


async def test_cookie_clearing_failure_is_swallowed() -> None:
    client = _client(clear_cookies=AsyncMock(side_effect=RuntimeError("nope")))
    session = BrowserSession(client, RunConfig())
    assert await session.clear_cookies_if_allowed("challenge") is False


async def test_per_site_proxy_is_set_once() -> None:
    client = _client()
    config = RunConfig(
        proxy_rotation_strategy=ProxyRotationStrategy.PER_SITE,
        proxy_list=["http://proxy-a:3128", "http://proxy-b:3128"],
    )
    session = BrowserSession(client, config)
    first = await session.rotate_for_query(1)
    second = await session.rotate_for_query(2)
    assert first is True and second is False
    client.set_proxy.assert_awaited_once()


async def test_proxy_rotation_skipped_without_capability() -> None:
    client = _client(BrowserCapabilities(proxy=False))
    config = RunConfig(
        proxy_rotation_strategy=ProxyRotationStrategy.PER_QUERY,
        proxy_list=["http://proxy-a:3128", "http://proxy-b:3128"],
    )
    session = BrowserSession(client, config)
    assert await session.rotate_for_query(1) is False
    client.set_proxy.assert_not_awaited()


async def test_ensure_alive_recovers_dead_page() -> None:
    client = _client(is_page_alive=MagicMock(return_value=False))
    session = BrowserSession(client, RunConfig())
    session.needs_navigation = False
    await session.ensure_alive()
    client.recover_page.assert_awaited_once()
    client.reconnect.assert_not_awaited()
    assert session.needs_navigation is True


async def test_ensure_alive_reconnects_dead_browser() -> None:
    client = _client(
        is_page_alive=MagicMock(return_value=False),
        is_browser_alive=MagicMock(return_value=False),
    )
    session = BrowserSession(client, RunConfig())
    await session.ensure_alive()
    client.reconnect.assert_awaited_once()
    client.recover_page.assert_not_awaited()


@pytest.mark.parametrize(
    ("kind", "browser_alive", "expect_reconnect", "expect_recover"),
    [
        (BrowserErrorKind.BROWSER_DEAD, True, 1, 0),
        (BrowserErrorKind.NOT_CONNECTED, True, 1, 0),
        (BrowserErrorKind.PAGE_CLOSED, True, 0, 1),
        (BrowserErrorKind.PAGE_CLOSED, False, 1, 0),
        (BrowserErrorKind.TIMEOUT, True, 0, 1),
        (BrowserErrorKind.TRANSIENT, True, 0, 1),
        (BrowserErrorKind.PERMANENT, True, 0, 0),
    ],
)
async def test_recover(
    kind: BrowserErrorKind, browser_alive: bool, expect_reconnect: int, expect_recover: int
) -> None:
    client = _client(is_browser_alive=MagicMock(return_value=browser_alive))
    session = BrowserSession(client, RunConfig())
    session.needs_navigation = False
    await session.recover(kind)
    assert client.reconnect.await_count == expect_reconnect
    assert client.recover_page.await_count == expect_recover
    assert session.needs_navigation is True
