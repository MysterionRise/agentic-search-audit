"""Tests for type definitions."""

import pytest

from agentic_search_audit.core.types import (
    Query,
    QueryOrigin,
    ResultItem,
    compute_fqi,
    get_fqi_band,
)
from tests.helpers import make_fqi_judge_score


def test_query_creation():
    """Test Query model."""
    query = Query(
        id="q001",
        text="running shoes",
        lang="en",
        origin=QueryOrigin.PREDEFINED,
    )

    assert query.id == "q001"
    assert query.text == "running shoes"
    assert query.lang == "en"
    assert query.origin == QueryOrigin.PREDEFINED


def test_result_item_creation():
    """Test ResultItem model."""
    item = ResultItem(
        rank=1,
        title="Nike Air Max",
        url="https://www.nike.com/product/123",
        snippet="Premium running shoe",
        price="$120",
    )

    assert item.rank == 1
    assert item.title == "Nike Air Max"
    assert item.url == "https://www.nike.com/product/123"
    assert item.price == "$120"


def test_judge_score_validation():
    """Test JudgeScore validation with FQI structure."""
    score = make_fqi_judge_score(
        query_understanding_score=4.5,
        results_relevance_score=4.8,
        result_presentation_score=4.2,
        advanced_features_score=4.6,
        error_handling_score=4.0,
        rationale="Excellent search results with high relevance",
        issues=["Some minor duplicates"],
        improvements=["Add more filter options"],
        evidence=[{"rank": 1, "reason": "Perfect match"}],
    )

    assert score.query_understanding.score == 4.5
    assert score.results_relevance.score == 4.8
    assert score.result_presentation.score == 4.2
    assert score.advanced_features.score == 4.6
    assert score.error_handling.score == 4.0
    assert len(score.issues) == 1
    assert len(score.evidence) == 1
    assert score.schema_version == "2.1"

    # FQI should be auto-computed by the model validator
    expected_fqi = 4.5 * 0.25 + 4.8 * 0.25 + 4.2 * 0.20 + 4.6 * 0.20 + 4.0 * 0.10
    assert score.fqi == pytest.approx(expected_fqi, abs=1e-3)


def test_judge_score_bounds():
    """Test JudgeScore dimension score bounds."""
    # Should fail with out of bounds dimension score (> 5)
    with pytest.raises(ValueError):
        make_fqi_judge_score(query_understanding_score=6.0)

    # Should fail with out of bounds dimension score (< 0)
    with pytest.raises(ValueError):
        make_fqi_judge_score(results_relevance_score=-1.0)


def test_fqi_weighted_calculation():
    """Test that FQI is correctly computed as sum(dimension * weight)."""
    score = make_fqi_judge_score(
        query_understanding_score=5.0,
        results_relevance_score=4.0,
        result_presentation_score=3.0,
        advanced_features_score=2.0,
        error_handling_score=1.0,
    )

    expected_fqi = 5.0 * 0.25 + 4.0 * 0.25 + 3.0 * 0.20 + 2.0 * 0.20 + 1.0 * 0.10
    assert score.fqi == pytest.approx(expected_fqi, abs=1e-4)

    # Verify with all equal scores
    score_equal = make_fqi_judge_score(
        query_understanding_score=3.0,
        results_relevance_score=3.0,
        result_presentation_score=3.0,
        advanced_features_score=3.0,
        error_handling_score=3.0,
    )
    # When all scores are the same, FQI should equal that score
    # (since weights sum to 1.0)
    assert score_equal.fqi == pytest.approx(3.0, abs=1e-4)


def test_fqi_hard_cap():
    """Test that FQI is capped at 3.5 when query_understanding or results_relevance < 2.0."""
    # query_understanding below 2.0 should trigger cap
    score_low_qu = make_fqi_judge_score(
        query_understanding_score=1.5,
        results_relevance_score=5.0,
        result_presentation_score=5.0,
        advanced_features_score=5.0,
        error_handling_score=5.0,
    )
    assert score_low_qu.fqi <= 3.5

    # results_relevance below 2.0 should trigger cap
    score_low_rr = make_fqi_judge_score(
        query_understanding_score=5.0,
        results_relevance_score=1.0,
        result_presentation_score=5.0,
        advanced_features_score=5.0,
        error_handling_score=5.0,
    )
    assert score_low_rr.fqi <= 3.5

    # Both below 2.0 should also trigger cap
    score_both_low = make_fqi_judge_score(
        query_understanding_score=1.0,
        results_relevance_score=1.0,
        result_presentation_score=5.0,
        advanced_features_score=5.0,
        error_handling_score=5.0,
    )
    assert score_both_low.fqi <= 3.5

    # When both are >= 2.0, no cap should apply
    score_no_cap = make_fqi_judge_score(
        query_understanding_score=2.5,
        results_relevance_score=2.5,
        result_presentation_score=5.0,
        advanced_features_score=5.0,
        error_handling_score=5.0,
    )
    expected_fqi = 2.5 * 0.25 + 2.5 * 0.25 + 5.0 * 0.20 + 5.0 * 0.20 + 5.0 * 0.10
    assert score_no_cap.fqi == pytest.approx(expected_fqi, abs=1e-4)
    assert score_no_cap.fqi > 3.5


def test_get_fqi_band():
    """Test FQI band label assignment."""
    assert get_fqi_band(5.0) == "Excellent"
    assert get_fqi_band(4.5) == "Excellent"
    assert get_fqi_band(4.0) == "Good"
    assert get_fqi_band(3.5) == "Good"
    assert get_fqi_band(3.0) == "Weak"
    assert get_fqi_band(2.5) == "Weak"
    assert get_fqi_band(2.0) == "Critical"
    assert get_fqi_band(1.5) == "Critical"
    assert get_fqi_band(1.0) == "Broken"
    assert get_fqi_band(0.0) == "Broken"


def test_compute_fqi():
    """Test the compute_fqi function directly."""
    dims = {
        "query_understanding": 4.0,
        "results_relevance": 4.0,
        "result_presentation": 4.0,
        "advanced_features": 4.0,
        "error_handling": 4.0,
    }
    # All 4.0 with weights summing to 1.0 should give 4.0
    assert compute_fqi(dims) == pytest.approx(4.0, abs=1e-4)

    # Test hard cap via compute_fqi directly
    dims_low_qu = {
        "query_understanding": 1.0,
        "results_relevance": 5.0,
        "result_presentation": 5.0,
        "advanced_features": 5.0,
        "error_handling": 5.0,
    }
    result = compute_fqi(dims_low_qu)
    assert result <= 3.5

    # Test with missing dimensions defaults to 0.0
    assert compute_fqi({}) == pytest.approx(0.0, abs=1e-4)

    # Test precise weighted sum
    dims_varied = {
        "query_understanding": 5.0,
        "results_relevance": 3.0,
        "result_presentation": 4.0,
        "advanced_features": 2.0,
        "error_handling": 1.0,
    }
    expected = 5.0 * 0.25 + 3.0 * 0.25 + 4.0 * 0.20 + 2.0 * 0.20 + 1.0 * 0.10
    assert compute_fqi(dims_varied) == pytest.approx(expected, abs=1e-4)
