"""BridgeBrowserClient over a scripted transport (the generic client, tested once)."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from agentic_search_audit.browser.bridge.client import BridgeBrowserClient
from agentic_search_audit.browser.bridge.transport import BridgeToolError, BridgeTransport
from agentic_search_audit.browser.errors import BrowserScriptError
from agentic_search_audit.core.types import BrowserCapabilities, BrowserClient
from tests.fakes.fake_transport import FakeTransport

pytestmark = pytest.mark.unit


def _envelope(value: Any) -> str:
    return json.dumps({"ok": True, "v": value})


def _by_marker(**answers: Any) -> Any:
    """Answer scripts by a substring they contain; default None."""

    def handler(source: str) -> Any:
        for marker, value in answers.items():
            if marker in source:
                return value
        return None

    return handler


@pytest.fixture(autouse=True)
def no_sleep() -> Any:
    with patch("agentic_search_audit.browser.bridge.client.asyncio.sleep"):
        yield


def test_fake_transport_satisfies_the_protocol() -> None:
    assert isinstance(FakeTransport(), BridgeTransport)
    assert isinstance(BridgeBrowserClient(FakeTransport()), BrowserClient)


async def test_evaluate_wraps_and_decodes() -> None:
    fake = FakeTransport(evaluate_handler=lambda src: _envelope(True))
    client = BridgeBrowserClient(fake)
    assert await client.evaluate("1 === 1") is True
    source = fake.scripts[-1]
    assert source.startswith("() => { return (")
    assert "(() => {" in source  # the envelope IIFE from wrap_expression
    assert "\n1 === 1\n" in source


@pytest.mark.parametrize("value", [0, False, "", [], {}], ids=repr)
async def test_falsy_values_survive(value: Any) -> None:
    fake = FakeTransport(evaluate_handler=lambda src: _envelope(value))
    assert await BridgeBrowserClient(fake).evaluate("x") == value


async def test_script_errors_raise() -> None:
    fake = FakeTransport(
        evaluate_handler=lambda src: json.dumps({"ok": False, "kind": "script", "message": "no"})
    )
    with pytest.raises(BrowserScriptError):
        await BridgeBrowserClient(fake).evaluate("x")


async def test_navigate_networkidle_waits_inside_the_page() -> None:
    fake = FakeTransport(
        evaluate_handler=_by_marker(
            **{
                "readyState": "complete",
                "PerformanceObserver": {"idle": True},
                "location.href": "https://x/after",
            }
        )
    )
    client = BridgeBrowserClient(fake, network_idle_ms=700)
    assert await client.navigate("https://x/", wait_until="networkidle") == "https://x/after"
    assert fake.calls[0] == ("navigate", ("https://x/", 60000))
    waits = [s for s in fake.scripts if "readyState" in s or "PerformanceObserver" in s]
    assert len(waits) == 2
    assert "700" in waits[1]


async def test_navigate_domcontentloaded_does_not_wait() -> None:
    fake = FakeTransport(evaluate_handler=_by_marker(**{"location.href": "https://x/"}))
    await BridgeBrowserClient(fake).navigate("https://x/", wait_until="domcontentloaded")
    assert not any("readyState" in s or "PerformanceObserver" in s for s in fake.scripts)


async def test_query_selector_returns_dict_or_none() -> None:
    fake = FakeTransport(evaluate_handler=_by_marker(exists={"exists": True, "tag": "input"}))
    client = BridgeBrowserClient(fake)
    assert await client.query_selector("input") == {"exists": True, "tag": "input"}
    fake.evaluate_handler = lambda src: None
    assert await client.query_selector("input") is None


async def test_click_is_synthetic_without_trusted_click() -> None:
    fake = FakeTransport(
        capabilities=BrowserCapabilities(trusted_click=False),
        evaluate_handler=_by_marker(MouseEvent=True, scrollIntoView={"x": 10, "y": 20}),
    )
    await BridgeBrowserClient(fake).click("button.go")
    assert "click_at" not in fake.names()
    assert any("dispatchEvent" in s for s in fake.scripts)


async def test_click_uses_trusted_click_when_available() -> None:
    fake = FakeTransport(evaluate_handler=_by_marker(scrollIntoView={"x": 10.5, "y": 20.5}))
    await BridgeBrowserClient(fake).click("button.go")
    assert ("click_at", (10.5, 20.5)) in fake.calls


async def test_click_missing_element_raises() -> None:
    fake = FakeTransport(evaluate_handler=lambda src: None)
    with pytest.raises(BridgeToolError):
        await BridgeBrowserClient(fake).click("button.missing")


async def test_type_text_trusted_path() -> None:
    fake = FakeTransport(evaluate_handler=_by_marker(scrollIntoView={"x": 1, "y": 1}, desc=True))
    await BridgeBrowserClient(fake).type_text("input", "ab", delay=1)
    typed = [args[0] for name, args in fake.calls if name == "type_into_focused"]
    assert typed == ["a", "b"]
    assert any("desc.set.call(el, '')" in s for s in fake.scripts)  # cleared first


async def test_type_text_synthetic_path() -> None:
    fake = FakeTransport(
        capabilities=BrowserCapabilities(trusted_input=False, trusted_click=False),
        evaluate_handler=_by_marker(
            MouseEvent=True, scrollIntoView={"x": 1, "y": 1}, dispatchEvent=True
        ),
    )
    await BridgeBrowserClient(fake).type_text("input", "ab", delay=1)
    assert "type_into_focused" not in fake.names()
    appended = [s for s in fake.scripts if "(el.value || '') +" in s]
    assert len(appended) == 2 and '"a"' in appended[0] and '"b"' in appended[1]


async def test_wait_for_selector_is_one_call_with_enlarged_timeout() -> None:
    fake = FakeTransport(evaluate_handler=lambda src: True)
    assert await BridgeBrowserClient(fake).wait_for_selector("#x", timeout=3000) is True
    evaluates = [args for name, args in fake.calls if name == "evaluate"]
    assert len(evaluates) == 1
    assert evaluates[0][1] == 3000 / 1000 + 5


async def test_wait_for_network_idle_is_one_call() -> None:
    fake = FakeTransport(evaluate_handler=lambda src: {"idle": True})
    await BridgeBrowserClient(fake).wait_for_network_idle(1200)
    assert len([n for n in fake.names() if n == "evaluate"]) == 1


async def test_get_html_and_text_helpers() -> None:
    fake = FakeTransport(
        evaluate_handler=_by_marker(outerHTML="<html/>", textContent="hi", getAttribute="v")
    )
    client = BridgeBrowserClient(fake)
    assert await client.get_html() == "<html/>"
    assert await client.get_element_text("p") == "hi"
    assert await client.get_element_attribute("p", "a") == "v"


async def test_identity_mutations_are_skipped_on_real_profile() -> None:
    fake = FakeTransport(
        capabilities=BrowserCapabilities(
            user_agent_override=False, proxy=False, clear_cookies=False
        )
    )
    client = BridgeBrowserClient(fake)
    await client.set_user_agent("ua")
    await client.set_proxy("http://p")
    await client.clear_cookies()
    assert fake.calls == []


async def test_identity_mutations_are_forwarded_when_allowed() -> None:
    fake = FakeTransport()
    client = BridgeBrowserClient(fake)
    await client.set_user_agent("ua")
    await client.clear_cookies()
    assert fake.names() == ["set_user_agent", "clear_cookies"]


async def test_lifecycle_and_viewport() -> None:
    fake = FakeTransport(capabilities=BrowserCapabilities(isolated_profile=True))
    async with BridgeBrowserClient(fake, viewport_width=800, viewport_height=600) as client:
        assert client.is_page_alive() and client.is_browser_alive()
        assert ("set_viewport", (800, 600)) in fake.calls
    assert fake.opened == 1 and fake.closed == 1


async def test_viewport_not_applied_on_real_profile() -> None:
    fake = FakeTransport(capabilities=BrowserCapabilities(isolated_profile=False))
    async with BridgeBrowserClient(fake):
        assert "set_viewport" not in fake.names()


async def test_recover_and_reconnect() -> None:
    fake = FakeTransport()
    client = BridgeBrowserClient(fake)
    await client.connect()
    fake.page_alive_value = False
    assert client.is_page_alive() is False
    await client.recover_page()
    assert ("new_tab", ("about:blank",)) in fake.calls and client.is_page_alive()
    await client.reconnect()
    assert fake.opened == 2 and fake.closed == 1


async def test_screenshot_resolves_path_and_creates_parent(tmp_path: Path) -> None:
    fake = FakeTransport()
    target = tmp_path / "shots" / "one.png"
    result = await BridgeBrowserClient(fake).screenshot(target, full_page=True)
    assert result == target and target.exists()
    assert fake.calls[-1] == ("screenshot", (target.resolve(), True))
