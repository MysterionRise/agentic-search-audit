"""Tests for PdpAnalyzer -- PDP visit flow, timeout, navigate-back, consistency checks."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_search_audit.core.types import (
    LLMConfig,
    ModalsConfig,
    Query,
    QueryOrigin,
    ResultItem,
    RunConfig,
)
from agentic_search_audit.extractors.pdp_analyzer import PdpAnalyzer


@pytest.fixture
def mock_client():
    """Create a mock browser client."""
    client = AsyncMock()
    client.navigate = AsyncMock(return_value="https://example.com/product/1")
    client.evaluate = AsyncMock(return_value=None)
    client.screenshot = AsyncMock()
    client.press_key = AsyncMock()
    client.query_selector = AsyncMock(return_value=None)
    return client


@pytest.fixture
def llm_config():
    return LLMConfig(provider="openai", model="gpt-4o-mini", api_key="test-key")


@pytest.fixture
def modals_config():
    return ModalsConfig()


@pytest.fixture
def sample_query():
    return Query(id="q001", text="running shoes", lang="en", origin=QueryOrigin.PREDEFINED)


@pytest.fixture
def sample_items():
    return [
        ResultItem(
            rank=1,
            title="Nike Air Max",
            url="https://example.com/product/1",
            price="$120",
        ),
        ResultItem(
            rank=2,
            title="Adidas Ultraboost",
            url="https://example.com/product/2",
            price="$180",
        ),
        ResultItem(
            rank=3,
            title="New Balance 990",
            url="https://example.com/product/3",
            price="$175",
        ),
        ResultItem(
            rank=4,
            title="Brooks Ghost",
            url="https://example.com/product/4",
            price="$130",
        ),
    ]


def _make_analyzer(
    mock_client, llm_config, modals_config, sample_query, tmp_path, timeout_ms=15000
):
    """Helper to build a PdpAnalyzer with mocked vision provider."""
    with patch(
        "agentic_search_audit.extractors.pdp_analyzer.create_vision_provider"
    ) as mock_factory:
        mock_vision = AsyncMock()
        mock_vision.analyze_image = AsyncMock(
            return_value={
                "title": "Nike Air Max",
                "price": "$120.00",
                "availability": "In Stock",
                "rating": 4.5,
                "review_count": "1,234",
            }
        )
        mock_factory.return_value = mock_vision

        analyzer = PdpAnalyzer(
            client=mock_client,
            llm_config=llm_config,
            modals_config=modals_config,
            run_dir=tmp_path,
            query=sample_query,
            timeout_ms=timeout_ms,
        )
    return analyzer


# ---------------------------------------------------------------------------
# PDP visit flow
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_analyze_pdps_visits_top_k(
    mock_client, llm_config, modals_config, sample_query, sample_items, tmp_path
):
    """analyze_pdps visits only top_k items."""
    analyzer = _make_analyzer(mock_client, llm_config, modals_config, sample_query, tmp_path)

    with patch("agentic_search_audit.extractors.pdp_analyzer.detect_challenge") as mock_detect:
        mock_detect.return_value = MagicMock(detected=False)

        # Write a dummy screenshot file so _extract_pdp_data can read it
        pdp_dir = tmp_path / "screenshots" / "pdp"
        pdp_dir.mkdir(parents=True, exist_ok=True)
        for i in range(1, 4):
            (pdp_dir / f"q001_{i}.png").write_bytes(b"\x89PNG fake")

        result = await analyzer.analyze_pdps(sample_items, "https://example.com/search", top_k=2)

    assert result is sample_items
    # Only first 2 items visited
    assert sample_items[0].attributes.get("pdp_analyzed") == "true"
    assert sample_items[1].attributes.get("pdp_analyzed") == "true"
    # Items 3 and 4 should not be visited
    assert "pdp_analyzed" not in sample_items[2].attributes
    assert "pdp_analyzed" not in sample_items[3].attributes


@pytest.mark.unit
async def test_pdp_stores_extracted_fields(
    mock_client, llm_config, modals_config, sample_query, tmp_path
):
    """Extracted PDP data is stored as pdp_ prefixed attributes."""
    item = ResultItem(rank=1, title="Nike Air Max", url="https://example.com/p/1", price="$120")
    analyzer = _make_analyzer(mock_client, llm_config, modals_config, sample_query, tmp_path)

    with patch("agentic_search_audit.extractors.pdp_analyzer.detect_challenge") as mock_detect:
        mock_detect.return_value = MagicMock(detected=False)
        pdp_dir = tmp_path / "screenshots" / "pdp"
        pdp_dir.mkdir(parents=True, exist_ok=True)
        (pdp_dir / "q001_1.png").write_bytes(b"\x89PNG fake")

        await analyzer.analyze_pdps([item], "https://example.com/search", top_k=1)

    assert item.attributes["pdp_analyzed"] == "true"
    assert item.attributes["pdp_title"] == "Nike Air Max"
    assert item.attributes["pdp_price"] == "$120.00"
    assert item.attributes["pdp_availability"] == "In Stock"


# ---------------------------------------------------------------------------
# No URL items
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_pdp_skips_item_without_url(
    mock_client, llm_config, modals_config, sample_query, tmp_path
):
    """Items without a URL are skipped."""
    item = ResultItem(rank=1, title="Nike Air Max", url=None, price="$120")
    analyzer = _make_analyzer(mock_client, llm_config, modals_config, sample_query, tmp_path)

    await analyzer.analyze_pdps([item], "https://example.com/search", top_k=1)

    assert item.attributes.get("pdp_analyzed") == "false"
    mock_client.navigate.assert_not_called()


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_pdp_timeout_sets_error_attribute(
    mock_client, llm_config, modals_config, sample_query, tmp_path
):
    """When PDP visit times out, pdp_error='timeout' is set."""

    # Make navigate hang forever so the timeout fires
    async def hang(*args, **kwargs):
        import asyncio

        await asyncio.sleep(999)

    mock_client.navigate = AsyncMock(side_effect=hang)

    analyzer = _make_analyzer(
        mock_client, llm_config, modals_config, sample_query, tmp_path, timeout_ms=100
    )

    item = ResultItem(rank=1, title="Nike Air Max", url="https://example.com/p/1", price="$120")
    await analyzer.analyze_pdps([item], "https://example.com/search", top_k=1)

    assert item.attributes.get("pdp_error") == "timeout"
    assert item.attributes.get("pdp_analyzed") == "false"


# ---------------------------------------------------------------------------
# Navigate-back fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_navigate_back_direct_on_domain_mismatch(
    mock_client, llm_config, modals_config, sample_query, tmp_path
):
    """_navigate_back uses direct navigation when history.back() lands on wrong domain."""
    analyzer = _make_analyzer(mock_client, llm_config, modals_config, sample_query, tmp_path)

    # history.back() lands on a different domain
    call_count = 0

    async def eval_side_effect(expr):
        nonlocal call_count
        call_count += 1
        if "history.back" in expr:
            return None
        if "location.href" in expr:
            return "https://other-domain.com/somewhere"
        return None

    mock_client.evaluate = AsyncMock(side_effect=eval_side_effect)

    await analyzer._navigate_back("https://example.com/search?q=shoes")

    # Should have navigated directly back
    mock_client.navigate.assert_called_with(
        "https://example.com/search?q=shoes", wait_until="networkidle"
    )


# ---------------------------------------------------------------------------
# Consistency checks
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_consistency_check_price_mismatch():
    """check_consistency detects price discrepancy."""
    item = ResultItem(
        rank=1,
        title="Nike Air Max",
        url="https://example.com/p/1",
        price="$120",
        attributes={
            "pdp_analyzed": "true",
            "pdp_price": "$129.99",
            "pdp_title": "Nike Air Max 90",
        },
    )

    issues = PdpAnalyzer.check_consistency(item)
    assert "price_discrepancy" in issues
    assert "120" in issues["price_discrepancy"]
    assert "129.99" in issues["price_discrepancy"]


@pytest.mark.unit
def test_consistency_check_no_issues():
    """check_consistency returns empty dict when data matches."""
    item = ResultItem(
        rank=1,
        title="Nike Air Max",
        url="https://example.com/p/1",
        price="$120.00",
        attributes={
            "pdp_analyzed": "true",
            "pdp_price": "$120.00",
            "pdp_title": "Nike Air Max Shoes",
            "pdp_availability": "In Stock",
        },
    )

    issues = PdpAnalyzer.check_consistency(item)
    assert len(issues) == 0


@pytest.mark.unit
def test_consistency_check_out_of_stock():
    """check_consistency flags out-of-stock items."""
    item = ResultItem(
        rank=1,
        title="Nike Air Max",
        url="https://example.com/p/1",
        price="$120",
        attributes={
            "pdp_analyzed": "true",
            "pdp_price": "$120.00",
            "pdp_availability": "Out of Stock",
        },
    )

    issues = PdpAnalyzer.check_consistency(item)
    assert "availability_issue" in issues


@pytest.mark.unit
def test_consistency_check_title_mismatch():
    """check_consistency flags low title similarity."""
    item = ResultItem(
        rank=1,
        title="Running Shoes",
        url="https://example.com/p/1",
        price="$120",
        attributes={
            "pdp_analyzed": "true",
            "pdp_price": "$120.00",
            "pdp_title": "Winter Jacket Collection Mens",
            "pdp_availability": "In Stock",
        },
    )

    issues = PdpAnalyzer.check_consistency(item)
    assert "title_discrepancy" in issues


@pytest.mark.unit
def test_consistency_check_skips_unanalyzed():
    """check_consistency returns empty dict when pdp_analyzed != 'true'."""
    item = ResultItem(
        rank=1,
        title="Nike Air Max",
        url="https://example.com/p/1",
        price="$120",
        attributes={"pdp_analyzed": "false"},
    )

    issues = PdpAnalyzer.check_consistency(item)
    assert len(issues) == 0


# ---------------------------------------------------------------------------
# RunConfig PDP fields
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_config_pdp_defaults():
    """RunConfig has PDP fields with correct defaults."""
    config = RunConfig()
    assert config.enable_pdp_analysis is False
    assert config.pdp_top_k == 3
    assert config.pdp_timeout_ms == 15000


@pytest.mark.unit
def test_run_config_pdp_custom():
    """RunConfig accepts custom PDP values."""
    config = RunConfig(enable_pdp_analysis=True, pdp_top_k=5, pdp_timeout_ms=30000)
    assert config.enable_pdp_analysis is True
    assert config.pdp_top_k == 5
    assert config.pdp_timeout_ms == 30000
