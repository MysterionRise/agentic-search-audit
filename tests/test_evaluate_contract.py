"""Every backend's ``evaluate`` must return the same Python value for the same JS result.

Each backend gets a fake engine that (a) asserts the script it receives went through the
shared wrapper and (b) answers with a JSON envelope. The test that fails on the old code
is ``test_true_is_bool``: the backends used to return ``"True"``.
"""

import json
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentic_search_audit.browser._js import wrap_expression
from agentic_search_audit.browser.errors import BrowserScriptError
from agentic_search_audit.core.types import BrowserClient

pytestmark = pytest.mark.unit

ENVELOPE_VALUES: list[Any] = [True, False, 0, 1, 1.5, "x", "", [1, "a", None], {"k": "v"}, None]


def _playwright_client(answer: Callable[[str], Any]) -> tuple[BrowserClient, MagicMock]:
    from agentic_search_audit.browser.playwright_client import PlaywrightBrowserClient

    client = PlaywrightBrowserClient()
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=answer)
    client._page = page
    return client, page.evaluate


def _cdp_client(answer: Callable[[str], Any]) -> tuple[BrowserClient, MagicMock]:
    from agentic_search_audit.browser.cdp_client import CDPBrowserClient

    client = CDPBrowserClient(cdp_endpoint="ws://localhost:9222")
    page = MagicMock()
    page.evaluate = AsyncMock(side_effect=answer)
    client._page = page
    return client, page.evaluate


def _undetected_client(answer: Callable[[str], Any]) -> tuple[BrowserClient, MagicMock]:
    from agentic_search_audit.browser.undetected_client import UndetectedBrowserClient

    client = UndetectedBrowserClient()
    driver = MagicMock()

    def execute_script(script: str) -> Any:
        assert script.startswith("return (() => {")
        return answer(script[len("return ") :])

    driver.execute_script = MagicMock(side_effect=execute_script)
    client._driver = driver
    return client, driver.execute_script


BACKENDS = {
    "playwright": _playwright_client,
    "cdp": _cdp_client,
    "undetected": _undetected_client,
}


def _envelope_for(value: Any) -> Callable[[str], str]:
    def answer(script: str) -> str:
        assert script == wrap_expression("EXPR"), "script must go through wrap_expression"
        return json.dumps({"ok": True, "v": value})

    return answer


@pytest.mark.parametrize("backend", sorted(BACKENDS))
@pytest.mark.parametrize("value", ENVELOPE_VALUES, ids=repr)
async def test_values_round_trip(backend: str, value: Any) -> None:
    client, engine = BACKENDS[backend](_envelope_for(value))
    assert await client.evaluate("EXPR") == value
    assert engine.call_count == 1


@pytest.mark.parametrize("backend", sorted(BACKENDS))
async def test_true_is_bool(backend: str) -> None:
    client, _ = BACKENDS[backend](_envelope_for(True))
    result = await client.evaluate("EXPR")
    assert result is True
    assert not isinstance(result, str)


@pytest.mark.parametrize("backend", sorted(BACKENDS))
async def test_error_envelope_raises(backend: str) -> None:
    def answer(script: str) -> str:
        return json.dumps({"ok": False, "kind": "script", "name": "TypeError", "message": "boom"})

    client, _ = BACKENDS[backend](answer)
    with pytest.raises(BrowserScriptError) as info:
        await client.evaluate("EXPR")
    assert info.value.kind == "script"
    assert info.value.name == "TypeError"


@pytest.mark.parametrize("backend", sorted(BACKENDS))
async def test_non_envelope_raises_decode(backend: str) -> None:
    client, _ = BACKENDS[backend](lambda script: "just text")
    with pytest.raises(BrowserScriptError) as info:
        await client.evaluate("EXPR")
    assert info.value.kind == "decode"


@pytest.mark.parametrize("backend", ["playwright", "cdp"])
async def test_playwright_page_gone_propagates(backend: str) -> None:
    from playwright.async_api import Error as PlaywrightError

    def answer(script: str) -> str:
        raise PlaywrightError("Target page, context or browser has been closed")

    client, _ = BACKENDS[backend](answer)
    with pytest.raises(PlaywrightError):
        await client.evaluate("EXPR")


async def test_undetected_driver_error_propagates() -> None:
    def answer(script: str) -> str:
        raise RuntimeError("chrome not reachable")

    client, _ = BACKENDS["undetected"](answer)
    with pytest.raises(RuntimeError):
        await client.evaluate("EXPR")


@pytest.mark.parametrize("backend", sorted(BACKENDS))
async def test_not_connected_raises(backend: str) -> None:
    client, _ = BACKENDS[backend](_envelope_for(1))
    if backend == "undetected":
        client._driver = None  # type: ignore[attr-defined]
    else:
        client._page = None  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="not connected"):
        await client.evaluate("EXPR")
