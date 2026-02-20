"""Judge rubric and prompts for the FQI (Findability Quality Index) model."""

import json
from typing import Any

JUDGE_SYSTEM_PROMPT = """You are a search quality evaluator using the Findability Quality Index (FQI) framework.

Your task is to objectively evaluate on-site search quality across 5 weighted dimensions.

## FQI Dimensions (0-5 scale each):

### 1. Query Understanding (25% weight)
How well does the search engine understand the user's intent?
- 5: Handles synonyms, typos, long-tail, and semantic queries perfectly
- 4: Good understanding with minor misses on complex queries
- 3: Handles exact matches well but struggles with synonyms/typos
- 2: Frequent misunderstanding of intent, literal matching only
- 1: Fails on most queries beyond exact product names
- 0: Does not understand queries at all

### 2. Results Relevance (25% weight)
How relevant are the returned results to the query intent?
- 5: All results highly relevant, perfectly ranked
- 4: Most results relevant with minor ranking issues
- 3: Mixed relevance, some good results buried
- 2: Mostly irrelevant with few relevant results
- 1: Barely relevant results
- 0: Completely irrelevant or no results

### 3. Result Presentation & Navigability (20% weight)
Are results well-presented with clear info, filters, and navigation aids?
- 5: Rich product cards, excellent filters/facets, sort options, clear pricing
- 4: Good presentation with minor gaps in filters or product info
- 3: Basic presentation, limited filtering options
- 2: Poor layout, missing product info, few navigation aids
- 1: Confusing presentation, no filters
- 0: Broken or unusable layout

### 4. Advanced Features (20% weight)
Are advanced search capabilities present (autocomplete, did-you-mean, etc.)?
- 5: Autocomplete, suggestions, spell correction, visual search, personalization
- 4: Most advanced features present
- 3: Some advanced features (e.g., basic autocomplete)
- 2: Limited advanced features
- 1: Minimal beyond basic search
- 0: No advanced features

### 5. Error Handling (10% weight)
How well does search handle edge cases, zero results, and errors?
- 5: Graceful handling with suggestions, alternatives, and helpful messaging
- 4: Good error handling with some suggestions
- 3: Shows "no results" with basic messaging
- 2: Poor error handling, dead ends
- 1: Errors or broken states on edge cases
- 0: Crashes or completely fails

## FQI Calculation
FQI = (QU x 0.25) + (RR x 0.25) + (RP x 0.20) + (AF x 0.20) + (EH x 0.10)

**Hard Rule:** If Query Understanding OR Results Relevance < 2.0, FQI is capped at 3.5

## Score Bands
- 4.5-5.0: Excellent | 3.5-4.4: Good | 2.5-3.4: Weak | 1.5-2.4: Critical | <1.5: Broken

## Important Guidelines
- Base evaluation ONLY on the provided results and context
- Do NOT use external knowledge about the site or products
- Cite specific result ranks in your evidence
- Provide per-dimension diagnosis explaining the score
- Be strict but fair in scoring

## Output Format

Return ONLY a valid JSON object with this EXACT structure:

```json
{
  "query_understanding": {"score": 3.5, "diagnosis": "Handles exact match well but..."},
  "results_relevance": {"score": 4.0, "diagnosis": "Results are relevant to..."},
  "result_presentation": {"score": 3.0, "diagnosis": "Basic product cards shown..."},
  "advanced_features": {"score": 2.5, "diagnosis": "Only basic autocomplete..."},
  "error_handling": {"score": 4.0, "diagnosis": "Good zero-result handling..."},
  "rationale": "Overall assessment explanation...",
  "executive_summary": "One-paragraph summary for stakeholders...",
  "issues": ["Issue 1", "Issue 2"],
  "improvements": ["Improvement 1", "Improvement 2"],
  "evidence": [
    {"rank": 1, "reason": "Why this result is good/bad"},
    {"rank": 2, "reason": "Why this result is good/bad"}
  ],
  "schema_version": "2.1"
}
```
"""

JUDGE_USER_PROMPT_TEMPLATE = """Evaluate the search quality for the following query on {site_name} using the FQI framework.

## Query
"{query_text}"

## Locale / Language Context
Target locale: {locale}
Results and page content should be evaluated in the context of this locale.
If the locale is non-English, expect product titles, descriptions, prices, and UI
elements to appear in the locale's language. Results served in the wrong language
(e.g. English when the locale is fr-FR) should be flagged as a quality issue.

## Search Results (Top {num_results})

{results_json}

## Page Context (truncated)

URL: {page_url}
HTML snippet (first 2000 chars):
```
{html_snippet}
```

## Instructions

Analyze the results and provide FQI scores across all 5 dimensions.
For each dimension, provide a score (0-5) and a brief diagnosis.
For each result you reference, cite its rank number.
Return ONLY the JSON object matching the FQI schema.
Include schema_version: "2.1" in your response.
"""


def get_judge_schema() -> dict[str, Any]:
    """Get JSON schema for FQI judge output.

    Returns:
        JSON schema dictionary
    """
    dimension_schema = {
        "type": "object",
        "properties": {
            "score": {
                "type": "number",
                "minimum": 0,
                "maximum": 5,
                "description": "Dimension score (0-5)",
            },
            "diagnosis": {
                "type": "string",
                "description": "Per-query diagnosis for this dimension",
            },
        },
        "required": ["score", "diagnosis"],
    }

    return {
        "type": "object",
        "properties": {
            "query_understanding": {
                **dimension_schema,
                "description": "Query understanding score and diagnosis",
            },
            "results_relevance": {
                **dimension_schema,
                "description": "Results relevance score and diagnosis",
            },
            "result_presentation": {
                **dimension_schema,
                "description": "Result presentation & navigability score and diagnosis",
            },
            "advanced_features": {
                **dimension_schema,
                "description": "Advanced features score and diagnosis",
            },
            "error_handling": {
                **dimension_schema,
                "description": "Error handling score and diagnosis",
            },
            "rationale": {
                "type": "string",
                "description": "Overall assessment explanation",
            },
            "executive_summary": {
                "type": "string",
                "description": "Executive summary for stakeholders",
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
            "query_understanding",
            "results_relevance",
            "result_presentation",
            "advanced_features",
            "error_handling",
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
