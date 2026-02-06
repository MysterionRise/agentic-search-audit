"""Type definitions for the audit system."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, HttpUrl, model_validator

if TYPE_CHECKING:
    pass


@runtime_checkable
class BrowserClient(Protocol):
    """Protocol defining the browser client interface.

    Both PlaywrightBrowserClient and MCPBrowserClient implement this interface,
    allowing them to be used interchangeably.
    """

    async def connect(self) -> None:
        """Connect to the browser."""
        ...

    async def disconnect(self) -> None:
        """Disconnect from the browser."""
        ...

    async def navigate(self, url: str, wait_until: str = "networkidle") -> str:
        """Navigate to a URL."""
        ...

    async def query_selector(self, selector: str) -> dict[str, Any] | None:
        """Query DOM for a single element."""
        ...

    async def query_selector_all(self, selector: str) -> list[dict[str, Any]]:
        """Query DOM for all matching elements."""
        ...

    async def evaluate(self, expression: str) -> Any:
        """Evaluate JavaScript in the page context."""
        ...

    async def click(self, selector: str) -> None:
        """Click an element."""
        ...

    async def type_text(self, selector: str, text: str, delay: int = 50) -> None:
        """Type text into an input element."""
        ...

    async def press_key(self, key: str) -> None:
        """Press a keyboard key."""
        ...

    async def screenshot(self, output_path: Path, full_page: bool = True) -> Path:
        """Take a screenshot of the page."""
        ...

    async def get_html(self) -> str:
        """Get current page HTML."""
        ...

    async def wait_for_selector(
        self, selector: str, timeout: int = 5000, visible: bool = True
    ) -> bool:
        """Wait for a selector to appear."""
        ...

    async def wait_for_network_idle(self, timeout: int = 2000) -> None:
        """Wait for network to be idle."""
        ...

    async def get_element_text(self, selector: str) -> str | None:
        """Get text content of an element."""
        ...

    async def get_element_attribute(self, selector: str, attribute: str) -> str | None:
        """Get attribute value of an element."""
        ...


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


FQI_WEIGHTS: dict[str, float] = {
    "query_understanding": 0.25,
    "results_relevance": 0.25,
    "result_presentation": 0.20,
    "advanced_features": 0.20,
    "error_handling": 0.10,
}

FQI_HARD_CAP = 3.5

FQI_BANDS: list[tuple[float, str]] = [
    (4.5, "Excellent"),
    (3.5, "Good"),
    (2.5, "Weak"),
    (1.5, "Critical"),
    (0.0, "Broken"),
]


def compute_fqi(dimensions: dict[str, float]) -> float:
    """Compute FQI score from dimension scores with hard cap rule.

    Args:
        dimensions: Dict mapping dimension name to score (0-5).

    Returns:
        FQI score (0-5), capped at 3.5 if query_understanding or results_relevance < 2.0.
    """
    fqi = sum(dimensions.get(dim, 0.0) * weight for dim, weight in FQI_WEIGHTS.items())
    if (
        dimensions.get("query_understanding", 0.0) < 2.0
        or dimensions.get("results_relevance", 0.0) < 2.0
    ):
        fqi = min(fqi, FQI_HARD_CAP)
    return round(fqi, 4)


def get_fqi_band(score: float) -> str:
    """Get FQI band label for a score."""
    for threshold, label in FQI_BANDS:
        if score >= threshold:
            return label
    return "Broken"


class DimensionDiagnosis(BaseModel):
    """Score and diagnosis for a single FQI dimension."""

    score: float = Field(ge=0, le=5, description="Dimension score (0-5)")
    diagnosis: str = Field(default="", description="Per-query diagnosis for this dimension")


class JudgeScore(BaseModel):
    """LLM judge scoring for a search query using the FQI model."""

    query_understanding: DimensionDiagnosis = Field(
        description="Query understanding score and diagnosis"
    )
    results_relevance: DimensionDiagnosis = Field(
        description="Results relevance score and diagnosis"
    )
    result_presentation: DimensionDiagnosis = Field(
        description="Result presentation & navigability score and diagnosis"
    )
    advanced_features: DimensionDiagnosis = Field(
        description="Advanced features score and diagnosis"
    )
    error_handling: DimensionDiagnosis = Field(description="Error handling score and diagnosis")
    fqi: float = Field(default=0.0, ge=0, le=5, description="Findability Quality Index (computed)")
    rationale: str = Field(description="Explanation of the overall assessment")
    executive_summary: str = Field(default="", description="Executive summary for this query")
    issues: list[str] = Field(default_factory=list, description="List of identified problems")
    improvements: list[str] = Field(default_factory=list, description="Suggested improvements")
    evidence: list[dict[str, Any]] = Field(
        default_factory=list, description="Per-result evidence with rank and reason"
    )
    schema_version: str = Field(default="2.1", description="Schema version for compatibility")

    @model_validator(mode="after")
    def _compute_fqi(self) -> "JudgeScore":
        """Auto-compute FQI from dimension scores."""
        dims = {
            "query_understanding": self.query_understanding.score,
            "results_relevance": self.results_relevance.score,
            "result_presentation": self.result_presentation.score,
            "advanced_features": self.advanced_features.score,
            "error_handling": self.error_handling.score,
        }
        self.fqi = compute_fqi(dims)
        return self


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
        default=["accept", "agree", "continue", "got it", "close", "dismiss"],
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
    max_tokens: int = Field(default=2000, description="Max tokens in response")
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


class ComplianceConfig(BaseModel):
    """Compliance and ethical crawling configuration."""

    respect_robots_txt: bool = Field(
        default=True, description="Whether to respect robots.txt directives"
    )
    user_agent: str = Field(
        default="AgenticSearchAudit/1.0", description="User agent for robots.txt checks"
    )
    robots_timeout: float = Field(
        default=10.0, description="Timeout for fetching robots.txt in seconds"
    )


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
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)
