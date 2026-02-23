"""Expert commentary agents for specialized search audit insights.

Provides two expert perspectives on aggregated audit results:
- Retail Search SME: Merchandising, conversion, product discoverability
- CPG/Brand Expert: Brand visibility, shopper journey, competitive positioning
"""

import asyncio
import json
import logging
import os

from openai import AsyncOpenAI

from ..core.types import AuditRecord, ExpertInsight, LLMConfig

logger = logging.getLogger(__name__)

DEFAULT_EXPERT_TIMEOUT_SECONDS = 30

RETAIL_SME_SYSTEM_PROMPT = """You are a Retail Search SME (Subject Matter Expert) with 15+ years of \
experience in e-commerce merchandising, site search optimization, and conversion rate optimization.

Your role is to analyze search audit results and provide actionable insights from a \
merchandising and conversion perspective.

Focus areas:
- **Product Discoverability**: Are shoppers finding what they need? Is the search \
guiding them to relevant products?
- **Conversion Impact**: How do search quality issues affect add-to-cart rates, \
bounce rates, and revenue?
- **Merchandising Gaps**: Are popular categories well-represented? Are hero products \
surfacing for key queries?
- **Competitive Positioning**: How does this search experience compare to best-in-class \
retailers (Amazon, Target, Sephora)?
- **Quick Wins**: What are the highest-impact, lowest-effort improvements?

Output ONLY a valid JSON object with this structure:
{
  "headline": "One-line headline assessment (max 15 words)",
  "commentary": "2-3 paragraph expert analysis with specific observations",
  "key_observations": ["observation 1", "observation 2", "observation 3"],
  "recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"],
  "risk_level": "low|medium|high|critical"
}
"""

CPG_BRAND_EXPERT_SYSTEM_PROMPT = """You are a CPG & Brand Strategy Expert with deep experience in \
digital shelf analytics, brand visibility measurement, and shopper marketing across \
retail and DTC channels.

Your role is to analyze search audit results and provide insights from a brand and \
shopper journey perspective.

Focus areas:
- **Brand Prominence**: Are brand names and hero products visible in search results?
- **Category Navigation**: Does search support natural category browsing patterns?
- **Cross-sell & Upsell**: Are related products and complementary items suggested?
- **Shopper Journey Friction**: Where do search-driven paths break down?
- **Digital Shelf Quality**: How well does the search results page serve as a \
digital shelf for product discovery?

Output ONLY a valid JSON object with this structure:
{
  "headline": "One-line headline assessment (max 15 words)",
  "commentary": "2-3 paragraph expert analysis with specific observations",
  "key_observations": ["observation 1", "observation 2", "observation 3"],
  "recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"],
  "risk_level": "low|medium|high|critical"
}
"""


def _build_expert_user_prompt(records: list[AuditRecord], site_name: str) -> str:
    """Build the user prompt with aggregated audit data for expert analysis.

    Args:
        records: All audit records from the run
        site_name: Name of the audited site

    Returns:
        Formatted prompt string
    """
    avg_fqi = sum(r.judge.fqi for r in records) / len(records) if records else 0
    avg_qu = (
        sum(r.judge.query_understanding.score for r in records) / len(records) if records else 0
    )
    avg_rr = sum(r.judge.results_relevance.score for r in records) / len(records) if records else 0
    avg_rp = (
        sum(r.judge.result_presentation.score for r in records) / len(records) if records else 0
    )
    avg_af = sum(r.judge.advanced_features.score for r in records) / len(records) if records else 0
    avg_eh = sum(r.judge.error_handling.score for r in records) / len(records) if records else 0

    query_summaries = []
    for r in records:
        top_results = []
        for item in r.items[:4]:
            top_results.append(
                {
                    "rank": item.rank,
                    "title": item.title or "N/A",
                    "price": item.price or "N/A",
                }
            )
        query_summaries.append(
            {
                "query": r.query.text,
                "fqi": round(r.judge.fqi, 2),
                "qu": r.judge.query_understanding.score,
                "rr": r.judge.results_relevance.score,
                "issues": r.judge.issues[:3],
                "top_results": top_results,
            }
        )

    return f"""Analyze the search audit results for {site_name}.

## Overall Scores
- FQI (Findability Quality Index): {avg_fqi:.2f}/5.00
- Query Understanding: {avg_qu:.2f}
- Results Relevance: {avg_rr:.2f}
- Result Presentation: {avg_rp:.2f}
- Advanced Features: {avg_af:.2f}
- Error Handling: {avg_eh:.2f}

## Per-Query Results ({len(records)} queries)

{json.dumps(query_summaries, indent=2)}

Provide your expert analysis as a JSON object. Be specific and cite query examples.
"""


class ExpertPanel:
    """Runs expert commentary agents on aggregated audit results."""

    def __init__(self, config: LLMConfig):
        """Initialize expert panel.

        Args:
            config: LLM configuration (reuses the same provider as the judge)
        """
        self.config = config
        self.client: AsyncOpenAI | None = None

        if config.provider in ("openai", "openrouter", "vllm"):
            if config.provider == "openai":
                api_key = os.getenv("OPENAI_API_KEY")
                self.client = AsyncOpenAI(api_key=api_key) if api_key else None
            elif config.provider == "openrouter":
                api_key = config.api_key or os.getenv("OPENROUTER_API_KEY")
                base_url = config.base_url or "https://openrouter.ai/api/v1"
                self.client = AsyncOpenAI(api_key=api_key, base_url=base_url) if api_key else None
            elif config.provider == "vllm":
                api_key = config.api_key or os.getenv("VLLM_API_KEY") or "not-required"
                self.client = (
                    AsyncOpenAI(base_url=config.base_url, api_key=api_key)
                    if config.base_url
                    else None
                )

    async def evaluate(self, records: list[AuditRecord], site_name: str) -> list[ExpertInsight]:
        """Run all expert agents and return their insights.

        Args:
            records: All audit records from the run
            site_name: Name of the audited site

        Returns:
            List of ExpertInsight objects (one per expert)
        """
        if not self.client or not records:
            logger.warning("Expert panel skipped: no LLM client or no records")
            return []

        user_prompt = _build_expert_user_prompt(records, site_name)

        experts = [
            ("Retail Search SME", RETAIL_SME_SYSTEM_PROMPT),
            ("CPG & Brand Strategy Expert", CPG_BRAND_EXPERT_SYSTEM_PROMPT),
        ]

        tasks = [
            self._call_expert(name, system_prompt, user_prompt) for name, system_prompt in experts
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        insights: list[ExpertInsight] = []
        for i, result in enumerate(results):
            expert_name = experts[i][0]
            if isinstance(result, BaseException):
                logger.error(f"Expert '{expert_name}' failed: {result}")
                insights.append(
                    ExpertInsight(
                        expert_name=expert_name,
                        headline="Analysis unavailable",
                        commentary=f"Expert analysis could not be completed: {result}",
                        key_observations=[],
                        recommendations=[],
                        risk_level="unknown",
                    )
                )
            else:
                insights.append(result)

        return insights

    async def _call_expert(
        self, expert_name: str, system_prompt: str, user_prompt: str
    ) -> ExpertInsight:
        """Call a single expert agent.

        Args:
            expert_name: Human-readable name of the expert
            system_prompt: Expert's system prompt
            user_prompt: Shared user prompt with audit data

        Returns:
            ExpertInsight object
        """
        assert self.client is not None

        logger.info(f"Calling expert: {expert_name}")
        timeout = getattr(self.config, "timeout", None) or DEFAULT_EXPERT_TIMEOUT_SECONDS

        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=1500,
                    response_format={"type": "json_object"},
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Expert '{expert_name}' timed out after {timeout}s")

        raw = response.choices[0].message.content or "{}"

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"Expert '{expert_name}' returned invalid JSON: {raw[:200]}")
            data = {}

        return ExpertInsight(
            expert_name=expert_name,
            headline=data.get("headline", "Analysis complete"),
            commentary=data.get("commentary", raw[:500]),
            key_observations=data.get("key_observations", []),
            recommendations=data.get("recommendations", []),
            risk_level=data.get("risk_level", "medium"),
        )
