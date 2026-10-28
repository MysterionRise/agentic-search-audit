"""Guards around the consent and close-button fallbacks in ModalHandler.

Before the evaluate() contract fix these fallbacks never ran on a real backend
(the string "False" counted as a dismissal); now that they do, they must stay
scoped and must not double-dismiss.
"""

from unittest.mock import AsyncMock

import pytest

from agentic_search_audit.core.types import LocationConfig, ModalsConfig
from agentic_search_audit.extractors.modals import ModalHandler

pytestmark = pytest.mark.unit


def _handler(evaluate: AsyncMock) -> tuple[ModalHandler, AsyncMock]:
    client = AsyncMock()
    client.query_selector = AsyncMock(return_value=None)
    client.evaluate = evaluate
    return ModalHandler(client, ModalsConfig(location=LocationConfig(enabled=False))), client


async def test_false_results_do_not_count_as_dismissals() -> None:
    handler, client = _handler(AsyncMock(return_value=False))
    assert await handler._try_cookie_consent_selectors() == 0
    # every fallback strategy ran: consent API, text button, shadow DOM, iframe
    scripts = [call.args[0] for call in client.evaluate.await_args_list]
    assert any("UC_UI" in script for script in scripts)
    assert any("acceptPatterns" in script for script in scripts)
    assert any("shadowRoot" in script for script in scripts)
    assert any("iframe" in script.lower() for script in scripts)


async def test_stringified_false_from_a_broken_backend_still_counts_zero() -> None:
    """A backend regressing to str() results must not look like a dismissal."""
    handler, _ = _handler(AsyncMock(return_value="False"))
    assert await handler._try_cookie_consent_selectors() == 0


async def test_api_dismissal_short_circuits_the_fallbacks() -> None:
    # call 1: the selector probe finds nothing; call 2: the consent-platform API answers
    handler, client = _handler(AsyncMock(side_effect=[None, "didomi_api"]))
    assert await handler._try_cookie_consent_selectors() == 1
    assert client.evaluate.await_count == 2


async def test_text_button_and_shadow_scripts_are_scoped_to_consent_containers() -> None:
    handler, client = _handler(AsyncMock(return_value=False))
    await handler._try_cookie_consent_selectors()
    scripts = [call.args[0] for call in client.evaluate.await_args_list]
    scoped = [s for s in scripts if "inConsentContainer" in s]
    assert len(scoped) == 2
    for script in scoped:
        assert "inConsentContainer" in script
        assert "text.length > 40" in script


async def test_close_button_loop_does_not_run_without_an_overlay() -> None:
    handler, client = _handler(AsyncMock(return_value=False))
    handler._check_modal_overlay = AsyncMock(return_value=False)  # type: ignore[method-assign]
    handler._find_close_button = AsyncMock()  # type: ignore[method-assign]
    assert await handler.dismiss_modals() == 0
    handler._find_close_button.assert_not_awaited()
    client.press_key.assert_not_awaited()


async def test_close_button_is_clicked_once_per_visible_overlay() -> None:
    handler, client = _handler(AsyncMock(return_value=False))
    overlay = AsyncMock(side_effect=[True, False])
    handler._check_modal_overlay = overlay  # type: ignore[method-assign]
    handler._find_close_button = AsyncMock(return_value=("button", 2))  # type: ignore[method-assign]
    client.evaluate = AsyncMock(side_effect=lambda script: "el.click()" in script)
    assert await handler.dismiss_modals() == 1
    click_scripts = [
        c.args[0]
        for c in client.evaluate.await_args_list
        if 'document.querySelectorAll("button")[2]' in c.args[0]
    ]
    assert len(click_scripts) == 1


async def test_find_close_button_reads_the_dict_result() -> None:
    handler, client = _handler(
        AsyncMock(return_value={"selector": "button", "index": 3, "text": "Close"})
    )
    assert await handler._find_close_button() == ("button", 3)


async def test_find_close_button_ignores_non_dict_results() -> None:
    handler, _ = _handler(AsyncMock(return_value='{"selector": "button", "index": 3}'))
    assert await handler._find_close_button() is None


async def test_find_close_button_script_is_anchored_and_container_scoped() -> None:
    handler, client = _handler(AsyncMock(return_value=None))
    handler.config = ModalsConfig(
        close_text_matches=["no thanks", "×"], location=LocationConfig(enabled=False)
    )
    await handler._find_close_button()
    script = client.evaluate.await_args_list[0].args[0]
    assert "containers.some" in script
    assert "anchored" in script
    assert "no\\\\ thanks" in script  # re.escape, JSON-encoded


async def test_find_close_button_without_patterns_is_a_noop() -> None:
    handler, client = _handler(AsyncMock(return_value=None))
    handler.config = ModalsConfig(close_text_matches=[], location=LocationConfig(enabled=False))
    assert await handler._find_close_button() is None
    client.evaluate.assert_not_awaited()
