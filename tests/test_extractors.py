"""Tests for extractors (search box, results, modals)."""

import pytest

from agentic_search_audit.core.types import ModalsConfig, ResultsConfig, SearchConfig


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
