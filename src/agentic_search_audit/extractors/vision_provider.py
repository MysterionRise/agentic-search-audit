"""Vision model provider abstraction."""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from openai import AsyncOpenAI

from ..core.types import LLMConfig

logger = logging.getLogger(__name__)


class VisionProvider(ABC):
    """Abstract base class for vision model providers."""

    @abstractmethod
    async def analyze_image(
        self, screenshot_base64: str, prompt: str, max_tokens: int = 1000, temperature: float = 0.1
    ) -> dict[str, Any] | None:
        """Analyze an image with a vision model.

        Args:
            screenshot_base64: Base64-encoded image
            prompt: Text prompt for analysis
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            Parsed JSON response or None on error
        """
        pass


class OpenAIVisionProvider(VisionProvider):
    """OpenAI vision model provider (gpt-4o, gpt-4o-mini, etc.)."""

    def __init__(self, config: LLMConfig):
        """Initialize OpenAI provider.

        Args:
            config: LLM configuration
        """
        self.config = config
        api_key = config.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in config or environment")

        self.client = AsyncOpenAI(api_key=api_key)

    async def analyze_image(
        self, screenshot_base64: str, prompt: str, max_tokens: int = 1000, temperature: float = 0.1
    ) -> dict[str, Any] | None:
        """Analyze image using OpenAI vision model."""
        try:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{screenshot_base64}",
                                    "detail": "high",
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                return None

            result: dict[str, Any] = json.loads(content)
            return result

        except Exception as e:
            logger.error(f"OpenAI vision analysis failed: {e}")
            return None


class VLLMVisionProvider(VisionProvider):
    """vLLM vision model provider (LLaVA, Qwen-VL, etc. via OpenAI-compatible API)."""

    def __init__(self, config: LLMConfig):
        """Initialize vLLM provider.

        Args:
            config: LLM configuration with base_url specified
        """
        self.config = config

        if not config.base_url:
            raise ValueError("base_url must be specified in config for vLLM provider")

        # vLLM supports OpenAI-compatible API
        api_key = config.api_key or os.getenv("VLLM_API_KEY", "EMPTY")

        self.client = AsyncOpenAI(base_url=config.base_url, api_key=api_key)

        logger.info(
            f"Initialized vLLM provider with base_url: {config.base_url}, model: {config.model}"
        )

    async def analyze_image(
        self, screenshot_base64: str, prompt: str, max_tokens: int = 1000, temperature: float = 0.1
    ) -> dict[str, Any] | None:
        """Analyze image using vLLM vision model."""
        try:
            # vLLM uses OpenAI-compatible format
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{screenshot_base64}",
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                # Note: vLLM might not support response_format for all models
                # We'll try to parse JSON from the response
            )

            content = response.choices[0].message.content
            if not content:
                return None

            # Try to parse as JSON
            # Some vLLM models might not support strict JSON mode
            try:
                result: dict[str, Any] = json.loads(content)
                return result
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                    result = json.loads(json_str)
                    return result  # type: ignore[return-value]
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                    result = json.loads(json_str)
                    return result  # type: ignore[return-value]
                else:
                    logger.error(f"Failed to parse JSON from vLLM response: {content}")
                    return None

        except Exception as e:
            logger.error(f"vLLM vision analysis failed: {e}", exc_info=True)
            return None


class OpenRouterVisionProvider(VisionProvider):
    """OpenRouter vision model provider (Qwen-VL, GPT-4V, etc. via unified API)."""

    def __init__(self, config: LLMConfig):
        """Initialize OpenRouter provider.

        Args:
            config: LLM configuration
        """
        self.config = config

        # Default base URL for OpenRouter
        base_url = config.base_url or "https://openrouter.ai/api/v1"

        # Get API key from config or environment
        api_key = config.api_key or os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set in config or environment")

        # OpenRouter uses OpenAI-compatible API
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "https://github.com/agentic-search-audit",  # Optional, for tracking
                "X-Title": "Agentic Search Audit",  # Optional, for tracking
            },
        )

        logger.info(
            f"Initialized OpenRouter provider with base_url: {base_url}, model: {config.model}"
        )

    async def analyze_image(
        self, screenshot_base64: str, prompt: str, max_tokens: int = 1000, temperature: float = 0.1
    ) -> dict[str, Any] | None:
        """Analyze image using OpenRouter vision model."""
        try:
            # OpenRouter uses OpenAI-compatible format
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{screenshot_base64}",
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            content = response.choices[0].message.content
            if not content:
                return None

            # Try to parse as JSON
            # Some models might not support strict JSON mode
            try:
                result: dict[str, Any] = json.loads(content)
                return result
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                    result = json.loads(json_str)
                    return result  # type: ignore[return-value]
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                    result = json.loads(json_str)
                    return result  # type: ignore[return-value]
                else:
                    logger.error(f"Failed to parse JSON from OpenRouter response: {content}")
                    return None

        except Exception as e:
            logger.error(f"OpenRouter vision analysis failed: {e}", exc_info=True)
            return None


class AnthropicVisionProvider(VisionProvider):
    """Anthropic vision model provider (Claude 3.5 Sonnet, Claude 3 Opus, etc.)."""

    def __init__(self, config: LLMConfig):
        """Initialize Anthropic provider.

        Args:
            config: LLM configuration
        """
        self.config = config

        # Import anthropic here to avoid requiring it when not using this provider
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package is required for Anthropic vision provider. "
                "Install with: pip install anthropic"
            )

        api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in config or environment")

        self.client = anthropic.AsyncAnthropic(api_key=api_key)

        logger.info(f"Initialized Anthropic provider with model: {config.model}")

    async def analyze_image(
        self, screenshot_base64: str, prompt: str, max_tokens: int = 1000, temperature: float = 0.1
    ) -> dict[str, Any] | None:
        """Analyze image using Anthropic vision model (Claude 3+).

        Args:
            screenshot_base64: Base64-encoded PNG image
            prompt: Text prompt for analysis
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            Parsed JSON response or None on error
        """
        try:
            response = await self.client.messages.create(
                model=self.config.model,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": screenshot_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
            )

            # Extract text content from response
            content = ""
            for block in response.content:
                if block.type == "text":
                    content = block.text
                    break

            if not content:
                logger.warning("Anthropic response contained no text content")
                return None

            # Try to parse as JSON
            try:
                result: dict[str, Any] = json.loads(content)
                return result
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0].strip()
                    result = json.loads(json_str)
                    return result  # type: ignore[return-value]
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0].strip()
                    result = json.loads(json_str)
                    return result  # type: ignore[return-value]
                else:
                    logger.error(f"Failed to parse JSON from Anthropic response: {content}")
                    return None

        except Exception as e:
            logger.error(f"Anthropic vision analysis failed: {e}", exc_info=True)
            return None


def create_vision_provider(config: LLMConfig) -> VisionProvider:
    """Factory function to create vision provider based on config.

    Args:
        config: LLM configuration

    Returns:
        Appropriate vision provider instance

    Raises:
        ValueError: If provider is not supported
    """
    if config.provider == "openai":
        return OpenAIVisionProvider(config)
    elif config.provider == "vllm":
        return VLLMVisionProvider(config)
    elif config.provider == "openrouter":
        return OpenRouterVisionProvider(config)
    elif config.provider == "anthropic":
        return AnthropicVisionProvider(config)
    else:
        raise ValueError(f"Unsupported vision provider: {config.provider}")
