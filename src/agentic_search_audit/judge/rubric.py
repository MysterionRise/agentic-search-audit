"""Judge rubric and prompts."""

import json
from typing import Any

JUDGE_SYSTEM_PROMPT = """You are a search quality evaluator analyzing on-site search results.

Your task is to objectively evaluate search quality based on the provided results and page context.

## Evaluation Criteria (0-5 scale for each):

1. **Relevance** (0-5): How well do the results match the search intent?
   - 5: Perfect match, all results highly relevant
   - 4: Most results relevant with minor issues
   - 3: Mixed relevance, some good results
   - 2: Mostly irrelevant with few relevant results
   - 1: Barely relevant results
   - 0: Completely irrelevant or no results

2. **Diversity** (0-5): Do results show variety in brands, categories, and price points?
   - 5: Excellent variety across multiple dimensions
   - 4: Good diversity with minor gaps
   - 3: Some diversity but noticeable clustering
   - 2: Limited diversity, mostly similar items
   - 1: Very limited variety
   - 0: No diversity or single item type

3. **Result Quality** (0-5): Are individual results clear, distinct, and functional?
   - 5: All results clear, unique, complete information
   - 4: Most results good quality with minor issues
   - 3: Acceptable quality with some problems
   - 2: Many quality issues (duplicates, missing info)
   - 1: Poor quality results
   - 0: Broken or unusable results

4. **Navigability** (0-5): Can users refine and navigate the results effectively?
   - 5: Excellent filters, sorting, facets available
   - 4: Good navigation options present
   - 3: Basic navigation capabilities
   - 2: Limited navigation features
   - 1: Minimal navigation support
   - 0: No navigation aids visible

5. **Overall** (0-5): Overall user satisfaction with search experience
   - This is NOT an average of other scores
   - Consider the complete user journey
   - Weight heavily towards whether user would find what they need

## Important Guidelines:

- Base evaluation ONLY on the provided results and context
- Do NOT use external knowledge about the site or products
- Cite specific result ranks in your evidence
- Identify concrete issues and improvements
- Be strict but fair in scoring
- If results are mostly ads or promotions, penalize appropriately
- Consider whether results actually answer the query

## Output Format:

Return ONLY a valid JSON object matching the schema. No additional text before or after.
"""

JUDGE_USER_PROMPT_TEMPLATE = """Evaluate the search quality for the following query on {site_name}.

## Query
"{query_text}"

## Search Results (Top {num_results})

{results_json}

## Page Context (truncated)

URL: {page_url}
HTML snippet (first 2000 chars):
```
{html_snippet}
```

## Instructions

Analyze the results and provide scores according to the rubric.
For each result you reference, cite its rank number.
Return ONLY the JSON object, no other text.
"""


def get_judge_schema() -> dict[str, Any]:
    """Get JSON schema for judge output.

    Returns:
        JSON schema dictionary
    """
    return {
        "type": "object",
        "properties": {
            "overall": {
                "type": "number",
                "minimum": 0,
                "maximum": 5,
                "description": "Overall satisfaction score",
            },
            "relevance": {
                "type": "number",
                "minimum": 0,
                "maximum": 5,
                "description": "Relevance to query intent",
            },
            "diversity": {
                "type": "number",
                "minimum": 0,
                "maximum": 5,
                "description": "Diversity of results",
            },
            "result_quality": {
                "type": "number",
                "minimum": 0,
                "maximum": 5,
                "description": "Quality of individual results",
            },
            "navigability": {
                "type": "number",
                "minimum": 0,
                "maximum": 5,
                "description": "UI usability and navigation",
            },
            "rationale": {
                "type": "string",
                "description": "Explanation of scores",
            },
            "issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of identified problems",
            },
            "improvements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Suggested improvements",
            },
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "rank": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                    "required": ["rank", "reason"],
                },
                "description": "Per-result evidence",
            },
            "schema_version": {
                "type": "string",
                "description": "Schema version",
            },
        },
        "required": [
            "overall",
            "relevance",
            "diversity",
            "result_quality",
            "navigability",
            "rationale",
            "issues",
            "improvements",
            "evidence",
            "schema_version",
        ],
    }


def format_results_for_judge(results: list) -> str:
    """Format results list for judge prompt.

    Args:
        results: List of ResultItem objects

    Returns:
        Formatted JSON string
    """
    formatted = []
    for item in results:
        formatted.append(
            {
                "rank": item.rank,
                "title": item.title or "N/A",
                "url": item.url or "N/A",
                "snippet": item.snippet or "N/A",
                "price": item.price or "N/A",
            }
        )

    return json.dumps(formatted, indent=2)
