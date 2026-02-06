"""Tests for LLM judge implementation."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_search_audit.core.types import (
    DimensionDiagnosis,
    JudgeScore,
    LLMConfig,
    Query,
    QueryOrigin,
    ResultItem,
)
from agentic_search_audit.judge.judge import HTML_SNIPPET_MAX_CHARS, SearchQualityJudge
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
    assert "query_understanding" in required_fields
    assert "results_relevance" in required_fields
    assert "result_presentation" in required_fields
    assert "advanced_features" in required_fields
    assert "error_handling" in required_fields
    assert "rationale" in required_fields
    assert "issues" in required_fields
    assert "improvements" in required_fields
    assert "evidence" in required_fields
    assert "schema_version" in required_fields

    # Old fields should NOT be present
    assert "overall" not in required_fields
    assert "relevance" not in required_fields
    assert "diversity" not in required_fields
    assert "result_quality" not in required_fields
    assert "navigability" not in required_fields


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

    # Should mention FQI framework and key evaluation dimensions
    assert "fqi" in prompt.lower() or "findability" in prompt.lower()
    assert "query understanding" in prompt.lower()
    assert "results relevance" in prompt.lower()
    assert "result presentation" in prompt.lower()
    assert "advanced features" in prompt.lower()
    assert "error handling" in prompt.lower()

    # Should mention score range
    assert "0-5" in prompt or "0 to 5" in prompt.lower()

    # Should mention JSON output
    assert "json" in prompt.lower()


@pytest.mark.unit
def test_judge_score_validation():
    """Test JudgeScore validation."""
    # Valid score using new FQI structure
    score = JudgeScore(
        query_understanding=DimensionDiagnosis(score=4.5, diagnosis="Good understanding"),
        results_relevance=DimensionDiagnosis(score=4.8, diagnosis="Highly relevant"),
        result_presentation=DimensionDiagnosis(score=4.2, diagnosis="Well presented"),
        advanced_features=DimensionDiagnosis(score=4.6, diagnosis="Rich features"),
        error_handling=DimensionDiagnosis(score=4.0, diagnosis="Good error handling"),
        rationale="Excellent results",
        issues=["Minor issue"],
        improvements=["Add filters"],
        evidence=[{"rank": 1, "reason": "Perfect match"}],
        schema_version="2.0",
    )

    assert score.query_understanding.score == 4.5
    assert score.results_relevance.score == 4.8
    # FQI should be auto-computed
    assert score.fqi > 0


@pytest.mark.unit
def test_judge_score_bounds_upper():
    """Test JudgeScore upper bound validation."""
    with pytest.raises(ValueError):
        JudgeScore(
            query_understanding=DimensionDiagnosis(score=6.0, diagnosis="Invalid"),  # > 5
            results_relevance=DimensionDiagnosis(score=4.0, diagnosis="OK"),
            result_presentation=DimensionDiagnosis(score=4.0, diagnosis="OK"),
            advanced_features=DimensionDiagnosis(score=4.0, diagnosis="OK"),
            error_handling=DimensionDiagnosis(score=4.0, diagnosis="OK"),
            rationale="Test",
            issues=[],
            improvements=[],
            evidence=[],
            schema_version="2.1",
        )


@pytest.mark.unit
def test_judge_score_bounds_lower():
    """Test JudgeScore lower bound validation."""
    with pytest.raises(ValueError):
        JudgeScore(
            query_understanding=DimensionDiagnosis(score=-0.5, diagnosis="Invalid"),  # < 0
            results_relevance=DimensionDiagnosis(score=4.0, diagnosis="OK"),
            result_presentation=DimensionDiagnosis(score=4.0, diagnosis="OK"),
            advanced_features=DimensionDiagnosis(score=4.0, diagnosis="OK"),
            error_handling=DimensionDiagnosis(score=4.0, diagnosis="OK"),
            rationale="Test",
            issues=[],
            improvements=[],
            evidence=[],
            schema_version="2.1",
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


# ============================================================================
# SearchQualityJudge Tests
# ============================================================================


class TestSearchQualityJudgeInit:
    """Tests for SearchQualityJudge.__init__() method."""

    @pytest.mark.unit
    def test_judge_init_openai_provider(self, monkeypatch):
        """Test initialization with OpenAI provider."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-12345")

        with patch("agentic_search_audit.judge.judge.AsyncOpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            config = LLMConfig(provider="openai", model="gpt-4o-mini")
            judge = SearchQualityJudge(config)

            mock_openai.assert_called_once_with(api_key="sk-test-key-12345")
            assert judge.client == mock_client
            assert judge.config == config

    @pytest.mark.unit
    def test_judge_init_openrouter_provider_with_config_key(self):
        """Test initialization with OpenRouter provider using config API key."""
        with patch("agentic_search_audit.judge.judge.AsyncOpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            config = LLMConfig(
                provider="openrouter",
                model="anthropic/claude-3-sonnet",
                api_key="or-test-key-12345",
            )
            judge = SearchQualityJudge(config)

            mock_openai.assert_called_once_with(
                api_key="or-test-key-12345",
                base_url="https://openrouter.ai/api/v1",
            )
            assert judge.client == mock_client

    @pytest.mark.unit
    def test_judge_init_openrouter_provider_with_env_var(self, monkeypatch):
        """Test initialization with OpenRouter provider using environment variable."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-env-key-12345")

        with patch("agentic_search_audit.judge.judge.AsyncOpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            config = LLMConfig(provider="openrouter", model="anthropic/claude-3-sonnet")
            SearchQualityJudge(config)

            mock_openai.assert_called_once_with(
                api_key="or-env-key-12345",
                base_url="https://openrouter.ai/api/v1",
            )

    @pytest.mark.unit
    def test_judge_init_openrouter_custom_base_url(self, monkeypatch):
        """Test initialization with OpenRouter using custom base URL."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key")

        with patch("agentic_search_audit.judge.judge.AsyncOpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            config = LLMConfig(
                provider="openrouter",
                model="test-model",
                base_url="https://custom.openrouter.ai/v1",
            )
            SearchQualityJudge(config)

            mock_openai.assert_called_once_with(
                api_key="or-test-key",
                base_url="https://custom.openrouter.ai/v1",
            )

    @pytest.mark.unit
    def test_judge_init_missing_openai_api_key(self, monkeypatch):
        """Test that missing OpenAI API key raises ValueError."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        config = LLMConfig(provider="openai", model="gpt-4o-mini")

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            SearchQualityJudge(config)

    @pytest.mark.unit
    def test_judge_init_missing_openrouter_api_key(self, monkeypatch):
        """Test that missing OpenRouter API key raises ValueError."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        config = LLMConfig(provider="openrouter", model="test-model", api_key=None)

        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            SearchQualityJudge(config)

    @pytest.mark.unit
    def test_judge_init_unsupported_provider(self, monkeypatch):
        """Test that unsupported provider raises ValueError."""
        # We need to bypass Pydantic validation to test the judge's own validation
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        config = LLMConfig(provider="openai", model="test-model")
        # Manually override the provider to test the judge's validation
        config.provider = "unsupported_provider"  # type: ignore[assignment]

        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            SearchQualityJudge(config)


class TestSearchQualityJudgeEvaluate:
    """Tests for SearchQualityJudge.evaluate() method."""

    @pytest.fixture
    def mock_judge(self, monkeypatch):
        """Create a mock judge instance."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        with patch("agentic_search_audit.judge.judge.AsyncOpenAI"):
            config = LLMConfig(provider="openai", model="gpt-4o-mini")
            judge = SearchQualityJudge(config)
            return judge

    @pytest.fixture
    def sample_query(self):
        """Create a sample query for testing."""
        return Query(
            id="test-query-001",
            text="running shoes",
            lang="en",
            origin=QueryOrigin.PREDEFINED,
        )

    @pytest.fixture
    def sample_results(self):
        """Create sample results for testing."""
        return [
            ResultItem(
                rank=1,
                title="Nike Air Max",
                url="https://example.com/product/1",
                snippet="Premium running shoe",
                price="$120",
            ),
            ResultItem(
                rank=2,
                title="Adidas Ultraboost",
                url="https://example.com/product/2",
                snippet="Responsive cushioning",
                price="$180",
            ),
        ]

    @pytest.fixture
    def valid_judge_response(self):
        """Create a valid judge response JSON in FQI format."""
        return json.dumps(
            {
                "query_understanding": {"score": 4.5, "diagnosis": "Good query understanding"},
                "results_relevance": {"score": 4.8, "diagnosis": "Highly relevant results"},
                "result_presentation": {"score": 4.2, "diagnosis": "Well presented"},
                "advanced_features": {"score": 4.6, "diagnosis": "Rich feature set"},
                "error_handling": {"score": 4.0, "diagnosis": "Good error handling"},
                "rationale": "Excellent results matching the query intent.",
                "executive_summary": "Search performs well across all dimensions.",
                "issues": ["Minor: Could show more price ranges"],
                "improvements": ["Add filter by brand"],
                "evidence": [{"rank": 1, "reason": "Perfect match"}],
                "schema_version": "2.1",
            }
        )

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_evaluate_success(
        self, mock_judge, sample_query, sample_results, valid_judge_response
    ):
        """Test successful evaluation returns JudgeScore."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = valid_judge_response

        mock_judge.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await mock_judge.evaluate(
            query=sample_query,
            results=sample_results,
            page_url="https://example.com/search?q=running+shoes",
            html_content="<html><body>Search Results</body></html>",
            site_name="Example Store",
        )

        assert isinstance(result, JudgeScore)
        assert result.fqi > 0
        assert result.results_relevance.score == 4.8
        assert result.rationale == "Excellent results matching the query intent."

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_evaluate_empty_results(self, mock_judge, sample_query, valid_judge_response):
        """Test evaluation handles empty results list."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        # Modify response to reflect empty results scenario
        response_data = json.loads(valid_judge_response)
        response_data["query_understanding"]["score"] = 1.0
        response_data["results_relevance"]["score"] = 1.0
        response_data["rationale"] = "No results found."
        mock_response.choices[0].message.content = json.dumps(response_data)

        mock_judge.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await mock_judge.evaluate(
            query=sample_query,
            results=[],  # Empty results
            page_url="https://example.com/search?q=xyz",
            html_content="<html><body>No results</body></html>",
            site_name="Example Store",
        )

        assert isinstance(result, JudgeScore)
        assert result.fqi > 0  # FQI is computed from dimension scores

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_evaluate_large_html(
        self, mock_judge, sample_query, sample_results, valid_judge_response
    ):
        """Test evaluation truncates large HTML content."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = valid_judge_response

        mock_create = AsyncMock(return_value=mock_response)
        mock_judge.client.chat.completions.create = mock_create

        # Create HTML content larger than the limit
        large_html = "x" * 5000

        await mock_judge.evaluate(
            query=sample_query,
            results=sample_results,
            page_url="https://example.com/search",
            html_content=large_html,
            site_name="Example Store",
        )

        # Verify the LLM was called (prompt was built with truncated HTML)
        mock_create.assert_called_once()
        # The HTML snippet should be truncated to HTML_SNIPPET_MAX_CHARS
        assert len(large_html[:HTML_SNIPPET_MAX_CHARS]) == HTML_SNIPPET_MAX_CHARS


class TestSearchQualityJudgeCallLLM:
    """Tests for SearchQualityJudge._call_llm() method."""

    @pytest.fixture
    def mock_judge(self, monkeypatch):
        """Create a mock judge instance."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        with patch("agentic_search_audit.judge.judge.AsyncOpenAI"):
            config = LLMConfig(provider="openai", model="gpt-4o-mini")
            judge = SearchQualityJudge(config)
            return judge

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_call_llm_success(self, mock_judge):
        """Test successful LLM API call."""
        expected_response = '{"overall": 4.0}'
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = expected_response

        mock_judge.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await mock_judge._call_llm("Test prompt")

        assert result == expected_response
        mock_judge.client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_call_llm_timeout(self, mock_judge):
        """Test LLM API call timeout handling."""
        # Patch asyncio.wait_for to raise TimeoutError
        with patch("agentic_search_audit.judge.judge.asyncio.wait_for") as mock_wait_for:
            mock_wait_for.side_effect = asyncio.TimeoutError()

            with pytest.raises(TimeoutError, match="timed out"):
                await mock_judge._call_llm("Test prompt")

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_call_llm_api_error(self, mock_judge):
        """Test LLM API error propagation."""
        mock_judge.client.chat.completions.create = AsyncMock(
            side_effect=Exception("API Error: Rate limit exceeded")
        )

        with pytest.raises(Exception, match="API Error"):
            await mock_judge._call_llm("Test prompt")

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_call_llm_empty_response(self, mock_judge):
        """Test handling of empty/None LLM response."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        mock_judge.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await mock_judge._call_llm("Test prompt")

        assert result == ""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_call_llm_uses_custom_system_prompt(self, mock_judge):
        """Test that custom system prompt is used when provided."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"test": true}'

        mock_create = AsyncMock(return_value=mock_response)
        mock_judge.client.chat.completions.create = mock_create
        mock_judge.config.system_prompt = "Custom system prompt"

        await mock_judge._call_llm("Test prompt")

        call_args = mock_create.call_args
        system_message = call_args.kwargs["messages"][0]
        assert system_message["content"] == "Custom system prompt"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_call_llm_unsupported_provider(self, mock_judge):
        """Test that unsupported provider raises ValueError in _call_llm."""
        mock_judge.config.provider = "unsupported"  # type: ignore[assignment]

        with pytest.raises(ValueError, match="Unsupported provider"):
            await mock_judge._call_llm("Test prompt")


class TestSearchQualityJudgeParseResponse:
    """Tests for SearchQualityJudge._parse_response() method."""

    @pytest.fixture
    def mock_judge(self, monkeypatch):
        """Create a mock judge instance."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        with patch("agentic_search_audit.judge.judge.AsyncOpenAI"):
            config = LLMConfig(provider="openai", model="gpt-4o-mini")
            judge = SearchQualityJudge(config)
            return judge

    @pytest.mark.unit
    def test_parse_response_valid_json(self, mock_judge):
        """Test parsing valid JSON response."""
        response = json.dumps(
            {
                "query_understanding": {"score": 4.5, "diagnosis": "Good understanding"},
                "results_relevance": {"score": 4.8, "diagnosis": "Highly relevant"},
                "result_presentation": {"score": 4.2, "diagnosis": "Well presented"},
                "advanced_features": {"score": 4.6, "diagnosis": "Rich features"},
                "error_handling": {"score": 4.0, "diagnosis": "Good handling"},
                "rationale": "Excellent results",
                "issues": [],
                "improvements": [],
                "evidence": [{"rank": 1, "reason": "Good match"}],
                "schema_version": "2.1",
            }
        )

        result = mock_judge._parse_response(response)

        assert isinstance(result, JudgeScore)
        assert result.query_understanding.score == 4.5
        assert result.results_relevance.score == 4.8

    @pytest.mark.unit
    def test_parse_response_missing_required_field(self, mock_judge):
        """Test parsing response with missing required field raises ValueError."""
        response = json.dumps(
            {
                # Missing 'query_understanding' field
                "results_relevance": {"score": 4.8, "diagnosis": "Relevant"},
                "result_presentation": {"score": 4.2, "diagnosis": "Good"},
                "advanced_features": {"score": 4.6, "diagnosis": "Rich"},
                "error_handling": {"score": 4.0, "diagnosis": "OK"},
                "rationale": "Test",
                "issues": [],
                "improvements": [],
                "evidence": [],
                "schema_version": "2.1",
            }
        )

        with pytest.raises(ValueError, match="Missing required field: query_understanding"):
            mock_judge._parse_response(response)

    @pytest.mark.unit
    def test_parse_response_invalid_json(self, mock_judge):
        """Test parsing malformed JSON raises ValueError."""
        response = "{ invalid json content"

        with pytest.raises(ValueError, match="Invalid JSON response"):
            mock_judge._parse_response(response)

    @pytest.mark.unit
    def test_parse_response_score_out_of_bounds_upper(self, mock_judge):
        """Test parsing response with dimension score > 5 raises validation error."""
        response = json.dumps(
            {
                "query_understanding": {"score": 6.0, "diagnosis": "Invalid"},  # > 5
                "results_relevance": {"score": 4.8, "diagnosis": "OK"},
                "result_presentation": {"score": 4.2, "diagnosis": "OK"},
                "advanced_features": {"score": 4.6, "diagnosis": "OK"},
                "error_handling": {"score": 4.0, "diagnosis": "OK"},
                "rationale": "Test",
                "issues": [],
                "improvements": [],
                "evidence": [],
                "schema_version": "2.1",
            }
        )

        with pytest.raises(ValueError):
            mock_judge._parse_response(response)

    @pytest.mark.unit
    def test_parse_response_score_out_of_bounds_lower(self, mock_judge):
        """Test parsing response with dimension score < 0 raises validation error."""
        response = json.dumps(
            {
                "query_understanding": {"score": -1.0, "diagnosis": "Invalid"},  # < 0
                "results_relevance": {"score": 4.8, "diagnosis": "OK"},
                "result_presentation": {"score": 4.2, "diagnosis": "OK"},
                "advanced_features": {"score": 4.6, "diagnosis": "OK"},
                "error_handling": {"score": 4.0, "diagnosis": "OK"},
                "rationale": "Test",
                "issues": [],
                "improvements": [],
                "evidence": [],
                "schema_version": "2.1",
            }
        )

        with pytest.raises(ValueError):
            mock_judge._parse_response(response)

    @pytest.mark.unit
    def test_parse_response_empty_string(self, mock_judge):
        """Test parsing empty string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            mock_judge._parse_response("")


class TestSearchQualityJudgeBuildUserPrompt:
    """Tests for SearchQualityJudge._build_user_prompt() method."""

    @pytest.fixture
    def mock_judge(self, monkeypatch):
        """Create a mock judge instance."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        with patch("agentic_search_audit.judge.judge.AsyncOpenAI"):
            config = LLMConfig(provider="openai", model="gpt-4o-mini")
            judge = SearchQualityJudge(config)
            return judge

    @pytest.fixture
    def sample_query(self):
        """Create a sample query."""
        return Query(
            id="test-001",
            text="blue sneakers",
            lang="en",
            origin=QueryOrigin.PREDEFINED,
        )

    @pytest.fixture
    def sample_results(self):
        """Create sample results."""
        return [
            ResultItem(
                rank=1, title="Blue Nike Sneakers", url="https://example.com/1", price="$99"
            ),
            ResultItem(rank=2, title="Blue Adidas Shoes", url="https://example.com/2", price="$89"),
        ]

    @pytest.mark.unit
    def test_build_user_prompt_basic(self, mock_judge, sample_query, sample_results):
        """Test basic prompt construction with placeholder substitution."""
        prompt = mock_judge._build_user_prompt(
            query=sample_query,
            results=sample_results,
            page_url="https://example.com/search?q=blue+sneakers",
            html_content="<html><body>Results</body></html>",
            site_name="Example Store",
        )

        # Check key placeholders are substituted
        assert "Example Store" in prompt
        assert "blue sneakers" in prompt
        assert "2" in prompt  # num_results
        assert "Blue Nike Sneakers" in prompt
        assert "https://example.com/search?q=blue+sneakers" in prompt
        assert "<html><body>Results</body></html>" in prompt

    @pytest.mark.unit
    def test_build_user_prompt_html_truncation(self, mock_judge, sample_query, sample_results):
        """Test that HTML content > 2000 chars is truncated."""
        large_html = "x" * 5000

        prompt = mock_judge._build_user_prompt(
            query=sample_query,
            results=sample_results,
            page_url="https://example.com/search",
            html_content=large_html,
            site_name="Test Store",
        )

        # The large HTML should be truncated
        assert "x" * HTML_SNIPPET_MAX_CHARS in prompt
        assert "x" * (HTML_SNIPPET_MAX_CHARS + 100) not in prompt

    @pytest.mark.unit
    def test_build_user_prompt_empty_html(self, mock_judge, sample_query, sample_results):
        """Test handling of empty HTML content."""
        prompt = mock_judge._build_user_prompt(
            query=sample_query,
            results=sample_results,
            page_url="https://example.com/search",
            html_content="",
            site_name="Test Store",
        )

        # Should contain "N/A" for empty HTML
        assert "N/A" in prompt

    @pytest.mark.unit
    def test_build_user_prompt_none_html(self, mock_judge, sample_query, sample_results):
        """Test handling of None HTML content."""
        prompt = mock_judge._build_user_prompt(
            query=sample_query,
            results=sample_results,
            page_url="https://example.com/search",
            html_content=None,  # type: ignore[arg-type]
            site_name="Test Store",
        )

        # Should handle None gracefully
        assert "N/A" in prompt

    @pytest.mark.unit
    def test_build_user_prompt_empty_results(self, mock_judge, sample_query):
        """Test building prompt with empty results list."""
        prompt = mock_judge._build_user_prompt(
            query=sample_query,
            results=[],
            page_url="https://example.com/search",
            html_content="<html></html>",
            site_name="Test Store",
        )

        # Should include 0 for num_results
        assert "0" in prompt
