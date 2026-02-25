"""LLM judge implementation."""

import asyncio
import json
import logging
import os
import random
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from ..core.types import JudgeScore, LLMConfig, Query, ResultItem
from .rubric import (
    JUDGE_SYSTEM_PROMPT,
    JUDGE_USER_PROMPT_TEMPLATE,
    format_results_for_judge,
    get_judge_schema,
)

if TYPE_CHECKING:
    from .rate_limiter import LLMRateLimiter

logger = logging.getLogger(__name__)

# Default timeout for LLM API calls (in seconds)
DEFAULT_LLM_TIMEOUT_SECONDS = 30

# Maximum characters of HTML content to include in judge prompt
# Longer content would exceed token limits and increase costs
HTML_SNIPPET_MAX_CHARS = 2000

# Retry configuration
JUDGE_MAX_RETRIES = 3
JUDGE_RETRY_BACKOFF_BASE = 2.0  # seconds


def _is_retryable_llm_error(exc: BaseException) -> bool:
    """Check if an LLM API error is worth retrying.

    Retries on: TimeoutError, HTTP 429 (rate limit), HTTP 502/503 (server error),
    connection errors.
    Does NOT retry on: 400 (bad request), 401/403 (auth), 404, JSON parse errors.
    """
    if isinstance(exc, TimeoutError | asyncio.TimeoutError):
        return True

    # OpenAI library errors
    try:
        from openai import APIConnectionError, APIStatusError

        if isinstance(exc, APIConnectionError):
            return True
        if isinstance(exc, APIStatusError):
            return exc.status_code in (429, 502, 503)
    except ImportError:
        pass

    # Anthropic library errors
    try:
        from anthropic import APIConnectionError as AnthropicConnectionError
        from anthropic import APIStatusError as AnthropicStatusError

        if isinstance(exc, AnthropicConnectionError):
            return True
        if isinstance(exc, AnthropicStatusError):
            return exc.status_code in (429, 502, 503)
    except ImportError:
        pass

    return False


class SearchQualityJudge:
    """LLM-based judge for search quality evaluation."""

    def __init__(
        self,
        config: LLMConfig,
        rate_limiter: "LLMRateLimiter | None" = None,
    ):
        """Initialize judge.

        Args:
            config: LLM configuration
            rate_limiter: Optional shared rate limiter for LLM API calls
        """
        self.config = config
        self.rate_limiter = rate_limiter
        self.client: Any = None
        self._anthropic_client: Any = None

        # Initialize LLM client
        if config.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            self.client = AsyncOpenAI(api_key=api_key)
        elif config.provider == "openrouter":
            # OpenRouter uses OpenAI-compatible API
            api_key = config.api_key or os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY environment variable not set and no api_key in config"
                )
            base_url = config.base_url or "https://openrouter.ai/api/v1"
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
            )
        elif config.provider == "anthropic":
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "anthropic package is required for Anthropic provider. "
                    "Install with: pip install anthropic"
                )
            api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY environment variable not set and no api_key in config"
                )
            self._anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
        elif config.provider == "vllm":
            if not config.base_url:
                raise ValueError("base_url must be specified in config for vLLM provider")
            api_key = config.api_key or os.getenv("VLLM_API_KEY")
            if not api_key:
                logger.warning(
                    "No API key configured for vLLM provider. "
                    "Set VLLM_API_KEY or api_key in config if your deployment requires auth."
                )
                api_key = "not-required"
            self.client = AsyncOpenAI(base_url=config.base_url, api_key=api_key)
        else:
            raise ValueError(f"Unsupported LLM provider: {config.provider}")

        self.schema = get_judge_schema()

    async def evaluate(
        self,
        query: Query,
        results: list[ResultItem],
        page_url: str,
        html_content: str,
        site_name: str,
        locale: str = "en-US",
    ) -> JudgeScore:
        """Evaluate search quality for a query.

        Args:
            query: Search query
            results: Extracted search results
            page_url: URL of search results page
            html_content: HTML content of page
            site_name: Name of site being evaluated
            locale: BCP-47 locale code for the target site

        Returns:
            Judge scores and evidence
        """
        logger.info(f"Evaluating query: {query.text}")

        # Prepare prompt
        user_prompt = self._build_user_prompt(
            query=query,
            results=results,
            page_url=page_url,
            html_content=html_content,
            site_name=site_name,
            locale=locale,
        )

        # Call LLM
        try:
            response = await self._call_llm(user_prompt)
            # Parse and validate response
            judge_score = self._parse_response(response)
        except Exception as e:
            logger.error(f"LLM evaluation failed for query '{query.text}': {e}")
            # Return degraded score so the audit can continue
            from ..core.types import DimensionDiagnosis

            judge_score = JudgeScore(
                query_understanding=DimensionDiagnosis(score=0, diagnosis="LLM evaluation failed"),
                results_relevance=DimensionDiagnosis(score=0, diagnosis="LLM evaluation failed"),
                result_presentation=DimensionDiagnosis(score=0, diagnosis="LLM evaluation failed"),
                advanced_features=DimensionDiagnosis(score=0, diagnosis="LLM evaluation failed"),
                error_handling=DimensionDiagnosis(score=0, diagnosis="LLM evaluation failed"),
                rationale=f"LLM evaluation failed: {e}",
                issues=["LLM evaluation failed -- scores are degraded"],
            )

        logger.info(f"Evaluation complete. FQI score: {judge_score.fqi:.2f}")

        return judge_score

    def _build_user_prompt(
        self,
        query: Query,
        results: list[ResultItem],
        page_url: str,
        html_content: str,
        site_name: str,
        locale: str = "en-US",
    ) -> str:
        """Build user prompt for judge.

        Args:
            query: Search query
            results: Search results
            page_url: Results page URL
            html_content: Page HTML
            site_name: Site name
            locale: BCP-47 locale code for the target site

        Returns:
            Formatted prompt
        """
        # Truncate HTML to avoid token limits
        html_snippet = html_content[:HTML_SNIPPET_MAX_CHARS] if html_content else "N/A"

        # Format results
        results_json = format_results_for_judge(results)

        # Build prompt
        prompt = JUDGE_USER_PROMPT_TEMPLATE.format(
            site_name=site_name,
            query_text=query.text,
            num_results=len(results),
            results_json=results_json,
            page_url=page_url,
            html_snippet=html_snippet,
            locale=locale,
        )

        return prompt

    async def _call_llm(self, user_prompt: str) -> str:
        """Call LLM for evaluation with retry logic.

        Retries on transient failures (429, 502/503, timeouts, connection errors)
        with exponential backoff. Does NOT retry on auth errors or bad requests.

        Args:
            user_prompt: User prompt

        Returns:
            LLM response text

        Raises:
            TimeoutError: If all retry attempts time out
            ValueError: If the provider is not supported
        """
        last_exc: BaseException | None = None

        for attempt in range(JUDGE_MAX_RETRIES):
            try:
                if self.rate_limiter:
                    async with self.rate_limiter.acquire():
                        return await self._call_llm_once(user_prompt)
                else:
                    return await self._call_llm_once(user_prompt)
            except Exception as e:
                last_exc = e
                if not _is_retryable_llm_error(e) or attempt >= JUDGE_MAX_RETRIES - 1:
                    raise
                backoff = JUDGE_RETRY_BACKOFF_BASE * (2**attempt) * random.uniform(0.7, 1.3)
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1,
                    JUDGE_MAX_RETRIES,
                    e,
                    backoff,
                )
                await asyncio.sleep(backoff)

        # Should not reach here, but just in case
        raise last_exc or RuntimeError("LLM call failed with no exception")  # type: ignore[misc]

    async def _call_llm_once(self, user_prompt: str) -> str:
        """Execute a single LLM API call (no retry).

        Args:
            user_prompt: User prompt

        Returns:
            LLM response text
        """
        logger.debug("Calling LLM for evaluation...")

        timeout_seconds = getattr(self.config, "timeout", None) or DEFAULT_LLM_TIMEOUT_SECONDS

        if self.config.provider in ["openai", "openrouter", "vllm"]:
            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.config.model,
                        messages=[
                            {
                                "role": "system",
                                "content": self.config.system_prompt or JUDGE_SYSTEM_PROMPT,
                            },
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=self.config.temperature,
                        max_tokens=self.config.max_tokens,
                        response_format={"type": "json_object"},
                        seed=self.config.seed if hasattr(self.config, "seed") else None,
                    ),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"LLM evaluation timed out after {timeout_seconds} seconds. "
                    "The API may be overloaded or experiencing issues."
                )

            return response.choices[0].message.content or ""

        if self.config.provider == "anthropic":
            system_prompt = self.config.system_prompt or JUDGE_SYSTEM_PROMPT
            try:
                response = await asyncio.wait_for(
                    self._anthropic_client.messages.create(
                        model=self.config.model,
                        max_tokens=self.config.max_tokens,
                        system=system_prompt,
                        messages=[
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=self.config.temperature,
                    ),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"LLM evaluation timed out after {timeout_seconds} seconds. "
                    "The API may be overloaded or experiencing issues."
                )

            for block in response.content:
                if block.type == "text":
                    return str(block.text)
            return ""

        raise ValueError(f"Unsupported provider: {self.config.provider}")

    def _parse_response(self, response: str) -> JudgeScore:
        """Parse and validate LLM response.

        Args:
            response: Raw LLM response

        Returns:
            Validated JudgeScore

        Raises:
            ValueError: If response is invalid
        """
        try:
            # Parse JSON
            data = json.loads(response)

            # Validate against schema (basic check)
            required_fields = self.schema["required"]
            for field in required_fields:
                if field not in data:
                    logger.error(
                        f"Response missing field '{field}'. Got fields: {list(data.keys())}"
                    )
                    logger.debug(f"Full response data: {data}")
                    raise ValueError(f"Missing required field: {field}")

            # Create JudgeScore object (Pydantic will validate)
            judge_score = JudgeScore(**data)

            return judge_score

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response: {response}")
            raise ValueError(f"Invalid JSON response: {e}") from e

        except Exception as e:
            logger.error(f"Failed to validate response: {e}")
            raise ValueError(f"Invalid response: {e}") from e
