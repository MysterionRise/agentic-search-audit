"""Tests for extractors (search box, results, modals)."""

from unittest.mock import AsyncMock

import pytest

from agentic_search_audit.core.types import LLMConfig, ModalsConfig, ResultsConfig, SearchConfig
from agentic_search_audit.extractors.results import ResultsExtractor
from agentic_search_audit.extractors.search_box import SearchBoxFinder


@pytest.mark.unit
def test_search_config_defaults():
    """Test SearchConfig default values."""
    config = SearchConfig()

    assert len(config.input_selectors) > 0
    assert 'input[type="search"]' in config.input_selectors
    assert config.submit_strategy == "enter"


@pytest.mark.unit
def test_search_config_custom():
    """Test SearchConfig with custom values."""
    config = SearchConfig(
        input_selectors=["#search-input"],
        submit_strategy="clickSelector",
        submit_selector="button[type='submit']",
    )

    assert config.input_selectors == ["#search-input"]
    assert config.submit_strategy == "clickSelector"
    assert config.submit_selector == "button[type='submit']"


@pytest.mark.unit
def test_results_config_defaults():
    """Test ResultsConfig default values."""
    config = ResultsConfig()

    assert len(config.item_selectors) > 0
    assert len(config.title_selectors) > 0
    assert config.url_attr == "href"


@pytest.mark.unit
def test_results_config_custom():
    """Test ResultsConfig with custom values."""
    config = ResultsConfig(
        item_selectors=[".product"],
        title_selectors=["h2.title"],
        url_attr="data-url",
        snippet_selectors=[".desc"],
        price_selectors=[".price"],
    )

    assert config.item_selectors == [".product"]
    assert config.title_selectors == ["h2.title"]
    assert config.url_attr == "data-url"


@pytest.mark.unit
def test_modals_config_defaults():
    """Test ModalsConfig default values."""
    config = ModalsConfig()

    assert len(config.close_text_matches) > 0
    assert "accept" in config.close_text_matches
    assert "close" in config.close_text_matches
    assert config.max_auto_clicks == 3
    assert config.wait_after_close_ms == 500


@pytest.mark.unit
def test_modals_config_custom():
    """Test ModalsConfig with custom values."""
    config = ModalsConfig(
        close_text_matches=["ok", "dismiss"],
        max_auto_clicks=5,
        wait_after_close_ms=1000,
    )

    assert config.close_text_matches == ["ok", "dismiss"]
    assert config.max_auto_clicks == 5
    assert config.wait_after_close_ms == 1000


def _make_finder(trigger_selector: str | None = None) -> tuple[SearchBoxFinder, AsyncMock]:
    """Create a SearchBoxFinder with a mock browser client."""
    client = AsyncMock()
    config = SearchConfig(trigger_selector=trigger_selector)
    llm_config = LLMConfig()
    finder = SearchBoxFinder(client, config, llm_config, use_intelligent_fallback=False)
    return finder, client


@pytest.mark.unit
async def test_click_trigger_noop_when_none():
    """_click_trigger returns True immediately when trigger_selector is None."""
    finder, client = _make_finder(trigger_selector=None)
    assert await finder._click_trigger() is True
    client.click.assert_not_called()


@pytest.mark.unit
async def test_click_trigger_clicks_and_waits():
    """_click_trigger clicks the trigger and waits for an input selector to appear."""
    finder, client = _make_finder(trigger_selector=".search-icon")
    client.wait_for_selector = AsyncMock(return_value=True)

    assert await finder._click_trigger() is True
    client.click.assert_awaited_once_with(".search-icon")
    client.wait_for_selector.assert_awaited()


@pytest.mark.unit
async def test_click_trigger_returns_false_on_click_error():
    """_click_trigger returns False when the click itself raises."""
    finder, client = _make_finder(trigger_selector=".search-icon")
    client.click = AsyncMock(side_effect=RuntimeError("element not found"))

    assert await finder._click_trigger() is False


@pytest.mark.unit
async def test_click_trigger_rejects_dangerous_selector():
    """_click_trigger returns False for dangerous selectors."""
    finder, client = _make_finder(trigger_selector="javascript:alert(1)")

    assert await finder._click_trigger() is False
    client.click.assert_not_called()


@pytest.mark.unit
async def test_submit_search_calls_trigger_before_find():
    """submit_search invokes _click_trigger before looking for the search box."""
    finder, client = _make_finder(trigger_selector=".open-search")
    # Trigger click succeeds, input appears
    client.wait_for_selector = AsyncMock(return_value=True)
    # query_selector returns a match for the first default selector
    client.query_selector = AsyncMock(return_value={"nodeId": 1})
    # evaluate / type_text / press_key succeed
    client.evaluate = AsyncMock(return_value=None)
    client.type_text = AsyncMock()
    client.press_key = AsyncMock()

    result = await finder.submit_search("shoes")

    assert result is True
    # Trigger was clicked first
    client.click.assert_any_call(".open-search")


# --- check_for_no_results tests ---


def _make_results_extractor(
    no_results_selectors: list[str] | None = None,
) -> tuple[ResultsExtractor, AsyncMock]:
    """Create a ResultsExtractor with a mock browser client."""
    client = AsyncMock()
    config = ResultsConfig(
        no_results_selectors=no_results_selectors or [],
    )
    return ResultsExtractor(client, config, "https://example.com"), client


@pytest.mark.unit
async def test_no_results_explicit_selector_visible():
    """Explicit no_results_selectors: returns True when element is visible."""
    ext, client = _make_results_extractor(no_results_selectors=[".no-results-msg"])
    client.evaluate = AsyncMock(return_value="true")

    assert await ext.check_for_no_results() is True


@pytest.mark.unit
async def test_no_results_explicit_selector_hidden():
    """Explicit no_results_selectors: returns False when element is hidden."""
    ext, client = _make_results_extractor(no_results_selectors=[".no-results-msg"])
    client.evaluate = AsyncMock(return_value="false")

    assert await ext.check_for_no_results() is False


@pytest.mark.unit
async def test_no_results_explicit_selector_missing():
    """Explicit no_results_selectors: returns False when element doesn't exist."""
    ext, client = _make_results_extractor(no_results_selectors=[".no-results-msg"])
    client.evaluate = AsyncMock(return_value="false")

    assert await ext.check_for_no_results() is False


@pytest.mark.unit
async def test_no_results_heuristic_detects_pattern():
    """Heuristic fallback: detects 'no results' in scoped content area."""
    ext, client = _make_results_extractor()
    client.evaluate = AsyncMock(
        return_value="showing no results for your search. try something else."
    )

    assert await ext.check_for_no_results() is True


@pytest.mark.unit
async def test_no_results_heuristic_ignores_footer_text():
    """Heuristic fallback: the JS scope excludes footer/nav text.

    The mock returns scoped text that does NOT contain a no-results
    pattern, simulating the fix where footer text is excluded.
    """
    ext, client = _make_results_extractor()
    # Scoped text only has product content, no 'no results' phrase
    client.evaluate = AsyncMock(return_value="nike air max running shoes best sellers")

    assert await ext.check_for_no_results() is False


@pytest.mark.unit
async def test_no_results_heuristic_null_text():
    """Heuristic fallback: returns False when evaluate returns null."""
    ext, client = _make_results_extractor()
    client.evaluate = AsyncMock(return_value="null")

    assert await ext.check_for_no_results() is False


@pytest.mark.unit
async def test_no_results_config_field_defaults_empty():
    """no_results_selectors defaults to empty list."""
    config = ResultsConfig()
    assert config.no_results_selectors == []


@pytest.mark.unit
async def test_no_results_config_field_accepts_selectors():
    """no_results_selectors accepts custom selectors."""
    config = ResultsConfig(
        no_results_selectors=[".empty-state", "#no-results-banner"],
    )
    assert config.no_results_selectors == [".empty-state", "#no-results-banner"]
