"""Tests for the one-round-trip results extraction."""

import json
from unittest.mock import AsyncMock

import pytest

from agentic_search_audit.core.types import ResultsConfig
from agentic_search_audit.extractors.results import (
    EXTRACT_RESULTS_JS,
    ResultsExtractor,
    build_extract_results_js,
)

pytestmark = pytest.mark.unit


def _cfg_from(script: str) -> dict:
    """Pull the JSON config back out of the generated script."""
    prefix = EXTRACT_RESULTS_JS.split("__CFG__")[0]
    suffix = EXTRACT_RESULTS_JS.split("__CFG__")[1]
    assert script.startswith(prefix) and script.endswith(suffix)
    return json.loads(script[len(prefix) : len(script) - len(suffix)])


def test_selectors_survive_quotes_and_backslashes() -> None:
    nasty = "a[title='it\\'s'] > span[data-x=\"\\\\\"]"
    config = ResultsConfig(item_selectors=[nasty], title_selectors=["h2"])
    cfg = _cfg_from(build_extract_results_js(config, top_k=5))
    assert cfg["itemSelectors"] == [nasty]
    assert cfg["titleSelectors"] == ["h2"]
    assert cfg["topK"] == 5
    assert cfg["urlAttr"] == "href"
    assert "__CFG__" not in build_extract_results_js(config, top_k=5)


def test_top_k_and_text_cap_are_passed_through() -> None:
    cfg = _cfg_from(build_extract_results_js(ResultsConfig(), top_k=3, max_text_chars=42))
    assert cfg["topK"] == 3
    assert cfg["maxTextChars"] == 42


def test_non_ascii_selector_is_escaped() -> None:
    config = ResultsConfig(item_selectors=["[aria-label='Résultats']"])
    script = build_extract_results_js(config, top_k=1)
    assert "\\u00e9" in script  # json.dumps keeps the script ASCII-only


@pytest.mark.parametrize(
    "raw",
    [None, "string", 7, {"items": "x"}, {"items": []}, {"selector": ".p"}, []],
    ids=repr,
)
async def test_malformed_results_yield_empty(raw: object) -> None:
    client = AsyncMock()
    client.evaluate = AsyncMock(return_value=raw)
    extractor = ResultsExtractor(client, ResultsConfig(), "https://example.com")
    assert await extractor.extract_results(top_k=5) == []
    client.evaluate.assert_awaited_once()


async def test_single_round_trip_builds_items() -> None:
    client = AsyncMock()
    client.evaluate = AsyncMock(
        return_value={
            "selector": ".product-card",
            "total": 12,
            "items": [
                {
                    "index": 0,
                    "title": "  Shoe  ",
                    "url": "/p/1",
                    "snippet": "",
                    "price": "$10",
                    "image": "//cdn.example.com/1.jpg",
                },
                "garbage",
                {
                    "index": 2,
                    "title": None,
                    "url": None,
                    "snippet": None,
                    "price": None,
                    "image": None,
                },
            ],
        }
    )
    extractor = ResultsExtractor(client, ResultsConfig(), "https://example.com/search")
    items = await extractor.extract_results(top_k=3)
    client.evaluate.assert_awaited_once()
    assert [i.rank for i in items] == [1, 3]  # ranks are page positions; garbage skipped
    assert items[0].title == "Shoe"
    assert items[0].url == "https://example.com/p/1"
    assert items[0].snippet is None
    assert items[0].price == "$10"
    assert items[0].image == "https://cdn.example.com/1.jpg"
    assert items[1].title is None and items[1].url is None


async def test_script_failure_yields_empty() -> None:
    client = AsyncMock()
    client.evaluate = AsyncMock(side_effect=RuntimeError("boom"))
    extractor = ResultsExtractor(client, ResultsConfig(), "https://example.com")
    assert await extractor.extract_results() == []
