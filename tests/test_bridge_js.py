"""JS builders used by the bridge client."""

import pytest

from agentic_search_audit.browser.bridge import js

pytestmark = pytest.mark.unit

NASTY = "a[title='it\\'s'] > span[data-x=\"q\"]"


@pytest.mark.parametrize(
    "builder",
    [
        js.query_selector_info,
        js.query_selector_all_info,
        js.element_center,
        js.synthetic_click,
        js.focus_element,
        js.clear_input,
        js.element_text,
    ],
)
def test_selector_builders_embed_json(builder) -> None:
    source = builder(NASTY)
    assert '"a[title=\'it\\\\\'s\'] > span[data-x=\\"q\\"]"' in source
    assert source.lstrip().startswith(("() =>", "async () =>"))


def test_append_text_and_attribute_embed_json() -> None:
    assert '"x\\"y"' in js.append_text("input", 'x"y')
    assert '"data-a"' in js.element_attribute("p", "data-a")


def test_waits_are_async_with_timeouts() -> None:
    assert js.wait_for_selector("#x", 2500, True).startswith("async () =>")
    assert "2500" in js.wait_for_selector("#x", 2500, True)
    assert "true" in js.wait_for_selector("#x", 1, True)
    assert "false" in js.wait_for_selector("#x", 1, False)
    assert "PerformanceObserver" in js.wait_network_idle(1200, 500)
    assert "1200" in js.wait_network_idle(1200, 500)


def test_function_from_expression_keeps_expression_on_its_own_line() -> None:
    assert js.function_from_expression("1 + 1 // c") == "() => { return (\n1 + 1 // c\n); }"
