"""Tests for LLM query generation."""

import json
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from agentic_search_audit.core.types import LLMConfig, QueryOrigin
from agentic_search_audit.generators.query_gen import (
    QueryGenerator,
    QueryIntent,
)


class TestQueryIntent:
    """Tests for QueryIntent enum."""

    def test_intent_values(self):
        """Test intent string values."""
        assert QueryIntent.HEAD_TERM.value == "head_term"
        assert QueryIntent.LONG_TAIL.value == "long_tail"
        assert QueryIntent.MISSPELLING.value == "misspelling"
        assert QueryIntent.SEMANTIC.value == "semantic"
        assert QueryIntent.ATTRIBUTE.value == "attribute"
        assert QueryIntent.BRAND.value == "brand"
        assert QueryIntent.NEGATIVE.value == "negative"


class TestQueryGenerator:
    """Tests for QueryGenerator class."""

    @pytest.fixture
    def openai_config(self):
        """Create OpenAI config for testing."""
        return LLMConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key="test-key",
        )

    @pytest.fixture
    def sample_html(self):
        """Sample HTML content for testing."""
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Test Store</title></head>
        <body>
            <nav>
                <a href="/shoes">Shoes</a>
                <a href="/clothing">Clothing</a>
            </nav>
            <main>
                <h1>Welcome to Test Store</h1>
                <div class="product">
                    <h2>Nike Running Shoes</h2>
                    <p class="price">$120</p>
                </div>
                <div class="product">
                    <h2>Adidas Sports T-Shirt</h2>
                    <p class="price">$45</p>
                </div>
            </main>
        </body>
        </html>
        """

    @pytest.fixture
    def sample_llm_response(self):
        """Sample LLM response for testing."""
        return {
            "site_category": "e-commerce/fashion",
            "detected_brands": ["Nike", "Adidas"],
            "detected_categories": ["Shoes", "Clothing"],
            "queries": [
                {
                    "text": "running shoes",
                    "intent": "head_term",
                    "reasoning": "Main product category visible on page",
                    "expected_results": True,
                },
                {
                    "text": "nike running shoes size 10",
                    "intent": "long_tail",
                    "reasoning": "Specific product with attributes",
                    "expected_results": True,
                },
                {
                    "text": "runing shoes",
                    "intent": "misspelling",
                    "reasoning": "Common typo for running",
                    "expected_results": True,
                },
                {
                    "text": "sneakers",
                    "intent": "semantic",
                    "reasoning": "Synonym for shoes",
                    "expected_results": True,
                },
                {
                    "text": "red shirt",
                    "intent": "attribute",
                    "reasoning": "Color attribute search",
                    "expected_results": True,
                },
                {
                    "text": "Nike",
                    "intent": "brand",
                    "reasoning": "Brand visible on page",
                    "expected_results": True,
                },
                {
                    "text": "asdfqwerty12345",
                    "intent": "negative",
                    "reasoning": "Nonsense query should return no results",
                    "expected_results": False,
                },
            ],
        }

    def test_init_openai(self, openai_config):
        """Test initialization with OpenAI config."""
        with patch("agentic_search_audit.generators.query_gen.AsyncOpenAI"):
            generator = QueryGenerator(openai_config)
            assert generator.config == openai_config

    def test_init_without_api_key_raises(self):
        """Test initialization without API key raises error."""
        config = LLMConfig(provider="openai", model="gpt-4o-mini", api_key=None)

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                QueryGenerator(config)

    def test_extract_relevant_html(self, openai_config, sample_html):
        """Test HTML extraction and cleaning."""
        with patch("agentic_search_audit.generators.query_gen.AsyncOpenAI"):
            generator = QueryGenerator(openai_config)
            cleaned = generator._extract_relevant_html(sample_html)

            # Should remove excessive whitespace
            assert "  " not in cleaned or len(cleaned) < len(sample_html)
            # Should preserve content
            assert "Nike Running Shoes" in cleaned

    def test_extract_relevant_html_truncation(self, openai_config):
        """Test HTML truncation to max chars."""
        with patch("agentic_search_audit.generators.query_gen.AsyncOpenAI"):
            generator = QueryGenerator(openai_config)
            long_html = "x" * 20000
            cleaned = generator._extract_relevant_html(long_html, max_chars=1000)

            assert len(cleaned) == 1000

    def test_parse_json_response_direct(self, openai_config, sample_llm_response):
        """Test parsing direct JSON response."""
        with patch("agentic_search_audit.generators.query_gen.AsyncOpenAI"):
            generator = QueryGenerator(openai_config)
            result = generator._parse_json_response(json.dumps(sample_llm_response))

            assert result is not None
            assert result["site_category"] == "e-commerce/fashion"
            assert len(result["queries"]) == 7

    def test_parse_json_response_markdown(self, openai_config, sample_llm_response):
        """Test parsing JSON from markdown code block."""
        with patch("agentic_search_audit.generators.query_gen.AsyncOpenAI"):
            generator = QueryGenerator(openai_config)
            content = f"Here is the result:\n```json\n{json.dumps(sample_llm_response)}\n```"
            result = generator._parse_json_response(content)

            assert result is not None
            assert len(result["queries"]) == 7

    def test_parse_response_to_queries(self, openai_config, sample_llm_response):
        """Test parsing response into Query objects."""
        with patch("agentic_search_audit.generators.query_gen.AsyncOpenAI"):
            generator = QueryGenerator(openai_config)
            queries = generator._parse_response(sample_llm_response, max_queries=10)

            assert len(queries) == 7
            assert queries[0].text == "running shoes"
            assert queries[0].origin == QueryOrigin.GENERATED
            assert "gen_head_term" in queries[0].id

    def test_parse_response_respects_max_queries(self, openai_config, sample_llm_response):
        """Test that max_queries limit is respected."""
        with patch("agentic_search_audit.generators.query_gen.AsyncOpenAI"):
            generator = QueryGenerator(openai_config)
            queries = generator._parse_response(sample_llm_response, max_queries=3)

            assert len(queries) == 3

    @pytest.mark.asyncio
    async def test_generate_from_html(self, openai_config, sample_html, sample_llm_response):
        """Test full query generation flow."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(sample_llm_response)

        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch(
            "agentic_search_audit.generators.query_gen.AsyncOpenAI", return_value=mock_client
        ):
            generator = QueryGenerator(openai_config)
            queries = await generator.generate_from_html(sample_html)

            assert len(queries) == 7
            assert all(q.origin == QueryOrigin.GENERATED for q in queries)

    @pytest.mark.asyncio
    async def test_generate_from_html_empty_response(self, openai_config, sample_html):
        """Test handling of empty LLM response."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch(
            "agentic_search_audit.generators.query_gen.AsyncOpenAI", return_value=mock_client
        ):
            generator = QueryGenerator(openai_config)
            queries = await generator.generate_from_html(sample_html)

            assert queries == []

    def test_save_queries(self, openai_config, sample_llm_response):
        """Test saving queries to JSON file."""
        with patch("agentic_search_audit.generators.query_gen.AsyncOpenAI"):
            generator = QueryGenerator(openai_config)
            queries = generator._parse_response(sample_llm_response, max_queries=10)

            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                output_path = f.name

            generator.save_queries(queries, output_path)

            # Read back and verify
            with open(output_path) as f:
                data = json.load(f)

            assert "queries" in data
            assert len(data["queries"]) == 7
            assert data["queries"][0]["text"] == "running shoes"
            assert data["queries"][0]["origin"] == "generated"


class TestQueryGeneratorProviders:
    """Tests for different LLM providers."""

    def test_init_vllm_requires_base_url(self):
        """Test vLLM provider requires base_url."""
        config = LLMConfig(provider="vllm", model="test-model")

        with pytest.raises(ValueError, match="base_url"):
            QueryGenerator(config)

    def test_init_vllm_with_base_url(self):
        """Test vLLM provider with base_url."""
        config = LLMConfig(
            provider="vllm",
            model="test-model",
            base_url="http://localhost:8000/v1",
        )

        with patch("agentic_search_audit.generators.query_gen.AsyncOpenAI"):
            generator = QueryGenerator(config)
            assert generator.client is not None

    def test_init_openrouter(self):
        """Test OpenRouter provider initialization."""
        config = LLMConfig(provider="openrouter", model="test-model", api_key="test-key")

        with patch("agentic_search_audit.generators.query_gen.AsyncOpenAI"):
            generator = QueryGenerator(config)
            assert generator.client is not None

    def test_init_anthropic(self):
        """Test Anthropic provider initialization."""
        config = LLMConfig(provider="anthropic", model="claude-3-sonnet", api_key="test-key")

        with patch("anthropic.AsyncAnthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client
            generator = QueryGenerator(config)
            assert generator.anthropic_client is not None
            assert generator.client is None

    def test_init_unsupported_provider_pydantic(self):
        """Test unsupported provider is caught by Pydantic validation."""
        # Pydantic's literal validation catches invalid provider values
        with pytest.raises(ValidationError):
            LLMConfig(provider="unsupported", model="test")
