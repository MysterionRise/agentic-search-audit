"""Tests for lazy loading and infinite scroll support."""

from unittest.mock import AsyncMock, patch

import pytest

from agentic_search_audit.core.types import ResultsConfig, RunConfig


@pytest.mark.unit
def test_run_config_scroll_defaults():
    """RunConfig should expose lazy-loading defaults."""
    cfg = RunConfig()
    assert cfg.max_scroll_attempts == 5
    assert cfg.scroll_step_px == 800
    assert cfg.scroll_pause_ms == 1500
    assert len(cfg.load_more_selectors) > 0
    assert len(cfg.load_more_text_patterns) > 0


@pytest.mark.unit
def test_run_config_scroll_custom():
    """RunConfig accepts custom scroll settings."""
    cfg = RunConfig(
        max_scroll_attempts=10,
        scroll_step_px=1200,
        scroll_pause_ms=2000,
        load_more_selectors=["#load-more"],
        load_more_text_patterns=["load more products"],
    )
    assert cfg.max_scroll_attempts == 10
    assert cfg.scroll_step_px == 1200
    assert cfg.scroll_pause_ms == 2000
    assert cfg.load_more_selectors == ["#load-more"]
    assert cfg.load_more_text_patterns == ["load more products"]


# ---------------------------------------------------------------------------
# ResultsExtractor.count_visible_results
# ---------------------------------------------------------------------------

@pytest.mark.unit
async def test_count_visible_results_returns_count():
    """count_visible_results returns the DOM element count."""
    from agentic_search_audit.extractors.results import ResultsExtractor

    client = AsyncMock()
    client.evaluate = AsyncMock(return_value="7")
    config = ResultsConfig(item_selectors=[".product-card"])
    extractor = ResultsExtractor(client, config, "https://example.com")

    count = await extractor.count_visible_results()
    assert count == 7


@pytest.mark.unit
async def test_count_visible_results_fallback_selectors():
    """count_visible_results tries each selector until one matches."""
    from agentic_search_audit.extractors.results import ResultsExtractor

    client = AsyncMock()
    # First selector returns 0, second returns 3
    client.evaluate = AsyncMock(side_effect=["0", "3"])
    config = ResultsConfig(item_selectors=[".nope", ".product-card"])
    extractor = ResultsExtractor(client, config, "https://example.com")

    count = await extractor.count_visible_results()
    assert count == 3


@pytest.mark.unit
async def test_count_visible_results_returns_zero_when_none():
    """count_visible_results returns 0 when no selectors match."""
    from agentic_search_audit.extractors.results import ResultsExtractor

    client = AsyncMock()
    client.evaluate = AsyncMock(return_value="0")
    config = ResultsConfig(item_selectors=[".product-card"])
    extractor = ResultsExtractor(client, config, "https://example.com")

    count = await extractor.count_visible_results()
    assert count == 0


# ---------------------------------------------------------------------------
# Orchestrator._scroll_for_results
# ---------------------------------------------------------------------------

def _make_orchestrator(top_k=10, max_scroll_attempts=3, visible_counts=None):
    """Helper to build a minimal orchestrator with mocked client."""
    from unittest.mock import MagicMock

    from agentic_search_audit.core.orchestrator import SearchAuditOrchestrator
    from agentic_search_audit.core.types import (
        AuditConfig,
        RunConfig,
        SiteConfig,
    )

    site_cfg = SiteConfig(url="https://example.com")
    run_cfg = RunConfig(
        top_k=top_k,
        max_scroll_attempts=max_scroll_attempts,
        scroll_pause_ms=0,  # no actual sleeping in tests
    )
    config = AuditConfig(site=site_cfg, run=run_cfg)
    orch = SearchAuditOrchestrator(config, [], MagicMock())

    client = AsyncMock()
    client.evaluate = AsyncMock(return_value=None)
    client.query_selector = AsyncMock(return_value=None)
    client.wait_for_network_idle = AsyncMock()
    orch.client = client

    extractor = AsyncMock()
    if visible_counts is not None:
        extractor.count_visible_results = AsyncMock(side_effect=visible_counts)
    else:
        extractor.count_visible_results = AsyncMock(return_value=0)

    return orch, client, extractor


@pytest.mark.unit
async def test_scroll_stops_when_enough_results():
    """_scroll_for_results stops early when top_k results are visible."""
    # After initial scroll: 12 results (>= top_k=10) -> stop
    orch, client, extractor = _make_orchestrator(
        top_k=10, max_scroll_attempts=5, visible_counts=[12]
    )

    with patch("agentic_search_audit.core.orchestrator.asyncio.sleep", new_callable=AsyncMock):
        await orch._scroll_for_results(extractor, 10)

    # Should NOT enter the scroll loop since initial count >= top_k
    assert extractor.count_visible_results.call_count == 1


@pytest.mark.unit
async def test_scroll_increments_until_enough():
    """_scroll_for_results scrolls until top_k results appear."""
    # After initial scroll: 3, then after scroll attempt 1: 6, attempt 2: 10 (done)
    orch, client, extractor = _make_orchestrator(
        top_k=10, max_scroll_attempts=5, visible_counts=[3, 6, 10]
    )

    with patch("agentic_search_audit.core.orchestrator.asyncio.sleep", new_callable=AsyncMock):
        await orch._scroll_for_results(extractor, 10)

    assert extractor.count_visible_results.call_count == 3


@pytest.mark.unit
async def test_scroll_stops_when_no_new_results():
    """_scroll_for_results stops when result count stops growing."""
    # After initial: 4, then still 4 -> no growth -> stop
    orch, client, extractor = _make_orchestrator(
        top_k=10, max_scroll_attempts=5, visible_counts=[4, 4]
    )

    with patch("agentic_search_audit.core.orchestrator.asyncio.sleep", new_callable=AsyncMock):
        await orch._scroll_for_results(extractor, 10)

    # 2 count calls: initial + 1 scroll attempt that saw no growth
    assert extractor.count_visible_results.call_count == 2


@pytest.mark.unit
async def test_scroll_respects_max_attempts():
    """_scroll_for_results respects max_scroll_attempts."""
    # Each scroll adds 1, but max_attempts=3 so we stop after 3 loop iterations
    orch, client, extractor = _make_orchestrator(
        top_k=100, max_scroll_attempts=3, visible_counts=[2, 3, 4, 5]
    )

    with patch("agentic_search_audit.core.orchestrator.asyncio.sleep", new_callable=AsyncMock):
        await orch._scroll_for_results(extractor, 100)

    # 1 initial + 3 loop iterations = 4 calls max
    assert extractor.count_visible_results.call_count == 4


# ---------------------------------------------------------------------------
# Orchestrator._click_load_more
# ---------------------------------------------------------------------------

@pytest.mark.unit
async def test_click_load_more_via_selector():
    """_click_load_more clicks via CSS selector."""
    orch, client, _ = _make_orchestrator()
    client.query_selector = AsyncMock(return_value={"nodeId": 1})

    result = await orch._click_load_more()
    assert result is True
    client.click.assert_called()


@pytest.mark.unit
async def test_click_load_more_via_text_pattern():
    """_click_load_more falls back to text pattern matching."""
    orch, client, _ = _make_orchestrator()
    # All CSS selectors fail
    client.query_selector = AsyncMock(return_value=None)
    # Text pattern match succeeds
    client.evaluate = AsyncMock(return_value="true")

    result = await orch._click_load_more()
    assert result is True


@pytest.mark.unit
async def test_click_load_more_returns_false_when_nothing_found():
    """_click_load_more returns False when no button found."""
    orch, client, _ = _make_orchestrator()
    client.query_selector = AsyncMock(return_value=None)
    client.evaluate = AsyncMock(return_value="false")

    result = await orch._click_load_more()
    assert result is False
