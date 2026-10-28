"""The evaluate() contract against a real Chromium (marker: browser).

Skips when Playwright's Chromium is not installed (``playwright install chromium``).
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from agentic_search_audit.browser.errors import BrowserScriptError

pytestmark = [
    pytest.mark.browser,
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="module"),
]


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def page() -> AsyncIterator[object]:
    playwright = pytest.importorskip("playwright.async_api")
    pw = await playwright.async_playwright().start()
    try:
        browser = await pw.chromium.launch(headless=True)
    except Exception as exc:  # browser binary missing
        await pw.stop()
        pytest.skip(f"Chromium not available: {exc}")
    page = await browser.new_page()
    await page.set_content(
        "<html><body><div id='main' class='a b'>hi</div><span>1</span></body></html>"
    )
    try:
        yield page
    finally:
        await page.close()
        await browser.close()
        await pw.stop()


async def _ev(page: object, expression: str) -> object:
    from agentic_search_audit.browser.playwright_client import evaluate_on_page

    return await evaluate_on_page(page, expression)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("true", True),
        ("false", False),
        ("0", 0),
        ("1.5", 1.5),
        ("'x'", "x"),
        ("undefined", None),
        ("null", None),
        ("NaN", None),
        ("1/0", None),
        ("[1, 'a', null, undefined]", [1, "a", None, None]),
        ("({k: 'v', n: [1, 2]})", {"k": "v", "n": [1, 2]}),
        ("new Map([['a', 1]])", [["a", 1]]),
        ("new Set([1, 2])", [1, 2]),
        ("123n", "123"),
        ("(() => 1)", None),
        ("document.querySelectorAll('div').length", 1),
        ("document.querySelector('#main').textContent", "hi"),
        ("1 + 1 // trailing comment", 2),
        ("2 + 2;;", 4),
        ("(function(){ return document.title; })()", ""),
    ],
)
async def test_values(page: object, expression: str, expected: object) -> None:
    assert await _ev(page, expression) == expected


async def test_dom_node_descriptor(page: object) -> None:
    assert await _ev(page, "document.querySelector('#main')") == {
        "__node__": "DIV",
        "id": "main",
        "className": "a b",
    }
    assert await _ev(page, "document.querySelectorAll('span')") == [
        {"__node__": "SPAN", "id": None, "className": None}
    ]


@pytest.mark.parametrize(
    ("expression", "kind"),
    [
        ("(() => { throw new TypeError('boom'); })()", "script"),
        ("Promise.resolve(1)", "unsupported_promise"),
        ("(() => { const o = {}; o.self = o; return o; })()", "serialization"),
        ("'x'.repeat(2000001)", "payload_too_large"),
        ("foo(", "syntax"),
    ],
)
async def test_errors(page: object, expression: str, kind: str) -> None:
    with pytest.raises(BrowserScriptError) as info:
        await _ev(page, expression)
    assert info.value.kind == kind
