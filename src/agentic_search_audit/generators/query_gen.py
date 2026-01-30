"""LLM-based query generation from website content."""

import json
import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from openai import AsyncOpenAI

from ..core.types import LLMConfig, Query, QueryOrigin

logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    """Query intent categories for comprehensive coverage."""

    HEAD_TERM = "head_term"  # High-volume, general product categories
    LONG_TAIL = "long_tail"  # Specific, detailed queries
    MISSPELLING = "misspelling"  # Intentional typos to test tolerance
    SEMANTIC = "semantic"  # Synonyms and related terms
    ATTRIBUTE = "attribute"  # Product attributes (color, size, price)
    BRAND = "brand"  # Brand-specific searches
    NEGATIVE = "negative"  # Queries that should return no results


@dataclass
class GeneratedQuery:
    """A generated query with metadata."""

    text: str
    intent: QueryIntent
    reasoning: str
    expected_results: bool = True


QUERY_GENERATION_PROMPT = """You are a search quality expert analyzing a website to generate test search queries.

Analyze the following homepage HTML content and generate diverse search queries that would help evaluate the site's search functionality.

Generate exactly 26 queries distributed across these 7 intent categories:

1. **Head Terms (4 queries)**: High-volume, general product/content categories visible on the page
   Example: "running shoes", "laptops", "dresses"

2. **Long Tail (4 queries)**: Specific, detailed queries that combine multiple attributes
   Example: "waterproof hiking boots size 10", "wireless noise cancelling headphones under $200"

3. **Misspellings (4 queries)**: Common typos and misspellings to test typo tolerance
   Example: "nikey shoes" (nike), "samung phone" (samsung), "runing shoes" (running)

4. **Semantic (4 queries)**: Synonyms and related terms that should match products
   Example: "sneakers" for shoes, "notebook" for laptop, "couch" for sofa

5. **Attribute (4 queries)**: Queries focused on specific attributes
   Example: "red dress", "size large t-shirt", "under $50 gifts"

6. **Brand (4 queries)**: Brand-specific searches (extract brands from the page)
   Example: "Nike", "Apple iPhone", "Samsung TV"

7. **Negative (2 queries)**: Queries that should return no results (nonsense or out-of-scope)
   Example: "asdfqwerty12345", "buy elephants online"

Guidelines:
- Base queries on actual content visible in the HTML (product names, categories, brands)
- Make queries realistic - what would real users search for?
- For misspellings, use common typo patterns (swapped letters, missing letters, phonetic errors)
- For semantic queries, use synonyms that real users might use
- Ensure diversity - don't repeat similar queries

Return your response as a JSON object with this structure:
{{
    "site_category": "e-commerce/fashion/electronics/etc",
    "detected_brands": ["brand1", "brand2"],
    "detected_categories": ["category1", "category2"],
    "queries": [
        {{
            "text": "the search query",
            "intent": "head_term|long_tail|misspelling|semantic|attribute|brand|negative",
            "reasoning": "why this query was chosen",
            "expected_results": true/false
        }}
    ]
}}

HTML Content (first 15000 characters):
{html_content}
"""


class QueryGenerator:
    """Generates search queries using LLM analysis of website content."""

    def __init__(self, llm_config: LLMConfig):
        """Initialize query generator.

        Args:
            llm_config: LLM configuration
        """
        self.config = llm_config
        self._init_client()

    def _init_client(self) -> None:
        """Initialize the appropriate LLM client based on config."""
        if self.config.provider == "openai":
            api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set")
            self.client = AsyncOpenAI(api_key=api_key)

        elif self.config.provider == "openrouter":
            api_key = self.config.api_key or os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY not set")
            base_url = self.config.base_url or "https://openrouter.ai/api/v1"
            self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)

        elif self.config.provider == "anthropic":
            # For Anthropic, we'll use the messages API differently
            try:
                import anthropic

                api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY not set")
                self.anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
                self.client = None
            except ImportError:
                raise ImportError("anthropic package required for Anthropic provider")

        elif self.config.provider == "vllm":
            if not self.config.base_url:
                raise ValueError("base_url required for vLLM provider")
            api_key = self.config.api_key or os.getenv("VLLM_API_KEY", "EMPTY")
            self.client = AsyncOpenAI(base_url=self.config.base_url, api_key=api_key)

        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

    async def generate_from_html(
        self,
        html_content: str,
        max_queries: int = 26,
    ) -> list[Query]:
        """Generate queries from HTML content.

        Args:
            html_content: Homepage HTML content
            max_queries: Maximum number of queries to generate

        Returns:
            List of generated Query objects
        """
        logger.info("Generating queries from HTML content using LLM...")

        # Truncate HTML to reasonable size
        html_snippet = self._extract_relevant_html(html_content)

        # Build prompt
        prompt = QUERY_GENERATION_PROMPT.format(html_content=html_snippet)

        # Call LLM
        result = await self._call_llm(prompt)

        if not result:
            logger.error("Failed to generate queries from LLM")
            return []

        # Parse and convert to Query objects
        queries = self._parse_response(result, max_queries)

        logger.info(f"Generated {len(queries)} queries")
        return queries

    async def generate_from_homepage(
        self,
        homepage_html: str,
        include_intents: list[QueryIntent] | None = None,
    ) -> list[Query]:
        """Generate queries optimized for a specific homepage.

        Args:
            homepage_html: Homepage HTML content
            include_intents: Optional list of intents to include (all if None)

        Returns:
            List of generated Query objects
        """
        queries = await self.generate_from_html(homepage_html)

        if include_intents:
            intent_values = {i.value for i in include_intents}
            queries = [
                q
                for q in queries
                if any(intent in q.id for intent in intent_values)
            ]

        return queries

    def _extract_relevant_html(self, html_content: str, max_chars: int = 15000) -> str:
        """Extract relevant portions of HTML for analysis.

        Args:
            html_content: Full HTML content
            max_chars: Maximum characters to extract

        Returns:
            Cleaned HTML snippet
        """
        # Remove script and style tags
        html_content = re.sub(
            r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE
        )
        html_content = re.sub(
            r"<style[^>]*>.*?</style>", "", html_content, flags=re.DOTALL | re.IGNORECASE
        )

        # Remove HTML comments
        html_content = re.sub(r"<!--.*?-->", "", html_content, flags=re.DOTALL)

        # Remove excessive whitespace
        html_content = re.sub(r"\s+", " ", html_content)

        # Truncate to max chars
        return html_content[:max_chars]

    async def _call_llm(self, prompt: str) -> dict[str, Any] | None:
        """Call LLM with prompt.

        Args:
            prompt: Text prompt

        Returns:
            Parsed JSON response or None
        """
        try:
            if self.config.provider == "anthropic":
                return await self._call_anthropic(prompt)
            else:
                return await self._call_openai_compatible(prompt)

        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            return None

    async def _call_openai_compatible(self, prompt: str) -> dict[str, Any] | None:
        """Call OpenAI-compatible API."""
        response = await self.client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.config.max_tokens or 2000,
            temperature=self.config.temperature or 0.3,
        )

        content = response.choices[0].message.content
        if not content:
            return None

        return self._parse_json_response(content)

    async def _call_anthropic(self, prompt: str) -> dict[str, Any] | None:
        """Call Anthropic API."""
        response = await self.anthropic_client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens or 2000,
            messages=[{"role": "user", "content": prompt}],
        )

        content = ""
        for block in response.content:
            if block.type == "text":
                content = block.text
                break

        if not content:
            return None

        return self._parse_json_response(content)

    def _parse_json_response(self, content: str) -> dict[str, Any] | None:
        """Parse JSON from LLM response."""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                return json.loads(json_str)
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
                return json.loads(json_str)
            else:
                logger.error(f"Failed to parse JSON from response: {content[:500]}")
                return None

    def _parse_response(self, result: dict[str, Any], max_queries: int) -> list[Query]:
        """Parse LLM response into Query objects.

        Args:
            result: Parsed JSON response
            max_queries: Maximum queries to return

        Returns:
            List of Query objects
        """
        queries = []

        raw_queries = result.get("queries", [])
        for i, q in enumerate(raw_queries[:max_queries], 1):
            intent = q.get("intent", "head_term")
            query = Query(
                id=f"gen_{intent}_{i:03d}",
                text=q.get("text", ""),
                lang="en",
                origin=QueryOrigin.GENERATED,
            )
            queries.append(query)

        return queries

    def save_queries(self, queries: list[Query], output_path: str) -> None:
        """Save generated queries to JSON file.

        Args:
            queries: List of queries
            output_path: Path to save JSON file
        """
        data = {
            "queries": [
                {
                    "id": q.id,
                    "text": q.text,
                    "lang": q.lang,
                    "origin": q.origin.value,
                }
                for q in queries
            ]
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved {len(queries)} queries to {output_path}")
