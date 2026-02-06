"""Industry benchmarks for search quality comparison."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Industry(str, Enum):
    """Industry categories for benchmarking."""

    ECOMMERCE = "ecommerce"
    RETAIL = "retail"
    FASHION = "fashion"
    ELECTRONICS = "electronics"
    MARKETPLACE = "marketplace"
    TRAVEL = "travel"
    MEDIA = "media"
    B2B = "b2b"
    GENERAL = "general"


@dataclass
class IndustryBenchmark:
    """Benchmark scores for an industry using FQI dimensions."""

    industry: Industry
    name: str
    description: str

    # FQI dimension averages and top quartiles (0-5 scale)
    query_understanding_avg: float
    query_understanding_top_quartile: float

    results_relevance_avg: float
    results_relevance_top_quartile: float

    result_presentation_avg: float
    result_presentation_top_quartile: float

    advanced_features_avg: float
    advanced_features_top_quartile: float

    error_handling_avg: float
    error_handling_top_quartile: float

    fqi_avg: float
    fqi_top_quartile: float

    # Key metrics
    zero_result_rate_avg: float  # Percentage
    zero_result_rate_top_quartile: float

    # Sample sizes and sources
    sample_size: int
    last_updated: str

    def compare(self, scores: dict[str, float]) -> dict[str, Any]:
        """Compare provided scores against benchmark.

        Args:
            scores: Dictionary with metric scores

        Returns:
            Comparison results with percentiles and gaps
        """
        comparisons = {}

        dimension_map = {
            "query_understanding": (
                self.query_understanding_avg,
                self.query_understanding_top_quartile,
            ),
            "results_relevance": (
                self.results_relevance_avg,
                self.results_relevance_top_quartile,
            ),
            "result_presentation": (
                self.result_presentation_avg,
                self.result_presentation_top_quartile,
            ),
            "advanced_features": (
                self.advanced_features_avg,
                self.advanced_features_top_quartile,
            ),
            "error_handling": (
                self.error_handling_avg,
                self.error_handling_top_quartile,
            ),
            "fqi": (self.fqi_avg, self.fqi_top_quartile),
        }

        for metric, (avg, top) in dimension_map.items():
            if metric in scores:
                score = scores[metric]
                gap_to_avg = score - avg
                gap_to_top = score - top

                # Estimate percentile (simplified linear interpolation)
                if score >= top:
                    percentile = 90 + (score - top) / (5.0 - top) * 10
                elif score >= avg:
                    percentile = 50 + (score - avg) / (top - avg) * 40
                else:
                    percentile = max(0, 50 * score / avg) if avg > 0 else 0

                percentile = min(99, max(1, percentile))

                comparisons[metric] = {
                    "score": score,
                    "industry_avg": avg,
                    "industry_top_quartile": top,
                    "gap_to_avg": gap_to_avg,
                    "gap_to_top": gap_to_top,
                    "percentile": round(percentile),
                    "status": self._get_status(score, avg, top),
                }

        return comparisons

    def _get_status(self, score: float, avg: float, top: float) -> str:
        """Determine status relative to benchmark."""
        if score >= top:
            return "top_performer"
        elif score >= avg:
            return "above_average"
        elif score >= avg * 0.8:
            return "near_average"
        else:
            return "below_average"


# Industry benchmark data (based on aggregated industry research)
INDUSTRY_BENCHMARKS: dict[Industry, IndustryBenchmark] = {
    Industry.ECOMMERCE: IndustryBenchmark(
        industry=Industry.ECOMMERCE,
        name="E-commerce (General)",
        description="General e-commerce sites including multi-category retailers",
        query_understanding_avg=3.0,
        query_understanding_top_quartile=3.9,
        results_relevance_avg=3.2,
        results_relevance_top_quartile=4.1,
        result_presentation_avg=3.2,
        result_presentation_top_quartile=4.1,
        advanced_features_avg=2.8,
        advanced_features_top_quartile=3.7,
        error_handling_avg=3.0,
        error_handling_top_quartile=3.9,
        fqi_avg=3.1,
        fqi_top_quartile=4.0,
        zero_result_rate_avg=8.5,
        zero_result_rate_top_quartile=3.0,
        sample_size=150,
        last_updated="2024-Q4",
    ),
    Industry.FASHION: IndustryBenchmark(
        industry=Industry.FASHION,
        name="Fashion & Apparel",
        description="Fashion retailers, apparel, and accessories",
        query_understanding_avg=3.2,
        query_understanding_top_quartile=4.1,
        results_relevance_avg=3.4,
        results_relevance_top_quartile=4.3,
        result_presentation_avg=3.5,
        result_presentation_top_quartile=4.3,
        advanced_features_avg=3.0,
        advanced_features_top_quartile=3.9,
        error_handling_avg=3.1,
        error_handling_top_quartile=4.0,
        fqi_avg=3.3,
        fqi_top_quartile=4.2,
        zero_result_rate_avg=6.5,
        zero_result_rate_top_quartile=2.5,
        sample_size=80,
        last_updated="2024-Q4",
    ),
    Industry.ELECTRONICS: IndustryBenchmark(
        industry=Industry.ELECTRONICS,
        name="Electronics & Technology",
        description="Consumer electronics, computers, and tech products",
        query_understanding_avg=3.3,
        query_understanding_top_quartile=4.2,
        results_relevance_avg=3.5,
        results_relevance_top_quartile=4.4,
        result_presentation_avg=3.2,
        result_presentation_top_quartile=4.1,
        advanced_features_avg=3.0,
        advanced_features_top_quartile=3.8,
        error_handling_avg=3.1,
        error_handling_top_quartile=4.0,
        fqi_avg=3.3,
        fqi_top_quartile=4.2,
        zero_result_rate_avg=7.0,
        zero_result_rate_top_quartile=2.8,
        sample_size=65,
        last_updated="2024-Q4",
    ),
    Industry.MARKETPLACE: IndustryBenchmark(
        industry=Industry.MARKETPLACE,
        name="Marketplace",
        description="Multi-vendor marketplaces (Amazon, eBay style)",
        query_understanding_avg=3.5,
        query_understanding_top_quartile=4.4,
        results_relevance_avg=3.6,
        results_relevance_top_quartile=4.5,
        result_presentation_avg=3.4,
        result_presentation_top_quartile=4.3,
        advanced_features_avg=3.3,
        advanced_features_top_quartile=4.2,
        error_handling_avg=3.4,
        error_handling_top_quartile=4.3,
        fqi_avg=3.5,
        fqi_top_quartile=4.4,
        zero_result_rate_avg=5.0,
        zero_result_rate_top_quartile=1.5,
        sample_size=40,
        last_updated="2024-Q4",
    ),
    Industry.TRAVEL: IndustryBenchmark(
        industry=Industry.TRAVEL,
        name="Travel & Hospitality",
        description="Travel booking, hotels, flights, and experiences",
        query_understanding_avg=3.1,
        query_understanding_top_quartile=4.0,
        results_relevance_avg=3.3,
        results_relevance_top_quartile=4.2,
        result_presentation_avg=3.2,
        result_presentation_top_quartile=4.1,
        advanced_features_avg=2.9,
        advanced_features_top_quartile=3.8,
        error_handling_avg=3.0,
        error_handling_top_quartile=3.9,
        fqi_avg=3.1,
        fqi_top_quartile=4.0,
        zero_result_rate_avg=10.0,
        zero_result_rate_top_quartile=4.0,
        sample_size=55,
        last_updated="2024-Q4",
    ),
    Industry.MEDIA: IndustryBenchmark(
        industry=Industry.MEDIA,
        name="Media & Content",
        description="News, entertainment, streaming, and content platforms",
        query_understanding_avg=3.0,
        query_understanding_top_quartile=3.9,
        results_relevance_avg=3.1,
        results_relevance_top_quartile=4.0,
        result_presentation_avg=3.1,
        result_presentation_top_quartile=3.9,
        advanced_features_avg=2.8,
        advanced_features_top_quartile=3.6,
        error_handling_avg=2.9,
        error_handling_top_quartile=3.8,
        fqi_avg=3.0,
        fqi_top_quartile=3.9,
        zero_result_rate_avg=12.0,
        zero_result_rate_top_quartile=5.0,
        sample_size=45,
        last_updated="2024-Q4",
    ),
    Industry.B2B: IndustryBenchmark(
        industry=Industry.B2B,
        name="B2B & Industrial",
        description="Business-to-business commerce and industrial supplies",
        query_understanding_avg=2.7,
        query_understanding_top_quartile=3.5,
        results_relevance_avg=2.9,
        results_relevance_top_quartile=3.7,
        result_presentation_avg=2.6,
        result_presentation_top_quartile=3.4,
        advanced_features_avg=2.3,
        advanced_features_top_quartile=3.1,
        error_handling_avg=2.5,
        error_handling_top_quartile=3.3,
        fqi_avg=2.7,
        fqi_top_quartile=3.5,
        zero_result_rate_avg=15.0,
        zero_result_rate_top_quartile=7.0,
        sample_size=35,
        last_updated="2024-Q4",
    ),
    Industry.GENERAL: IndustryBenchmark(
        industry=Industry.GENERAL,
        name="General (All Industries)",
        description="Cross-industry average benchmark",
        query_understanding_avg=3.0,
        query_understanding_top_quartile=3.9,
        results_relevance_avg=3.2,
        results_relevance_top_quartile=4.1,
        result_presentation_avg=3.1,
        result_presentation_top_quartile=4.0,
        advanced_features_avg=2.8,
        advanced_features_top_quartile=3.7,
        error_handling_avg=2.9,
        error_handling_top_quartile=3.8,
        fqi_avg=3.1,
        fqi_top_quartile=4.0,
        zero_result_rate_avg=9.0,
        zero_result_rate_top_quartile=3.5,
        sample_size=500,
        last_updated="2024-Q4",
    ),
}


def get_industry_benchmark(industry: Industry | str) -> IndustryBenchmark:
    """Get benchmark for a specific industry.

    Args:
        industry: Industry enum or string name

    Returns:
        IndustryBenchmark for the industry
    """
    if isinstance(industry, str):
        try:
            industry = Industry(industry.lower())
        except ValueError:
            industry = Industry.GENERAL

    return INDUSTRY_BENCHMARKS.get(industry, INDUSTRY_BENCHMARKS[Industry.GENERAL])


class IndustryBenchmarks:
    """Utility class for working with industry benchmarks."""

    @staticmethod
    def list_industries() -> list[str]:
        """List all available industries."""
        return [ind.value for ind in Industry]

    @staticmethod
    def get_benchmark(industry: Industry | str) -> IndustryBenchmark:
        """Get benchmark for an industry."""
        return get_industry_benchmark(industry)

    @staticmethod
    def compare_to_industry(
        scores: dict[str, float], industry: Industry | str = Industry.GENERAL
    ) -> dict[str, Any]:
        """Compare scores to industry benchmark.

        Args:
            scores: Dictionary with metric scores
            industry: Industry to compare against

        Returns:
            Comparison results
        """
        benchmark = get_industry_benchmark(industry)
        comparison = benchmark.compare(scores)

        return {
            "industry": benchmark.industry.value,
            "industry_name": benchmark.name,
            "comparisons": comparison,
            "benchmark_sample_size": benchmark.sample_size,
            "benchmark_updated": benchmark.last_updated,
        }

    @staticmethod
    def get_percentile_rating(percentile: int) -> str:
        """Get human-readable rating for percentile.

        Args:
            percentile: Percentile value (0-100)

        Returns:
            Rating string
        """
        if percentile >= 90:
            return "Excellent - Top 10%"
        elif percentile >= 75:
            return "Good - Top 25%"
        elif percentile >= 50:
            return "Average - Top 50%"
        elif percentile >= 25:
            return "Below Average - Bottom 50%"
        else:
            return "Needs Improvement - Bottom 25%"
