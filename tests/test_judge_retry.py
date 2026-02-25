"""Tests for judge LLM retry logic."""

import asyncio
import json

import pytest

from agentic_search_audit.core.types import LLMConfig, Query
from agentic_search_audit.judge.judge import SearchQualityJudge, _is_retryable_llm_error


@pytest.mark.unit
def test_is_retryable_timeout():
    """TimeoutError should be retryable."""
    assert _is_retryable_llm_error(TimeoutError("timeout")) is True
    assert _is_retryable_llm_error(asyncio.TimeoutError()) is True


@pytest.mark.unit
def test_is_retryable_value_error():
    """ValueError should NOT be retryable."""
    assert _is_retryable_llm_error(ValueError("bad input")) is False


@pytest.mark.unit
def test_is_retryable_runtime_error():
    """RuntimeError should NOT be retryable."""
    assert _is_retryable_llm_error(RuntimeError("unknown")) is False


@pytest.mark.unit
async def test_judge_retry_on_timeout():
    """Judge should retry on timeout and succeed on second attempt."""
    config = LLMConfig(provider="openai", model="gpt-4o-mini")
    judge = SearchQualityJudge(config)

    valid_response = json.dumps(
        {
            "query_understanding": {"score": 4.0, "diagnosis": "Good"},
            "results_relevance": {"score": 4.0, "diagnosis": "Good"},
            "result_presentation": {"score": 3.5, "diagnosis": "OK"},
            "advanced_features": {"score": 3.0, "diagnosis": "OK"},
            "error_handling": {"score": 3.0, "diagnosis": "OK"},
            "rationale": "Solid search quality",
            "issues": [],
            "improvements": [],
            "evidence": [],
            "schema_version": "2.1",
        }
    )

    call_count = 0

    async def mock_call_once(user_prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TimeoutError("timed out")
        return valid_response

    judge._call_llm_once = mock_call_once  # type: ignore[assignment]

    query = Query(id="q001", text="red shoes")
    score = await judge.evaluate(
        query=query,
        results=[],
        page_url="https://example.com",
        html_content="<html></html>",
        site_name="example.com",
    )

    assert call_count == 2
    assert score.fqi > 0


@pytest.mark.unit
async def test_judge_exhausts_retries():
    """Judge should produce degraded score after all retries exhausted."""
    config = LLMConfig(provider="openai", model="gpt-4o-mini")
    judge = SearchQualityJudge(config)

    async def always_timeout(user_prompt):
        raise TimeoutError("always fails")

    judge._call_llm_once = always_timeout  # type: ignore[assignment]

    query = Query(id="q001", text="red shoes")
    score = await judge.evaluate(
        query=query,
        results=[],
        page_url="https://example.com",
        html_content="<html></html>",
        site_name="example.com",
    )

    # Should return degraded all-zero score
    assert score.query_understanding.score == 0
    assert score.results_relevance.score == 0
    assert "LLM evaluation failed" in score.rationale


@pytest.mark.unit
async def test_judge_no_retry_on_value_error():
    """Judge should NOT retry on non-retryable errors."""
    config = LLMConfig(provider="openai", model="gpt-4o-mini")
    judge = SearchQualityJudge(config)

    call_count = 0

    async def bad_request(user_prompt):
        nonlocal call_count
        call_count += 1
        raise ValueError("Bad request")

    judge._call_llm_once = bad_request  # type: ignore[assignment]

    query = Query(id="q001", text="red shoes")
    score = await judge.evaluate(
        query=query,
        results=[],
        page_url="https://example.com",
        html_content="<html></html>",
        site_name="example.com",
    )

    # Should fail immediately without retries
    assert call_count == 1
    assert score.query_understanding.score == 0
