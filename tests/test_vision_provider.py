"""Tests for vision provider implementations."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_search_audit.core.types import LLMConfig


class TestOpenAIVisionProvider:
    """Tests for OpenAI vision provider."""

    @pytest.fixture
    def config(self):
        """Create OpenAI config for testing."""
        return LLMConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key="test-key",
        )

    def test_init_with_api_key(self, config):
        """Test initialization with API key."""
        from agentic_search_audit.extractors.vision_provider import OpenAIVisionProvider

        provider = OpenAIVisionProvider(config)
        assert provider.config == config

    def test_init_without_api_key_raises(self):
        """Test initialization without API key raises error."""
        from agentic_search_audit.extractors.vision_provider import OpenAIVisionProvider

        config = LLMConfig(provider="openai", model="gpt-4o-mini", api_key=None)

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                OpenAIVisionProvider(config)

    @pytest.mark.asyncio
    async def test_analyze_image_success(self, config):
        """Test successful image analysis."""
        from agentic_search_audit.extractors.vision_provider import OpenAIVisionProvider

        expected_response = {
            "selectors": ["input[type='search']"],
            "confidence": "high",
        }

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(expected_response)

        with patch("openai.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            provider = OpenAIVisionProvider(config)
            result = await provider.analyze_image(
                screenshot_base64="base64data",
                prompt="Find the search box",
            )

            assert result == expected_response

    @pytest.mark.asyncio
    async def test_analyze_image_empty_content(self, config):
        """Test handling of empty content response."""
        from agentic_search_audit.extractors.vision_provider import OpenAIVisionProvider

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        with patch("openai.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            provider = OpenAIVisionProvider(config)
            result = await provider.analyze_image(
                screenshot_base64="base64data",
                prompt="Find the search box",
            )

            assert result is None


class TestAnthropicVisionProvider:
    """Tests for Anthropic vision provider."""

    @pytest.fixture
    def config(self):
        """Create Anthropic config for testing."""
        return LLMConfig(
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            api_key="test-key",
        )

    def test_init_with_api_key(self, config):
        """Test initialization with API key."""
        with patch("anthropic.AsyncAnthropic") as mock_client_class:
            from agentic_search_audit.extractors.vision_provider import AnthropicVisionProvider

            provider = AnthropicVisionProvider(config)
            assert provider.config == config
            mock_client_class.assert_called_once_with(api_key="test-key")

    def test_init_without_api_key_raises(self):
        """Test initialization without API key raises error."""
        config = LLMConfig(provider="anthropic", model="claude-3-5-sonnet-20241022", api_key=None)

        with patch("anthropic.AsyncAnthropic"):
            with patch.dict("os.environ", {}, clear=True):
                from agentic_search_audit.extractors.vision_provider import AnthropicVisionProvider

                with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                    AnthropicVisionProvider(config)

    @pytest.mark.asyncio
    async def test_analyze_image_success(self, config):
        """Test successful image analysis."""
        expected_response = {
            "selectors": ["input[type='search']"],
            "confidence": "high",
        }

        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = json.dumps(expected_response)

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]

        with patch("anthropic.AsyncAnthropic") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            from agentic_search_audit.extractors.vision_provider import AnthropicVisionProvider

            provider = AnthropicVisionProvider(config)
            result = await provider.analyze_image(
                screenshot_base64="base64data",
                prompt="Find the search box",
            )

            assert result == expected_response

    @pytest.mark.asyncio
    async def test_analyze_image_with_markdown_json(self, config):
        """Test parsing JSON from markdown code block."""
        expected_response = {
            "selectors": ["input[type='search']"],
            "confidence": "high",
        }

        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = f"Here is the result:\n```json\n{json.dumps(expected_response)}\n```"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]

        with patch("anthropic.AsyncAnthropic") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            from agentic_search_audit.extractors.vision_provider import AnthropicVisionProvider

            provider = AnthropicVisionProvider(config)
            result = await provider.analyze_image(
                screenshot_base64="base64data",
                prompt="Find the search box",
            )

            assert result == expected_response

    @pytest.mark.asyncio
    async def test_analyze_image_empty_content(self, config):
        """Test handling of empty content response."""
        mock_response = MagicMock()
        mock_response.content = []

        with patch("anthropic.AsyncAnthropic") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            from agentic_search_audit.extractors.vision_provider import AnthropicVisionProvider

            provider = AnthropicVisionProvider(config)
            result = await provider.analyze_image(
                screenshot_base64="base64data",
                prompt="Find the search box",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_analyze_image_api_error(self, config):
        """Test handling of API errors."""
        with patch("anthropic.AsyncAnthropic") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.messages.create.side_effect = Exception("API error")
            mock_client_class.return_value = mock_client

            from agentic_search_audit.extractors.vision_provider import AnthropicVisionProvider

            provider = AnthropicVisionProvider(config)
            result = await provider.analyze_image(
                screenshot_base64="base64data",
                prompt="Find the search box",
            )

            assert result is None


class TestCreateVisionProvider:
    """Tests for create_vision_provider factory function."""

    def test_create_openai_provider(self):
        """Test creating OpenAI provider."""
        from agentic_search_audit.extractors.vision_provider import (
            OpenAIVisionProvider,
            create_vision_provider,
        )

        config = LLMConfig(provider="openai", model="gpt-4o", api_key="test-key")
        provider = create_vision_provider(config)

        assert isinstance(provider, OpenAIVisionProvider)

    def test_create_anthropic_provider(self):
        """Test creating Anthropic provider."""
        with patch("anthropic.AsyncAnthropic"):
            from agentic_search_audit.extractors.vision_provider import (
                AnthropicVisionProvider,
                create_vision_provider,
            )

            config = LLMConfig(
                provider="anthropic", model="claude-3-5-sonnet-20241022", api_key="test-key"
            )
            provider = create_vision_provider(config)

            assert isinstance(provider, AnthropicVisionProvider)

    def test_create_vllm_provider(self):
        """Test creating vLLM provider."""
        from agentic_search_audit.extractors.vision_provider import (
            VLLMVisionProvider,
            create_vision_provider,
        )

        config = LLMConfig(
            provider="vllm",
            model="llava-hf/llava-v1.6-mistral-7b-hf",
            base_url="http://localhost:8000/v1",
        )
        provider = create_vision_provider(config)

        assert isinstance(provider, VLLMVisionProvider)

    def test_create_openrouter_provider(self):
        """Test creating OpenRouter provider."""
        from agentic_search_audit.extractors.vision_provider import (
            OpenRouterVisionProvider,
            create_vision_provider,
        )

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            config = LLMConfig(
                provider="openrouter",
                model="qwen/qwen-vl-plus",
            )
            provider = create_vision_provider(config)

            assert isinstance(provider, OpenRouterVisionProvider)

    def test_create_unsupported_provider_raises(self):
        """Test that unsupported provider raises error."""
        from agentic_search_audit.extractors.vision_provider import create_vision_provider

        config = LLMConfig(provider="unsupported", model="test")  # type: ignore

        with pytest.raises(ValueError, match="Unsupported vision provider"):
            create_vision_provider(config)
