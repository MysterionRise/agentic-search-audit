"""Tests for LLM judge implementation."""

import json

import pytest

from agentic_search_audit.core.types import JudgeScore, LLMConfig, Query, ResultItem
from agentic_search_audit.judge.rubric import (
    JUDGE_SYSTEM_PROMPT,
    format_results_for_judge,
    get_judge_schema,
)


@pytest.mark.unit
def test_judge_schema():
    """Test that judge schema is valid."""
    schema = get_judge_schema()

    assert schema["type"] == "object"
    assert "properties" in schema
    assert "required" in schema

    # Check all required fields are present
    required_fields = schema["required"]
    assert "overall" in required_fields
    assert "relevance" in required_fields
    assert "diversity" in required_fields
    assert "result_quality" in required_fields
    assert "navigability" in required_fields
    assert "rationale" in required_fields
    assert "issues" in required_fields
    assert "improvements" in required_fields
    assert "evidence" in required_fields


@pytest.mark.unit
def test_format_results_for_judge():
    """Test formatting results for judge prompt."""
    results = [
        ResultItem(
            rank=1,
            title="Nike Air Max",
            url="https://nike.com/product/1",
            snippet="Premium running shoe",
            price="$120",
        ),
        ResultItem(
            rank=2,
            title="Nike React",
            url="https://nike.com/product/2",
            snippet="Lightweight trainer",
            price="$100",
        ),
    ]

    formatted = format_results_for_judge(results)

    # Should be valid JSON
    parsed = json.loads(formatted)

    assert len(parsed) == 2
    assert parsed[0]["rank"] == 1
    assert parsed[0]["title"] == "Nike Air Max"
    assert parsed[0]["price"] == "$120"
    assert parsed[1]["rank"] == 2


@pytest.mark.unit
def test_judge_system_prompt():
    """Test that system prompt contains key elements."""
    prompt = JUDGE_SYSTEM_PROMPT

    # Should mention key evaluation criteria
    assert "relevance" in prompt.lower()
    assert "diversity" in prompt.lower()
    assert "quality" in prompt.lower()
    assert "navigability" in prompt.lower()

    # Should mention score range
    assert "0-5" in prompt or "0 to 5" in prompt.lower()

    # Should mention JSON output
    assert "json" in prompt.lower()


@pytest.mark.unit
def test_judge_score_validation():
    """Test JudgeScore validation."""
    # Valid score
    score = JudgeScore(
        overall=4.5,
        relevance=4.8,
        diversity=4.2,
        result_quality=4.6,
        navigability=4.0,
        rationale="Excellent results",
        issues=["Minor issue"],
        improvements=["Add filters"],
        evidence=[{"rank": 1, "reason": "Perfect match"}],
        schema_version="1.0",
    )

    assert score.overall == 4.5
    assert score.relevance == 4.8


@pytest.mark.unit
def test_judge_score_bounds_upper():
    """Test JudgeScore upper bound validation."""
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


@pytest.mark.unit
def test_judge_score_bounds_lower():
    """Test JudgeScore lower bound validation."""
    with pytest.raises(ValueError):
        JudgeScore(
            overall=-0.5,  # Invalid: < 0
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


@pytest.mark.unit
def test_llm_config():
    """Test LLM configuration."""
    config = LLMConfig(
        provider="openai",
        model="gpt-4o-mini",
        max_tokens=800,
        temperature=0.2,
    )

    assert config.provider == "openai"
    assert config.model == "gpt-4o-mini"
    assert config.temperature == 0.2


@pytest.mark.unit
def test_llm_config_invalid_provider():
    """Test LLM config with invalid provider."""
    with pytest.raises(ValueError):
        LLMConfig(
            provider="invalid_provider",  # Not in allowed list
            model="gpt-4",
        )
