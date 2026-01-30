"""Search maturity assessment framework."""

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from ..core.types import AuditRecord

logger = logging.getLogger(__name__)


class MaturityLevel(IntEnum):
    """Search maturity levels (1-5 scale)."""

    L1_BASIC = 1  # Basic keyword matching only
    L2_FUNCTIONAL = 2  # Working search with basic features
    L3_ENHANCED = 3  # Good UX, filters, facets
    L4_INTELLIGENT = 4  # NLP, personalization, recommendations
    L5_AGENTIC = 5  # AI-powered, conversational, predictive


@dataclass
class DimensionScore:
    """Score for a single maturity dimension."""

    name: str
    score: float  # 0-5 scale
    level: MaturityLevel
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class MaturityReport:
    """Complete maturity assessment report."""

    overall_level: MaturityLevel
    overall_score: float
    dimensions: dict[str, DimensionScore]
    executive_summary: str
    strengths: list[str]
    weaknesses: list[str]
    priority_improvements: list[str]
    benchmark_comparison: dict[str, Any] | None = None


class MaturityEvaluator:
    """Evaluates search maturity based on audit results."""

    # Dimension weights for overall score calculation
    DIMENSION_WEIGHTS = {
        "relevance": 0.30,
        "query_understanding": 0.20,
        "result_presentation": 0.15,
        "error_handling": 0.15,
        "advanced_features": 0.20,
    }

    def __init__(self):
        """Initialize maturity evaluator."""
        self._thresholds = {
            MaturityLevel.L1_BASIC: 0.0,
            MaturityLevel.L2_FUNCTIONAL: 1.5,
            MaturityLevel.L3_ENHANCED: 2.5,
            MaturityLevel.L4_INTELLIGENT: 3.5,
            MaturityLevel.L5_AGENTIC: 4.5,
        }

    def evaluate(self, records: list[AuditRecord]) -> MaturityReport:
        """Evaluate search maturity from audit records.

        Args:
            records: List of audit records

        Returns:
            MaturityReport with assessment results
        """
        if not records:
            return self._empty_report()

        # Evaluate each dimension
        dimensions = {
            "relevance": self._evaluate_relevance(records),
            "query_understanding": self._evaluate_query_understanding(records),
            "result_presentation": self._evaluate_result_presentation(records),
            "error_handling": self._evaluate_error_handling(records),
            "advanced_features": self._evaluate_advanced_features(records),
        }

        # Calculate overall score (weighted average)
        overall_score = sum(
            dimensions[dim].score * weight for dim, weight in self.DIMENSION_WEIGHTS.items()
        )

        # Determine overall level
        overall_level = self._score_to_level(overall_score)

        # Generate insights
        strengths = self._identify_strengths(dimensions)
        weaknesses = self._identify_weaknesses(dimensions)
        priority_improvements = self._prioritize_improvements(dimensions)

        # Generate executive summary
        executive_summary = self._generate_executive_summary(
            overall_level, overall_score, dimensions, len(records)
        )

        return MaturityReport(
            overall_level=overall_level,
            overall_score=overall_score,
            dimensions=dimensions,
            executive_summary=executive_summary,
            strengths=strengths,
            weaknesses=weaknesses,
            priority_improvements=priority_improvements,
        )

    def _evaluate_relevance(self, records: list[AuditRecord]) -> DimensionScore:
        """Evaluate relevance quality dimension."""
        scores = [r.judge.relevance for r in records]
        avg_score = sum(scores) / len(scores)

        findings = []
        recommendations = []

        # Analyze score distribution
        low_relevance = [r for r in records if r.judge.relevance < 2.5]
        if low_relevance:
            findings.append(
                f"{len(low_relevance)} queries ({len(low_relevance)/len(records)*100:.0f}%) "
                f"had low relevance scores"
            )
            recommendations.append("Review ranking algorithm for poorly performing queries")

        high_relevance = [r for r in records if r.judge.relevance >= 4.0]
        if len(high_relevance) >= len(records) * 0.8:
            findings.append("Strong overall relevance performance")

        # Check for consistency
        score_variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
        if score_variance > 1.5:
            findings.append("High variance in relevance scores across queries")
            recommendations.append("Investigate query-specific issues causing inconsistency")

        return DimensionScore(
            name="Relevance Quality",
            score=avg_score,
            level=self._score_to_level(avg_score),
            findings=findings,
            recommendations=recommendations,
        )

    def _evaluate_query_understanding(self, records: list[AuditRecord]) -> DimensionScore:
        """Evaluate query understanding capabilities."""
        findings = []
        recommendations = []

        # Analyze based on query types if available
        # Look for patterns in issues mentioning typos, synonyms, etc.
        typo_issues = 0
        semantic_issues = 0

        for record in records:
            issues_text = " ".join(record.judge.issues).lower()
            if "typo" in issues_text or "misspell" in issues_text:
                typo_issues += 1
            if "synonym" in issues_text or "semantic" in issues_text or "meaning" in issues_text:
                semantic_issues += 1

        # Calculate score based on issue frequency
        base_score = sum(r.judge.relevance for r in records) / len(records)

        # Deduct for query understanding issues
        penalty = 0
        if typo_issues > len(records) * 0.2:
            penalty += 0.5
            findings.append(f"Typo tolerance issues detected in {typo_issues} queries")
            recommendations.append("Implement fuzzy matching or spell correction")

        if semantic_issues > len(records) * 0.2:
            penalty += 0.5
            findings.append(f"Semantic understanding issues in {semantic_issues} queries")
            recommendations.append("Consider adding synonym expansion or semantic search")

        adjusted_score = max(0, min(5, base_score - penalty))

        return DimensionScore(
            name="Query Understanding",
            score=adjusted_score,
            level=self._score_to_level(adjusted_score),
            findings=findings if findings else ["Query understanding appears adequate"],
            recommendations=recommendations,
        )

    def _evaluate_result_presentation(self, records: list[AuditRecord]) -> DimensionScore:
        """Evaluate result presentation quality."""
        scores = [r.judge.navigability for r in records]
        avg_score = sum(scores) / len(scores)

        findings = []
        recommendations = []

        # Check diversity scores
        diversity_scores = [r.judge.diversity for r in records]
        avg_diversity = sum(diversity_scores) / len(diversity_scores)

        if avg_diversity < 2.5:
            findings.append("Low result diversity may indicate filter bubble issues")
            recommendations.append("Improve result diversification algorithms")
        elif avg_diversity >= 4.0:
            findings.append("Good result diversity across queries")

        # Check result quality
        quality_scores = [r.judge.result_quality for r in records]
        avg_quality = sum(quality_scores) / len(quality_scores)

        if avg_quality < 2.5:
            findings.append("Result quality issues (missing images, descriptions, prices)")
            recommendations.append("Ensure search results include rich product information")

        # Combined score
        combined_score = (avg_score + avg_diversity + avg_quality) / 3

        return DimensionScore(
            name="Result Presentation",
            score=combined_score,
            level=self._score_to_level(combined_score),
            findings=findings if findings else ["Result presentation is adequate"],
            recommendations=recommendations,
        )

    def _evaluate_error_handling(self, records: list[AuditRecord]) -> DimensionScore:
        """Evaluate error handling and edge cases."""
        findings = []
        recommendations = []

        # Check for zero-result queries
        zero_results = [r for r in records if len(r.items) == 0]
        zero_rate = len(zero_results) / len(records) if records else 0

        score = 4.0  # Start with good score

        if zero_rate > 0.3:
            score -= 1.5
            findings.append(f"High zero-result rate: {zero_rate*100:.0f}% of queries")
            recommendations.append("Implement 'did you mean' suggestions for zero-result queries")
        elif zero_rate > 0.1:
            score -= 0.5
            findings.append(f"Moderate zero-result rate: {zero_rate*100:.0f}% of queries")

        # Check for error mentions in judge feedback
        error_mentions = 0
        for record in records:
            issues_text = " ".join(record.judge.issues).lower()
            if "error" in issues_text or "broken" in issues_text or "fail" in issues_text:
                error_mentions += 1

        if error_mentions > len(records) * 0.1:
            score -= 1.0
            findings.append(f"Error handling issues detected in {error_mentions} queries")
            recommendations.append("Improve error recovery and user feedback mechanisms")

        score = max(0, min(5, score))

        return DimensionScore(
            name="Error Handling",
            score=score,
            level=self._score_to_level(score),
            findings=findings if findings else ["Error handling appears adequate"],
            recommendations=recommendations,
        )

    def _evaluate_advanced_features(self, records: list[AuditRecord]) -> DimensionScore:
        """Evaluate presence of advanced search features."""
        findings = []
        recommendations = []

        # This is inferred from overall scores and judge feedback
        # Higher scores typically indicate more sophisticated search
        overall_scores = [r.judge.overall for r in records]
        avg_overall = sum(overall_scores) / len(overall_scores)

        # Check for mentions of advanced features in improvements
        feature_mentions = {
            "filters": 0,
            "facets": 0,
            "autocomplete": 0,
            "suggestions": 0,
            "personalization": 0,
        }

        for record in records:
            improvements_text = " ".join(record.judge.improvements).lower()
            for feature in feature_mentions:
                if feature in improvements_text:
                    feature_mentions[feature] += 1

        # If many queries recommend adding features, score lower
        missing_features = sum(
            1 for count in feature_mentions.values() if count > len(records) * 0.3
        )

        score = avg_overall
        if missing_features >= 3:
            score -= 1.0
            findings.append("Multiple advanced features appear to be missing")
            recommendations.extend(
                [
                    "Consider adding faceted search/filters",
                    "Implement autocomplete suggestions",
                    "Add personalized search results",
                ]
            )
        elif missing_features >= 1:
            score -= 0.5
            for feature, count in feature_mentions.items():
                if count > len(records) * 0.3:
                    recommendations.append(f"Consider adding {feature} functionality")

        score = max(0, min(5, score))

        return DimensionScore(
            name="Advanced Features",
            score=score,
            level=self._score_to_level(score),
            findings=findings if findings else ["Search features are adequate for current needs"],
            recommendations=recommendations,
        )

    def _score_to_level(self, score: float) -> MaturityLevel:
        """Convert numeric score to maturity level."""
        if score >= 4.5:
            return MaturityLevel.L5_AGENTIC
        elif score >= 3.5:
            return MaturityLevel.L4_INTELLIGENT
        elif score >= 2.5:
            return MaturityLevel.L3_ENHANCED
        elif score >= 1.5:
            return MaturityLevel.L2_FUNCTIONAL
        else:
            return MaturityLevel.L1_BASIC

    def _identify_strengths(self, dimensions: dict[str, DimensionScore]) -> list[str]:
        """Identify key strengths from dimension scores."""
        strengths = []
        for dim_name, dim_score in dimensions.items():
            if dim_score.score >= 4.0:
                strengths.append(
                    f"{dim_score.name}: Excellent performance (score: {dim_score.score:.1f})"
                )
            elif dim_score.score >= 3.5:
                strengths.append(
                    f"{dim_score.name}: Good performance (score: {dim_score.score:.1f})"
                )

        return strengths if strengths else ["No significant strengths identified"]

    def _identify_weaknesses(self, dimensions: dict[str, DimensionScore]) -> list[str]:
        """Identify key weaknesses from dimension scores."""
        weaknesses = []
        for dim_name, dim_score in dimensions.items():
            if dim_score.score < 2.0:
                weaknesses.append(
                    f"{dim_score.name}: Critical issues (score: {dim_score.score:.1f})"
                )
            elif dim_score.score < 2.5:
                weaknesses.append(
                    f"{dim_score.name}: Needs improvement (score: {dim_score.score:.1f})"
                )

        return weaknesses if weaknesses else ["No critical weaknesses identified"]

    def _prioritize_improvements(self, dimensions: dict[str, DimensionScore]) -> list[str]:
        """Prioritize improvements based on impact and effort."""
        all_recommendations = []

        # Collect all recommendations with their dimension weight
        for dim_name, dim_score in dimensions.items():
            weight = self.DIMENSION_WEIGHTS.get(dim_name, 0.1)
            gap = max(0, 4.0 - dim_score.score)  # Gap to "good" score
            priority = gap * weight

            for rec in dim_score.recommendations:
                all_recommendations.append((priority, rec))

        # Sort by priority (highest first) and return top 5
        all_recommendations.sort(key=lambda x: x[0], reverse=True)
        return [rec for _, rec in all_recommendations[:5]]

    def _generate_executive_summary(
        self,
        level: MaturityLevel,
        score: float,
        dimensions: dict[str, DimensionScore],
        num_queries: int,
    ) -> str:
        """Generate executive summary text."""
        level_descriptions = {
            MaturityLevel.L1_BASIC: "basic keyword-matching",
            MaturityLevel.L2_FUNCTIONAL: "functional but limited",
            MaturityLevel.L3_ENHANCED: "enhanced with good features",
            MaturityLevel.L4_INTELLIGENT: "intelligent with advanced capabilities",
            MaturityLevel.L5_AGENTIC: "best-in-class with AI-powered features",
        }

        desc = level_descriptions[level]

        # Find best and worst dimensions
        sorted_dims = sorted(dimensions.items(), key=lambda x: x[1].score, reverse=True)
        best_dim = sorted_dims[0][1]
        worst_dim = sorted_dims[-1][1]

        summary = (
            f"Based on {num_queries} search queries, the site's search functionality "
            f"is assessed at Maturity Level {level.value} ({level.name}): {desc}. "
            f"The overall maturity score is {score:.2f}/5.00. "
            f"The strongest dimension is {best_dim.name} ({best_dim.score:.1f}/5.0), "
            f"while {worst_dim.name} ({worst_dim.score:.1f}/5.0) requires the most attention."
        )

        return summary

    def _empty_report(self) -> MaturityReport:
        """Return empty report when no records available."""
        return MaturityReport(
            overall_level=MaturityLevel.L1_BASIC,
            overall_score=0.0,
            dimensions={},
            executive_summary="No audit records available for maturity assessment.",
            strengths=[],
            weaknesses=["Insufficient data for assessment"],
            priority_improvements=["Complete a search audit with multiple queries"],
        )
