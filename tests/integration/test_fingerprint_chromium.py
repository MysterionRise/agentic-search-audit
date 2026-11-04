"""The launched Playwright browser presents one consistent identity (marker: browser).

The user agent used to come from a pool of Chrome 129-133 strings on random operating
systems while the engine was Chromium 156 on the host OS, and playwright-stealth set
navigator.platform to "Win32" on every OS.
"""

import platform
import re
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.browser, pytest.mark.asyncio(loop_scope="module")]

NAVIGATOR_PLATFORMS = {"Darwin": "MacIntel", "Windows": "Win32", "Linux": "Linux x86_64"}
CLIENT_HINT_PLATFORMS = {"Darwin": '"macOS"', "Windows": '"Windows"', "Linux": '"Linux"'}


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def seen() -> AsyncIterator[dict[str, Any]]:
    pytest.importorskip("playwright.async_api")
    from agentic_search_audit.browser.playwright_client import PlaywrightBrowserClient

    client = PlaywrightBrowserClient(headless=True)
    try:
        await client.connect()
    except Exception as exc:  # browser binary missing
        pytest.skip(f"Chromium not available: {exc}")
    headers: dict[str, str] = {}

    async def capture(route: Any) -> None:
        headers.update(route.request.headers)
        await route.fulfill(status=200, content_type="text/html", body="<html></html>")

    try:
        await client._page.route("https://fingerprint.test/**", capture)
        await client._page.goto("https://fingerprint.test/")
        page = await client.evaluate(
            "({ua: navigator.userAgent, platform: navigator.platform,"
            " brands: navigator.userAgentData.brands, chPlatform: navigator.userAgentData.platform})"
        )
        yield {"engine": client._browser.version, "headers": headers, "page": page}
    finally:
        await client.disconnect()


async def test_user_agent_names_the_running_engine(seen: dict[str, Any]) -> None:
    major = re.match(r"(\d+)\.", seen["engine"]).group(1)  # type: ignore[union-attr]
    assert f"Chrome/{major}.0.0.0" in seen["page"]["ua"]
    assert seen["headers"]["user-agent"] == seen["page"]["ua"]
    assert "Headless" not in seen["page"]["ua"]


async def test_platform_matches_this_os(seen: dict[str, Any]) -> None:
    system = platform.system()
    if system not in NAVIGATOR_PLATFORMS:
        pytest.skip(f"no expectation for {system}")
    assert seen["page"]["platform"] == NAVIGATOR_PLATFORMS[system]
    assert seen["headers"]["sec-ch-ua-platform"] == CLIENT_HINT_PLATFORMS[system]


async def test_client_hint_header_matches_the_page(seen: dict[str, Any]) -> None:
    brands = ", ".join(f'"{b["brand"]}";v="{b["version"]}"' for b in seen["page"]["brands"])
    assert seen["headers"]["sec-ch-ua"] == brands
    assert "HeadlessChrome" not in seen["headers"]["sec-ch-ua"]
