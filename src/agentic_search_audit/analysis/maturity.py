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

    # Dimension weights aligned with FQI model
    DIMENSION_WEIGHTS = {
        "results_relevance": 0.25,
        "query_understanding": 0.25,
        "result_presentation": 0.20,
        "advanced_features": 0.20,
        "error_handling": 0.10,
    }

    def __init__(self) -> None:
        """Initialize maturity evaluator."""
        self._thresholds: dict[MaturityLevel, float] = {
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

        # Evaluate each dimension directly from FQI judge scores
        dimensions = {
            "results_relevance": self._evaluate_dimension(
                records, "results_relevance", "Results Relevance"
            ),
            "query_understanding": self._evaluate_dimension(
                records, "query_understanding", "Query Understanding"
            ),
            "result_presentation": self._evaluate_dimension(
                records, "result_presentation", "Result Presentation"
            ),
            "advanced_features": self._evaluate_dimension(
                records, "advanced_features", "Advanced Features"
            ),
            "error_handling": self._evaluate_dimension(records, "error_handling", "Error Handling"),
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

    def _evaluate_dimension(
        self, records: list[AuditRecord], dimension_key: str, display_name: str
    ) -> DimensionScore:
        """Evaluate a dimension directly from FQI judge scores.

        Args:
            records: Audit records
            dimension_key: Key matching the JudgeScore dimension attribute
            display_name: Human-readable name for the dimension

        Returns:
            DimensionScore with average score and collected findings
        """
        scores = [getattr(record.judge, dimension_key).score for record in records]
        avg_score = sum(scores) / len(scores)

        findings = []
        recommendations = []

        # Collect unique diagnoses from judge evaluations
        diagnoses = [getattr(record.judge, dimension_key).diagnosis for record in records]
        unique_diagnoses = list(dict.fromkeys(d for d in diagnoses if d))
        if unique_diagnoses:
            findings.extend(unique_diagnoses[:3])

        # Analyze score distribution
        low_scores = [s for s in scores if s < 2.5]
        if low_scores:
            findings.append(
                f"{len(low_scores)} queries ({len(low_scores)/len(records)*100:.0f}%) "
                f"had low {display_name.lower()} scores"
            )

        high_scores = [s for s in scores if s >= 4.0]
        if len(high_scores) >= len(records) * 0.8:
            findings.append(f"Strong overall {display_name.lower()} performance")

        # Check for consistency
        score_variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
        if score_variance > 1.5:
            findings.append(f"High variance in {display_name.lower()} scores across queries")
            recommendations.append("Investigate query-specific issues causing inconsistency")

        # Collect improvement suggestions from judge
        for record in records:
            for imp in record.judge.improvements:
                if imp not in recommendations:
                    recommendations.append(imp)
                    if len(recommendations) >= 3:
                        break
            if len(recommendations) >= 3:
                break

        if not findings:
            findings = [f"{display_name} appears adequate"]

        return DimensionScore(
            name=display_name,
            score=avg_score,
            level=self._score_to_level(avg_score),
            findings=findings,
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
