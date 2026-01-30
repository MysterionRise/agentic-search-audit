"""Conversion uplift planning and recommendations."""

import csv
import io
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..core.types import AuditRecord
from .maturity import MaturityEvaluator, MaturityReport

logger = logging.getLogger(__name__)


class Priority(str, Enum):
    """Recommendation priority levels."""

    CRITICAL = "critical"  # Must fix - blocking conversions
    HIGH = "high"  # High impact, should address soon
    MEDIUM = "medium"  # Notable improvement opportunity
    LOW = "low"  # Nice to have


class Effort(str, Enum):
    """Implementation effort levels."""

    QUICK_WIN = "quick_win"  # < 1 week
    MODERATE = "moderate"  # 1-4 weeks
    SIGNIFICANT = "significant"  # 1-3 months
    MAJOR = "major"  # 3+ months


class Category(str, Enum):
    """Recommendation categories."""

    RELEVANCE = "relevance"
    UX = "user_experience"
    CONVERSION = "conversion"
    TECHNICAL = "technical"
    CONTENT = "content"
    PERSONALIZATION = "personalization"


@dataclass
class Recommendation:
    """A single improvement recommendation."""

    id: str
    title: str
    description: str
    category: Category
    priority: Priority
    effort: Effort
    expected_uplift_pct: float  # Expected conversion uplift percentage
    confidence: float  # Confidence in the estimate (0-1)
    prerequisites: list[str] = field(default_factory=list)
    metrics_to_track: list[str] = field(default_factory=list)
    implementation_notes: str = ""

    @property
    def roi_score(self) -> float:
        """Calculate ROI score (uplift weighted by confidence, divided by effort)."""
        effort_weights = {
            Effort.QUICK_WIN: 1,
            Effort.MODERATE: 2,
            Effort.SIGNIFICANT: 4,
            Effort.MAJOR: 8,
        }
        return (self.expected_uplift_pct * self.confidence) / effort_weights[self.effort]


@dataclass
class UpliftPlan:
    """Complete uplift implementation plan."""

    recommendations: list[Recommendation]
    total_potential_uplift: float
    quick_wins: list[Recommendation]
    strategic_initiatives: list[Recommendation]
    summary: str
    phases: list[dict[str, Any]]


class UpliftPlanner:
    """Generates conversion uplift recommendations based on audit results."""

    # Rule-based recommendation templates
    RECOMMENDATION_RULES: list[dict[str, Any]] = [
        # Relevance issues
        {
            "id": "rel_001",
            "condition": lambda r, m: m.dimensions.get("relevance", DummyDim()).score < 3.0,
            "title": "Improve Search Relevance Algorithm",
            "description": "Search results are not sufficiently relevant to user queries. "
            "Consider implementing BM25, learning-to-rank, or semantic search.",
            "category": Category.RELEVANCE,
            "priority": Priority.CRITICAL,
            "effort": Effort.SIGNIFICANT,
            "uplift": 15.0,
            "confidence": 0.8,
            "metrics": ["Search exit rate", "Click-through rate", "Add-to-cart from search"],
        },
        {
            "id": "rel_002",
            "condition": lambda r, m: _has_typo_issues(r),
            "title": "Implement Typo Tolerance / Spell Correction",
            "description": "Search fails to handle misspellings. Add fuzzy matching or "
            "spell correction to catch common typos.",
            "category": Category.RELEVANCE,
            "priority": Priority.HIGH,
            "effort": Effort.MODERATE,
            "uplift": 8.0,
            "confidence": 0.85,
            "metrics": ["Zero-result rate", "Search refinement rate"],
        },
        {
            "id": "rel_003",
            "condition": lambda r, m: _has_synonym_issues(r),
            "title": "Add Synonym Expansion",
            "description": "Search misses results due to vocabulary mismatch. "
            "Implement synonym dictionaries or semantic similarity.",
            "category": Category.RELEVANCE,
            "priority": Priority.HIGH,
            "effort": Effort.MODERATE,
            "uplift": 6.0,
            "confidence": 0.75,
            "metrics": ["Search success rate", "Query refinement rate"],
        },
        # Zero result issues
        {
            "id": "err_001",
            "condition": lambda r, m: _high_zero_result_rate(r),
            "title": "Reduce Zero-Result Searches",
            "description": "Too many searches return no results. Implement fallback strategies: "
            "did-you-mean suggestions, related products, or category recommendations.",
            "category": Category.UX,
            "priority": Priority.CRITICAL,
            "effort": Effort.MODERATE,
            "uplift": 12.0,
            "confidence": 0.85,
            "metrics": ["Zero-result rate", "Search abandonment rate"],
        },
        {
            "id": "err_002",
            "condition": lambda r, m: _high_zero_result_rate(r),
            "title": "Add 'Did You Mean' Suggestions",
            "description": "When no results found, suggest corrected queries or alternatives "
            "to help users find what they're looking for.",
            "category": Category.UX,
            "priority": Priority.HIGH,
            "effort": Effort.QUICK_WIN,
            "uplift": 5.0,
            "confidence": 0.9,
            "metrics": ["Zero-result recovery rate", "Suggestion click rate"],
        },
        # UX issues
        {
            "id": "ux_001",
            "condition": lambda r, m: m.dimensions.get("result_presentation", DummyDim()).score
            < 3.0,
            "title": "Improve Search Results Display",
            "description": "Search results presentation needs enhancement. Ensure results show "
            "images, prices, ratings, and key product attributes clearly.",
            "category": Category.UX,
            "priority": Priority.HIGH,
            "effort": Effort.MODERATE,
            "uplift": 10.0,
            "confidence": 0.8,
            "metrics": ["Result card CTR", "Time to first click"],
        },
        {
            "id": "ux_002",
            "condition": lambda r, m: _low_navigability(r),
            "title": "Add Faceted Search / Filters",
            "description": "Users cannot easily refine results. Add faceted navigation with "
            "filters for category, price range, brand, ratings, etc.",
            "category": Category.UX,
            "priority": Priority.HIGH,
            "effort": Effort.SIGNIFICANT,
            "uplift": 18.0,
            "confidence": 0.85,
            "metrics": ["Filter usage rate", "Search-to-purchase conversion"],
        },
        {
            "id": "ux_003",
            "condition": lambda r, m: _low_diversity(r),
            "title": "Improve Result Diversity",
            "description": "Search results lack variety. Implement diversity algorithms to show "
            "different brands, price points, and categories.",
            "category": Category.RELEVANCE,
            "priority": Priority.MEDIUM,
            "effort": Effort.MODERATE,
            "uplift": 5.0,
            "confidence": 0.7,
            "metrics": ["Unique brands in top 10", "Price range coverage"],
        },
        # Conversion optimization
        {
            "id": "conv_001",
            "condition": lambda r, m: True,  # Always recommend if not present
            "title": "Implement Search Autocomplete",
            "description": "Add predictive autocomplete to help users formulate queries faster "
            "and discover products. Show trending/popular searches.",
            "category": Category.CONVERSION,
            "priority": Priority.HIGH,
            "effort": Effort.MODERATE,
            "uplift": 12.0,
            "confidence": 0.85,
            "metrics": ["Autocomplete selection rate", "Time to search"],
        },
        {
            "id": "conv_002",
            "condition": lambda r, m: m.overall_level.value >= 3,
            "title": "Add Search Analytics Dashboard",
            "description": "Implement comprehensive search analytics to track KPIs, identify "
            "failing queries, and measure improvements over time.",
            "category": Category.TECHNICAL,
            "priority": Priority.MEDIUM,
            "effort": Effort.MODERATE,
            "uplift": 3.0,
            "confidence": 0.6,
            "metrics": ["Query coverage", "Search conversion funnel"],
        },
        # Advanced features
        {
            "id": "adv_001",
            "condition": lambda r, m: m.overall_level.value >= 3,
            "title": "Implement Personalized Search Results",
            "description": "Personalize search results based on user history, preferences, "
            "and behavior to improve relevance for returning users.",
            "category": Category.PERSONALIZATION,
            "priority": Priority.MEDIUM,
            "effort": Effort.SIGNIFICANT,
            "uplift": 15.0,
            "confidence": 0.7,
            "metrics": ["Returning user search conversion", "Personal relevance score"],
        },
        {
            "id": "adv_002",
            "condition": lambda r, m: m.overall_level.value >= 4,
            "title": "Add Visual Search Capability",
            "description": "Allow users to search using images. Particularly valuable for "
            "fashion, home decor, and visually-driven categories.",
            "category": Category.CONVERSION,
            "priority": Priority.LOW,
            "effort": Effort.MAJOR,
            "uplift": 8.0,
            "confidence": 0.5,
            "metrics": ["Visual search usage", "Visual search conversion"],
        },
        {
            "id": "adv_003",
            "condition": lambda r, m: m.overall_level.value >= 4,
            "title": "Implement Conversational / AI Search",
            "description": "Add natural language understanding for conversational queries. "
            "Allow users to ask questions like 'best running shoes under $100'.",
            "category": Category.RELEVANCE,
            "priority": Priority.LOW,
            "effort": Effort.MAJOR,
            "uplift": 10.0,
            "confidence": 0.5,
            "metrics": ["NLU query handling rate", "Complex query conversion"],
        },
        # Content optimization
        {
            "id": "cont_001",
            "condition": lambda r, m: _missing_product_data(r),
            "title": "Improve Product Data Quality",
            "description": "Search results missing key information (titles, images, prices). "
            "Ensure all products have complete, searchable metadata.",
            "category": Category.CONTENT,
            "priority": Priority.HIGH,
            "effort": Effort.SIGNIFICANT,
            "uplift": 8.0,
            "confidence": 0.8,
            "metrics": ["Product data completeness", "Rich result display rate"],
        },
        {
            "id": "cont_002",
            "condition": lambda r, m: True,
            "title": "Optimize Product Titles for Search",
            "description": "Ensure product titles include key attributes and keywords that "
            "users actually search for. Avoid cryptic product codes.",
            "category": Category.CONTENT,
            "priority": Priority.MEDIUM,
            "effort": Effort.MODERATE,
            "uplift": 5.0,
            "confidence": 0.75,
            "metrics": ["Title keyword match rate", "Position improvement"],
        },
        # Technical improvements
        {
            "id": "tech_001",
            "condition": lambda r, m: True,
            "title": "Implement Search Result Caching",
            "description": "Cache popular search results to improve response times. "
            "Fast search improves user experience and conversion.",
            "category": Category.TECHNICAL,
            "priority": Priority.MEDIUM,
            "effort": Effort.QUICK_WIN,
            "uplift": 3.0,
            "confidence": 0.8,
            "metrics": ["Search latency P95", "Cache hit rate"],
        },
        {
            "id": "tech_002",
            "condition": lambda r, m: True,
            "title": "Add Search Query Logging & Analysis",
            "description": "Log all search queries with results and user actions. "
            "Essential for understanding user intent and improving search.",
            "category": Category.TECHNICAL,
            "priority": Priority.HIGH,
            "effort": Effort.QUICK_WIN,
            "uplift": 2.0,
            "confidence": 0.9,
            "metrics": ["Query log coverage", "Analysis actionability"],
        },
        # Mobile optimization
        {
            "id": "mob_001",
            "condition": lambda r, m: True,
            "title": "Optimize Search for Mobile",
            "description": "Ensure search experience is fully optimized for mobile devices. "
            "Consider voice search, larger touch targets, and simplified filters.",
            "category": Category.UX,
            "priority": Priority.HIGH,
            "effort": Effort.MODERATE,
            "uplift": 10.0,
            "confidence": 0.8,
            "metrics": ["Mobile search conversion", "Mobile filter usage"],
        },
    ]

    def __init__(self):
        """Initialize uplift planner."""
        self.maturity_evaluator = MaturityEvaluator()

    def generate_plan(
        self,
        records: list[AuditRecord],
        maturity_report: MaturityReport | None = None,
        max_recommendations: int = 15,
    ) -> UpliftPlan:
        """Generate uplift plan from audit records.

        Args:
            records: Audit records
            maturity_report: Pre-computed maturity report (optional)
            max_recommendations: Maximum recommendations to include

        Returns:
            UpliftPlan with prioritized recommendations
        """
        if maturity_report is None:
            maturity_report = self.maturity_evaluator.evaluate(records)

        # Generate recommendations based on rules
        recommendations = self._generate_recommendations(records, maturity_report)

        # Sort by ROI score
        recommendations.sort(key=lambda r: r.roi_score, reverse=True)

        # Limit to max
        recommendations = recommendations[:max_recommendations]

        # Identify quick wins and strategic initiatives
        quick_wins = [r for r in recommendations if r.effort == Effort.QUICK_WIN]
        strategic = [r for r in recommendations if r.effort in [Effort.SIGNIFICANT, Effort.MAJOR]]

        # Calculate total potential uplift (with diminishing returns)
        total_uplift = self._calculate_total_uplift(recommendations)

        # Generate phases
        phases = self._generate_phases(recommendations)

        # Generate summary
        summary = self._generate_summary(recommendations, total_uplift, maturity_report)

        return UpliftPlan(
            recommendations=recommendations,
            total_potential_uplift=total_uplift,
            quick_wins=quick_wins,
            strategic_initiatives=strategic,
            summary=summary,
            phases=phases,
        )

    def _generate_recommendations(
        self, records: list[AuditRecord], maturity: MaturityReport
    ) -> list[Recommendation]:
        """Generate recommendations based on audit data."""
        recommendations = []
        seen_ids = set()

        for rule in self.RECOMMENDATION_RULES:
            if rule["id"] in seen_ids:
                continue

            try:
                if rule["condition"](records, maturity):
                    rec = Recommendation(
                        id=rule["id"],
                        title=rule["title"],
                        description=rule["description"],
                        category=rule["category"],
                        priority=rule["priority"],
                        effort=rule["effort"],
                        expected_uplift_pct=rule["uplift"],
                        confidence=rule["confidence"],
                        metrics_to_track=rule.get("metrics", []),
                    )
                    recommendations.append(rec)
                    seen_ids.add(rule["id"])
            except Exception as e:
                logger.warning(f"Error evaluating rule {rule['id']}: {e}")

        return recommendations

    def _calculate_total_uplift(self, recommendations: list[Recommendation]) -> float:
        """Calculate total uplift with diminishing returns."""
        if not recommendations:
            return 0.0

        # Sort by uplift
        sorted_recs = sorted(recommendations, key=lambda r: r.expected_uplift_pct, reverse=True)

        total = 0.0
        remaining_headroom = 100.0  # Percentage points available

        for rec in sorted_recs:
            # Apply diminishing returns
            actual_uplift = rec.expected_uplift_pct * rec.confidence * (remaining_headroom / 100)
            total += actual_uplift
            remaining_headroom -= actual_uplift * 0.5  # Each improvement reduces future headroom

        return min(total, 50.0)  # Cap at 50% total uplift

    def _generate_phases(self, recommendations: list[Recommendation]) -> list[dict[str, Any]]:
        """Generate implementation phases."""
        phases = []

        # Phase 1: Quick wins (0-4 weeks)
        phase1_recs = [r for r in recommendations if r.effort == Effort.QUICK_WIN]
        if phase1_recs:
            phases.append(
                {
                    "name": "Phase 1: Quick Wins",
                    "duration": "0-4 weeks",
                    "recommendations": [r.id for r in phase1_recs],
                    "expected_uplift": sum(
                        r.expected_uplift_pct * r.confidence for r in phase1_recs
                    ),
                }
            )

        # Phase 2: Core improvements (1-3 months)
        phase2_recs = [
            r
            for r in recommendations
            if r.effort == Effort.MODERATE and r.priority in [Priority.CRITICAL, Priority.HIGH]
        ]
        if phase2_recs:
            phases.append(
                {
                    "name": "Phase 2: Core Improvements",
                    "duration": "1-3 months",
                    "recommendations": [r.id for r in phase2_recs],
                    "expected_uplift": sum(
                        r.expected_uplift_pct * r.confidence for r in phase2_recs
                    ),
                }
            )

        # Phase 3: Strategic initiatives (3-6 months)
        phase3_recs = [r for r in recommendations if r.effort in [Effort.SIGNIFICANT, Effort.MAJOR]]
        if phase3_recs:
            phases.append(
                {
                    "name": "Phase 3: Strategic Initiatives",
                    "duration": "3-6 months",
                    "recommendations": [r.id for r in phase3_recs],
                    "expected_uplift": sum(
                        r.expected_uplift_pct * r.confidence for r in phase3_recs
                    ),
                }
            )

        # Phase 4: Optimization (ongoing)
        phase4_recs = [
            r
            for r in recommendations
            if r.effort == Effort.MODERATE and r.priority in [Priority.MEDIUM, Priority.LOW]
        ]
        if phase4_recs:
            phases.append(
                {
                    "name": "Phase 4: Continuous Optimization",
                    "duration": "Ongoing",
                    "recommendations": [r.id for r in phase4_recs],
                    "expected_uplift": sum(
                        r.expected_uplift_pct * r.confidence for r in phase4_recs
                    ),
                }
            )

        return phases

    def _generate_summary(
        self, recommendations: list[Recommendation], total_uplift: float, maturity: MaturityReport
    ) -> str:
        """Generate executive summary."""
        critical = len([r for r in recommendations if r.priority == Priority.CRITICAL])
        quick_wins = len([r for r in recommendations if r.effort == Effort.QUICK_WIN])

        summary = (
            f"Based on the search quality audit, we've identified {len(recommendations)} "
            f"improvement opportunities with a combined potential conversion uplift of "
            f"{total_uplift:.1f}%. "
        )

        if critical > 0:
            summary += f"There are {critical} critical issues requiring immediate attention. "

        if quick_wins > 0:
            summary += (
                f"{quick_wins} quick wins can be implemented within 1-4 weeks to "
                f"deliver early results. "
            )

        summary += (
            f"The current search maturity level is {maturity.overall_level.name} "
            f"({maturity.overall_score:.1f}/5.0). Following this plan could elevate "
            f"the site to the next maturity level."
        )

        return summary

    def export_to_csv(self, plan: UpliftPlan) -> str:
        """Export recommendations to CSV format (for JIRA import).

        Args:
            plan: Uplift plan to export

        Returns:
            CSV string
        """
        output = io.StringIO()
        writer = csv.writer(output)

        # Header row
        writer.writerow(
            [
                "ID",
                "Title",
                "Description",
                "Category",
                "Priority",
                "Effort",
                "Expected Uplift %",
                "Confidence",
                "ROI Score",
                "Metrics to Track",
            ]
        )

        # Data rows
        for rec in plan.recommendations:
            writer.writerow(
                [
                    rec.id,
                    rec.title,
                    rec.description,
                    rec.category.value,
                    rec.priority.value,
                    rec.effort.value,
                    f"{rec.expected_uplift_pct:.1f}",
                    f"{rec.confidence:.0%}",
                    f"{rec.roi_score:.2f}",
                    "; ".join(rec.metrics_to_track),
                ]
            )

        return output.getvalue()


# Helper class for default dimension
class DummyDim:
    """Dummy dimension for safe attribute access."""

    score = 0.0


# Helper functions for rule conditions
def _has_typo_issues(records: list[AuditRecord]) -> bool:
    """Check if records indicate typo handling issues."""
    typo_count = 0
    for record in records:
        issues_text = " ".join(record.judge.issues).lower()
        if "typo" in issues_text or "misspell" in issues_text or "spelling" in issues_text:
            typo_count += 1
    return typo_count >= len(records) * 0.15


def _has_synonym_issues(records: list[AuditRecord]) -> bool:
    """Check if records indicate synonym/semantic issues."""
    semantic_count = 0
    for record in records:
        issues_text = " ".join(record.judge.issues).lower()
        if "synonym" in issues_text or "semantic" in issues_text or "vocabulary" in issues_text:
            semantic_count += 1
    return semantic_count >= len(records) * 0.15


def _high_zero_result_rate(records: list[AuditRecord]) -> bool:
    """Check for high zero-result rate."""
    if not records:
        return False
    zero_results = sum(1 for r in records if len(r.items) == 0)
    return (zero_results / len(records)) > 0.15


def _low_navigability(records: list[AuditRecord]) -> bool:
    """Check for low navigability scores."""
    if not records:
        return False
    avg = sum(r.judge.navigability for r in records) / len(records)
    return avg < 3.0


def _low_diversity(records: list[AuditRecord]) -> bool:
    """Check for low diversity scores."""
    if not records:
        return False
    avg = sum(r.judge.diversity for r in records) / len(records)
    return avg < 2.8


def _missing_product_data(records: list[AuditRecord]) -> bool:
    """Check for missing product data in results."""
    missing_count = 0
    total_items = 0

    for record in records:
        for item in record.items:
            total_items += 1
            if not item.title or not item.price:
                missing_count += 1

    if total_items == 0:
        return False
    return (missing_count / total_items) > 0.2
