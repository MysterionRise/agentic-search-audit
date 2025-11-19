"""Type definitions for the audit system."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class QueryOrigin(str, Enum):
    """Source of the query."""

    PREDEFINED = "predefined"
    GENERATED = "generated"


class Query(BaseModel):
    """A search query to evaluate."""

    id: str = Field(description="Unique identifier for the query")
    text: str = Field(description="The query text to search for")
    lang: str | None = Field(default="en", description="Language code (ISO 639-1)")
    origin: QueryOrigin = Field(default=QueryOrigin.PREDEFINED, description="Query source")


class ResultItem(BaseModel):
    """A single search result item."""

    rank: int = Field(description="Position in search results (1-indexed)")
    title: str | None = Field(default=None, description="Result title")
    url: str | None = Field(default=None, description="Result URL")
    snippet: str | None = Field(default=None, description="Result snippet/description")
    price: str | None = Field(default=None, description="Price if product result")
    image: str | None = Field(default=None, description="Image URL if available")
    attributes: dict[str, str] = Field(default_factory=dict, description="Additional metadata")


class PageArtifacts(BaseModel):
    """Artifacts captured from a search results page."""

    url: str = Field(description="Original search URL")
    final_url: str = Field(description="Final URL after redirects")
    html_path: str = Field(description="Path to saved HTML snapshot")
    screenshot_path: str = Field(description="Path to screenshot")
    ts: datetime = Field(default_factory=datetime.now, description="Timestamp of capture")


class JudgeScore(BaseModel):
    """LLM judge scoring for a search query."""

    overall: float = Field(ge=0, le=5, description="Overall satisfaction score (0-5)")
    relevance: float = Field(ge=0, le=5, description="Relevance to query intent (0-5)")
    diversity: float = Field(ge=0, le=5, description="Diversity of brands/categories/prices (0-5)")
    result_quality: float = Field(ge=0, le=5, description="Quality of individual results (0-5)")
    navigability: float = Field(ge=0, le=5, description="UI usability and filters (0-5)")
    rationale: str = Field(description="Explanation of the overall score")
    issues: list[str] = Field(default_factory=list, description="List of identified problems")
    improvements: list[str] = Field(default_factory=list, description="Suggested improvements")
    evidence: list[dict[str, Any]] = Field(
        default_factory=list, description="Per-result evidence with rank and reason"
    )
    schema_version: str = Field(default="1.0", description="Schema version for compatibility")


class AuditRecord(BaseModel):
    """Complete audit record for a single query."""

    site: str = Field(description="Site being audited")
    query: Query = Field(description="The search query")
    items: list[ResultItem] = Field(description="Extracted search results")
    page: PageArtifacts = Field(description="Page artifacts")
    judge: JudgeScore = Field(description="LLM judge evaluation")


# Configuration models


class SearchConfig(BaseModel):
    """Search interaction configuration."""

    input_selectors: list[str] = Field(
        default=[
            'input[type="search"]',
            'input[aria-label*="Search" i]',
            'input[name="q"]',
            'input[placeholder*="Search" i]',
        ],
        description="CSS selectors for search input",
    )
    submit_strategy: Literal["enter", "clickSelector"] = Field(
        default="enter", description="How to submit the search"
    )
    submit_selector: str | None = Field(
        default=None, description="Selector for submit button if using clickSelector"
    )
    use_intelligent_fallback: bool = Field(
        default=True,
        description="Use LLM-based intelligent detection if CSS selectors fail",
    )


class ResultsConfig(BaseModel):
    """Results extraction configuration."""

    item_selectors: list[str] = Field(
        default=[
            '[data-test*="product-card"]',
            '[data-testid*="product"]',
            ".product-card",
            'a[href*="/p/"]',
        ],
        description="Selectors for result items",
    )
    title_selectors: list[str] = Field(
        default=["h1", "h2", "h3", ".product-title", "a[title]"],
        description="Selectors for result titles",
    )
    url_attr: str = Field(default="href", description="Attribute containing result URL")
    snippet_selectors: list[str] = Field(
        default=[".product-subtitle", ".description", "p"],
        description="Selectors for snippets",
    )
    price_selectors: list[str] = Field(
        default=[".product-price", '[data-test*="price"]', ".price"],
        description="Selectors for prices",
    )
    image_selectors: list[str] = Field(
        default=["img", '[data-testid="product-image"]'], description="Selectors for images"
    )


class ModalsConfig(BaseModel):
    """Modal/popup handling configuration."""

    close_text_matches: list[str] = Field(
        default=[
            "accept",
            "accept all",
            "accept cookies",
            "allow",
            "allow all",
            "agree",
            "continue",
            "got it",
            "ok",
            "okay",
            "close",
            "dismiss",
            "i agree",
            "i accept",
            "consent",
        ],
        description="Text patterns for close buttons",
    )
    max_auto_clicks: int = Field(default=3, description="Max automatic modal dismissals")
    wait_after_close_ms: int = Field(default=500, description="Wait time after closing modal")


class RunConfig(BaseModel):
    """Runtime execution configuration."""

    top_k: int = Field(default=10, description="Number of top results to extract")
    viewport_width: int = Field(default=1366, description="Browser viewport width")
    viewport_height: int = Field(default=900, description="Browser viewport height")
    network_idle_ms: int = Field(default=1200, description="Network idle timeout in milliseconds")
    post_submit_ms: int = Field(default=800, description="Wait time after search submission")
    headless: bool = Field(default=True, description="Run browser in headless mode")
    throttle_rps: float = Field(default=0.5, description="Rate limit in requests per second")
    seed: int | None = Field(default=42, description="Random seed for reproducibility")


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: Literal["openai", "anthropic", "vllm", "openrouter"] = Field(
        default="openai", description="LLM provider"
    )
    model: str = Field(default="gpt-4o-mini", description="Model identifier")
    max_tokens: int = Field(default=800, description="Max tokens in response")
    temperature: float = Field(default=0.2, description="Sampling temperature")
    system_prompt: str | None = Field(default=None, description="Custom system prompt override")

    # Provider-specific configuration
    base_url: str | None = Field(
        default=None,
        description="Base URL for vLLM/OpenRouter server (e.g., 'http://localhost:8000/v1' or 'https://openrouter.ai/api/v1')",
    )
    api_key: str | None = Field(
        default=None, description="API key for the provider (if not using environment variable)"
    )


class ReportConfig(BaseModel):
    """Report generation configuration."""

    formats: list[Literal["md", "html", "json"]] = Field(
        default=["md", "html"], description="Output formats"
    )
    out_dir: str = Field(default="./runs", description="Output directory for runs")


class SiteConfig(BaseModel):
    """Site-specific configuration."""

    url: HttpUrl = Field(description="Site base URL")
    locale: str = Field(default="en-US", description="Locale/language code")
    search: SearchConfig = Field(default_factory=SearchConfig)
    results: ResultsConfig = Field(default_factory=ResultsConfig)
    modals: ModalsConfig = Field(default_factory=ModalsConfig)


class AuditConfig(BaseModel):
    """Complete audit configuration."""

    site: SiteConfig
    run: RunConfig = Field(default_factory=RunConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
