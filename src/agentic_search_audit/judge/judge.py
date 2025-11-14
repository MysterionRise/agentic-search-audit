"""LLM judge implementation."""

import json
import logging
import os

from openai import AsyncOpenAI

from ..core.types import JudgeScore, LLMConfig, Query, ResultItem
from .rubric import (
    JUDGE_SYSTEM_PROMPT,
    JUDGE_USER_PROMPT_TEMPLATE,
    format_results_for_judge,
    get_judge_schema,
)

logger = logging.getLogger(__name__)


class SearchQualityJudge:
    """LLM-based judge for search quality evaluation."""

    def __init__(self, config: LLMConfig):
        """Initialize judge.

        Args:
            config: LLM configuration
        """
        self.config = config

        # Initialize LLM client
        if config.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            self.client = AsyncOpenAI(api_key=api_key)
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
    ) -> JudgeScore:
        """Evaluate search quality for a query.

        Args:
            query: Search query
            results: Extracted search results
            page_url: URL of search results page
            html_content: HTML content of page
            site_name: Name of site being evaluated

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
        )

        # Call LLM
        response = await self._call_llm(user_prompt)

        # Parse and validate response
        judge_score = self._parse_response(response)

        logger.info(f"Evaluation complete. Overall score: {judge_score.overall:.2f}")

        return judge_score

    def _build_user_prompt(
        self,
        query: Query,
        results: list[ResultItem],
        page_url: str,
        html_content: str,
        site_name: str,
    ) -> str:
        """Build user prompt for judge.

        Args:
            query: Search query
            results: Search results
            page_url: Results page URL
            html_content: Page HTML
            site_name: Site name

        Returns:
            Formatted prompt
        """
        # Truncate HTML to avoid token limits
        html_snippet = html_content[:2000] if html_content else "N/A"

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
        )

        return prompt

    async def _call_llm(self, user_prompt: str) -> str:
        """Call LLM for evaluation.

        Args:
            user_prompt: User prompt

        Returns:
            LLM response text
        """
        logger.debug("Calling LLM for evaluation...")

        if self.config.provider == "openai":
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": self.config.system_prompt or JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                response_format={"type": "json_object"},
                seed=self.config.seed if hasattr(self.config, "seed") else None,
            )

            return response.choices[0].message.content or ""

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
