"""Tests for type definitions."""

import pytest
from agentic_search_audit.core.types import (
    Query,
    QueryOrigin,
    ResultItem,
    JudgeScore,
)


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
    """Test JudgeScore validation."""
    score = JudgeScore(
        overall=4.5,
        relevance=4.8,
        diversity=4.2,
        result_quality=4.6,
        navigability=4.0,
        rationale="Excellent search results with high relevance",
        issues=["Some minor duplicates"],
        improvements=["Add more filter options"],
        evidence=[{"rank": 1, "reason": "Perfect match"}],
        schema_version="1.0",
    )

    assert score.overall == 4.5
    assert score.relevance == 4.8
    assert len(score.issues) == 1
    assert len(score.evidence) == 1


def test_judge_score_bounds():
    """Test JudgeScore score bounds."""
    # Should fail with out of bounds score
    with pytest.raises(ValueError):
        JudgeScore(
            overall=6.0,  # Invalid: > 5
            relevance=4.0,
            diversity=4.0,
            result_quality=4.0,
            navigability=4.0,
            rationale="Test",
            issues=[],
            improvements=[],
            evidence=[],
            schema_version="1.0",
        )

    with pytest.raises(ValueError):
        JudgeScore(
            overall=-1.0,  # Invalid: < 0
            relevance=4.0,
            diversity=4.0,
            result_quality=4.0,
            navigability=4.0,
            rationale="Test",
            issues=[],
            improvements=[],
            evidence=[],
            schema_version="1.0",
        )
