"""Bridge backends against your real Chrome (opt-in).

    ASA_BRIDGE_INTEGRATION=1 uv run pytest -m integration tests/integration/test_bridge_real_browser.py

Prerequisites: chrome_devtools_mcp needs Node >= 20.19 (``nvm use 24``) and, on first run,
the chrome://inspect/#remote-debugging toggle plus the Chrome dialog; kimi_webbridge needs
``~/.kimi-webbridge/bin/kimi-webbridge start`` and its Chrome extension. Select backends with
``ASA_BRIDGE_BACKENDS=chrome_devtools_mcp,kimi_webbridge``; ``ASA_BRIDGE_MODE=launch`` lets
chrome_devtools_mcp start its own Chrome (no user action), ``ASA_BRIDGE_HEADLESS=1`` hides it.
"""

import os
from pathlib import Path

import pytest

from agentic_search_audit.browser.factory import create_browser_client
from agentic_search_audit.core.types import RunConfig

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("ASA_BRIDGE_INTEGRATION") != "1",
        reason="set ASA_BRIDGE_INTEGRATION=1 to drive your real Chrome",
    ),
]

BACKENDS = os.environ.get("ASA_BRIDGE_BACKENDS", "chrome_devtools_mcp,kimi_webbridge").split(",")
#: autoconnect (default, needs the user's Chrome), browser_url, or launch (no user action)
BRIDGE_MODE = os.environ.get("ASA_BRIDGE_MODE", "autoconnect")
HEADLESS = os.environ.get("ASA_BRIDGE_HEADLESS", "0") == "1"


@pytest.mark.parametrize("backend", BACKENDS)
async def test_bridge_end_to_end(backend: str, tmp_path: Path) -> None:
    config = RunConfig(
        browser_backend=backend, headless=HEADLESS, bridge={"mode": BRIDGE_MODE}  # type: ignore[arg-type]
    )
    client = create_browser_client(config)
    async with client:
        url = await client.navigate("https://books.toscrape.com/", wait_until="networkidle")
        assert "books.toscrape.com" in url

        assert await client.evaluate("1 + 1") == 2
        assert await client.evaluate("document.title") == "All products | Books to Scrape - Sandbox"
        assert await client.query_selector("article.product_pod") is not None
        count = await client.evaluate("document.querySelectorAll('article.product_pod').length")
        assert isinstance(count, int) and count == 20
        assert await client.wait_for_selector("article.product_pod", timeout=3000) is True

        shot = await client.screenshot(tmp_path / f"{backend}.png", full_page=True)
        assert shot.exists() and shot.stat().st_size > 1000
        assert "<html" in (await client.get_html()).lower()

        await client.press_key("Escape")
        await client.recover_page()
        assert client.is_page_alive() and client.is_browser_alive()
