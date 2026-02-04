"""Vision model provider abstraction."""

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from openai import AsyncOpenAI

from ..core.types import LLMConfig

logger = logging.getLogger(__name__)

# Default timeout for vision API calls (in seconds)
# Vision calls may take longer due to image processing
DEFAULT_VISION_TIMEOUT_SECONDS = 90


class VisionProviderError(Exception):
    """Base exception for vision provider errors."""

    pass


class VisionParsingError(VisionProviderError):
    """Raised when JSON parsing of vision response fails."""

    def __init__(self, message: str, raw_content: str | None = None):
        super().__init__(message)
        self.raw_content = raw_content


class VisionTimeoutError(VisionProviderError):
    """Raised when vision API call times out."""

    pass


def _parse_json_response(content: str, provider_name: str) -> dict[str, Any]:
    """Parse JSON from LLM response with multiple fallback strategies.

    Args:
        content: Raw response content from LLM
        provider_name: Name of the provider (for logging)

    Returns:
        Parsed JSON as dictionary

    Raises:
        VisionParsingError: If JSON parsing fails after all attempts
    """
    if not content:
        raise VisionParsingError(f"{provider_name} returned empty content", raw_content=content)

    # Strategy 1: Direct JSON parse
    try:
        result: dict[str, Any] = json.loads(content)
        return result
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from ```json code block
    if "```json" in content:
        try:
            json_str = content.split("```json")[1].split("```")[0].strip()
            result = json.loads(json_str)
            return result
        except (IndexError, json.JSONDecodeError) as e:
            logger.debug(f"Failed to parse JSON from ```json block: {e}")

    # Strategy 3: Extract from generic ``` code block
    if "```" in content:
        try:
            json_str = content.split("```")[1].split("```")[0].strip()
            result = json.loads(json_str)
            return result
        except (IndexError, json.JSONDecodeError) as e:
            logger.debug(f"Failed to parse JSON from ``` block: {e}")

    # All strategies failed - log detailed error
    # Truncate content for logging to avoid huge log entries
    truncated_content = content[:500] + "..." if len(content) > 500 else content
    logger.error(
        f"Failed to parse JSON from {provider_name} response after all strategies. "
        f"Content preview: {truncated_content}"
    )

    raise VisionParsingError(
        f"Could not parse JSON from {provider_name} response. "
        "Response may not be valid JSON or may be in an unexpected format.",
        raw_content=content,
    )


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
        timeout_seconds = getattr(self.config, "timeout", None) or DEFAULT_VISION_TIMEOUT_SECONDS

        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
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
                ),
                timeout=timeout_seconds,
            )

            content = response.choices[0].message.content
            if not content:
                return None

            result: dict[str, Any] = json.loads(content)
            return result

        except asyncio.TimeoutError:
            logger.error(f"OpenAI vision API call timed out after {timeout_seconds}s")
            return None
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
        # Some vLLM deployments don't require API keys, so we allow empty string
        # But we log a warning to make configuration explicit
        api_key = config.api_key or os.getenv("VLLM_API_KEY")

        if not api_key:
            logger.warning(
                "No API key configured for vLLM provider. "
                "Set VLLM_API_KEY environment variable or api_key in config if your vLLM deployment requires authentication."
            )
            # Use placeholder for OpenAI client (vLLM often doesn't require a real key)
            api_key = "not-required"

        self.client = AsyncOpenAI(base_url=config.base_url, api_key=api_key)

        logger.info(
            f"Initialized vLLM provider with base_url: {config.base_url}, model: {config.model}"
        )

    async def analyze_image(
        self, screenshot_base64: str, prompt: str, max_tokens: int = 1000, temperature: float = 0.1
    ) -> dict[str, Any] | None:
        """Analyze image using vLLM vision model."""
        timeout_seconds = getattr(self.config, "timeout", None) or DEFAULT_VISION_TIMEOUT_SECONDS

        try:
            # vLLM uses OpenAI-compatible format
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
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
                ),
                timeout=timeout_seconds,
            )

            content = response.choices[0].message.content
            if not content:
                logger.warning("vLLM returned empty response content")
                return None

            # Parse JSON using common helper (handles multiple formats)
            try:
                return _parse_json_response(content, "vLLM")
            except VisionParsingError as e:
                # Log the error but return None to allow graceful degradation
                logger.error(str(e))
                return None

        except asyncio.TimeoutError:
            logger.error(f"vLLM vision API call timed out after {timeout_seconds}s")
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
        timeout_seconds = getattr(self.config, "timeout", None) or DEFAULT_VISION_TIMEOUT_SECONDS

        try:
            # OpenRouter uses OpenAI-compatible format
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
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
                ),
                timeout=timeout_seconds,
            )

            content = response.choices[0].message.content
            if not content:
                logger.warning("OpenRouter returned empty response content")
                return None

            # Parse JSON using common helper (handles multiple formats)
            try:
                return _parse_json_response(content, "OpenRouter")
            except VisionParsingError as e:
                # Log the error but return None to allow graceful degradation
                logger.error(str(e))
                return None

        except asyncio.TimeoutError:
            logger.error(f"OpenRouter vision API call timed out after {timeout_seconds}s")
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
        timeout_seconds = getattr(self.config, "timeout", None) or DEFAULT_VISION_TIMEOUT_SECONDS

        try:
            response = await asyncio.wait_for(
                self.client.messages.create(
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
                ),
                timeout=timeout_seconds,
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

            # Parse JSON using common helper (handles multiple formats)
            try:
                return _parse_json_response(content, "Anthropic")
            except VisionParsingError as e:
                # Log the error but return None to allow graceful degradation
                logger.error(str(e))
                return None

        except asyncio.TimeoutError:
            logger.error(f"Anthropic vision API call timed out after {timeout_seconds}s")
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
