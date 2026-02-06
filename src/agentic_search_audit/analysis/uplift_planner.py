"""Observation-based findings analysis for search quality audits."""

import csv
import io
import logging
from dataclasses import dataclass, field
from enum import Enum

from ..core.types import AuditRecord

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    """Finding severity levels."""

    CRITICAL = "critical"  # >75% affected OR dimension avg <2.0
    HIGH = "high"  # >50% affected OR dimension avg <3.0
    MEDIUM = "medium"  # >25% affected
    LOW = "low"  # <25% affected


class Category(str, Enum):
    """Finding categories."""

    RELEVANCE = "relevance"
    UX = "user_experience"
    CONVERSION = "conversion"
    TECHNICAL = "technical"
    CONTENT = "content"
    PERSONALIZATION = "personalization"


@dataclass
class Finding:
    """A single observation-based finding."""

    id: str
    observation: str
    affected_queries: int
    total_queries: int
    severity: Severity
    affected_dimension: str
    avg_dimension_score: float
    example_queries: list[str] = field(default_factory=list)
    suggestion: str = ""
    category: Category = Category.RELEVANCE

    @property
    def affected_pct(self) -> float:
        """Percentage of queries affected."""
        if self.total_queries == 0:
            return 0.0
        return (self.affected_queries / self.total_queries) * 100


@dataclass
class FindingsReport:
    """Complete findings report."""

    findings: list[Finding]
    scope_limitations: str
    total_queries_analyzed: int
    summary: str


def calculate_severity(affected_pct: float, avg_dim_score: float) -> Severity:
    """Determine severity from frequency and dimension impact.

    Args:
        affected_pct: Percentage of queries affected (0-100).
        avg_dim_score: Average dimension score for affected queries (0-5).

    Returns:
        Severity level.
    """
    if affected_pct > 75 or avg_dim_score < 2.0:
        return Severity.CRITICAL
    if affected_pct > 50 or avg_dim_score < 3.0:
        return Severity.HIGH
    if affected_pct > 25:
        return Severity.MEDIUM
    return Severity.LOW


# Keyword-based issue patterns for grouping judge-reported issues into findings
ISSUE_PATTERNS: dict[str, dict] = {
    "autocomplete": {
        "keywords": ["autocomplete", "auto-complete", "auto complete", "predictive", "typeahead"],
        "dimension": "advanced_features",
        "category": Category.CONVERSION,
        "observation": "No autocomplete or predictive search suggestions observed",
        "suggestion": (
            "Consider implementing autocomplete if not already present, "
            "to help users formulate queries faster"
        ),
    },
    "typo_tolerance": {
        "keywords": ["typo", "misspell", "spelling", "spell correct", "fuzzy"],
        "dimension": "query_understanding",
        "category": Category.RELEVANCE,
        "observation": "Search does not handle misspellings or typos gracefully",
        "suggestion": (
            "Consider adding typo tolerance or spell correction " "if not already implemented"
        ),
    },
    "no_results": {
        "keywords": ["no result", "zero result", "empty result", "nothing found"],
        "dimension": "error_handling",
        "category": Category.UX,
        "observation": "Searches return zero results without helpful fallback content",
        "suggestion": (
            "Consider adding fallback strategies such as related products "
            "or alternative query suggestions when no results are found"
        ),
    },
    "synonym": {
        "keywords": ["synonym", "semantic", "vocabulary", "meaning", "intent"],
        "dimension": "query_understanding",
        "category": Category.RELEVANCE,
        "observation": "Search misses results due to vocabulary mismatch or lack of synonym handling",
        "suggestion": (
            "Consider implementing synonym expansion or semantic matching "
            "if not already in place"
        ),
    },
    "filters": {
        "keywords": ["filter", "facet", "refinement", "narrow", "sort option"],
        "dimension": "result_presentation",
        "category": Category.UX,
        "observation": "Limited or missing search result filtering and faceted navigation",
        "suggestion": (
            "Consider adding faceted navigation with filters for key attributes "
            "(category, price, brand) if not already available"
        ),
    },
    "relevance": {
        "keywords": ["irrelevant", "not relevant", "poor ranking", "wrong result", "mismatch"],
        "dimension": "results_relevance",
        "category": Category.RELEVANCE,
        "observation": "Search results are not sufficiently relevant to user queries",
        "suggestion": (
            "Consider reviewing the search ranking algorithm; "
            "semantic search or learning-to-rank may improve relevance"
        ),
    },
    "presentation": {
        "keywords": [
            "missing image",
            "no image",
            "missing price",
            "no price",
            "incomplete",
            "truncated",
            "product data",
        ],
        "dimension": "result_presentation",
        "category": Category.CONTENT,
        "observation": "Search result cards are missing key product information (images, prices, etc.)",
        "suggestion": (
            "Consider ensuring all product cards display complete information "
            "including images, prices, and key attributes"
        ),
    },
    "sorting": {
        "keywords": ["sort", "ordering", "rank order", "best match"],
        "dimension": "result_presentation",
        "category": Category.UX,
        "observation": "Sort options are missing or results ordering does not match user expectations",
        "suggestion": (
            "Consider providing sort options (relevance, price, popularity) "
            "if not already available"
        ),
    },
    "did_you_mean": {
        "keywords": ["did you mean", "suggestion", "alternative", "recommend"],
        "dimension": "error_handling",
        "category": Category.UX,
        "observation": "No 'did you mean' or query correction suggestions observed",
        "suggestion": (
            "Consider adding query correction suggestions "
            "to help users recover from failed searches"
        ),
    },
    "pagination": {
        "keywords": ["pagination", "next page", "load more", "infinite scroll"],
        "dimension": "result_presentation",
        "category": Category.UX,
        "observation": "Pagination or progressive loading of results is missing or problematic",
        "suggestion": (
            "Consider implementing clear pagination or infinite scroll " "if not already present"
        ),
    },
}

SCOPE_LIMITATIONS = (
    "This audit evaluates search quality from a frontend user perspective only. "
    "Observations are based on visible UI behavior and returned results. "
    "Backend implementation details, search infrastructure, and internal analytics "
    "are not assessed. Suggestions are qualified recommendations based on observed "
    "behavior and may already be partially addressed in ways not visible to the auditor."
)

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


class FindingsAnalyzer:
    """Aggregates per-query judge issues into site-level findings with evidence counts."""

    def analyze(self, records: list[AuditRecord]) -> FindingsReport:
        """Analyze audit records and produce a findings report.

        Args:
            records: Audit records with judge scores.

        Returns:
            FindingsReport with observation-based findings.
        """
        total = len(records)
        if total == 0:
            return FindingsReport(
                findings=[],
                scope_limitations=SCOPE_LIMITATIONS,
                total_queries_analyzed=0,
                summary="No queries were analyzed.",
            )

        # Step 1: Collect issues per query and match to patterns
        # pattern_key -> set of query indices that matched
        pattern_hits: dict[str, set[int]] = {k: set() for k in ISSUE_PATTERNS}
        # Track unmatched issues: issue_text_lower -> set of query indices
        unmatched: dict[str, set[int]] = {}

        for idx, record in enumerate(records):
            for issue in record.judge.issues:
                issue_lower = issue.lower()
                matched = False
                for pattern_key, pattern in ISSUE_PATTERNS.items():
                    if any(kw in issue_lower for kw in pattern["keywords"]):
                        pattern_hits[pattern_key].add(idx)
                        matched = True
                        break
                if not matched:
                    # Normalize for grouping: strip and lowercase
                    normalized = issue_lower.strip()
                    if normalized not in unmatched:
                        unmatched[normalized] = set()
                    unmatched[normalized].add(idx)

        findings: list[Finding] = []
        finding_id = 1

        # Step 2: Create findings from matched patterns
        for pattern_key, query_indices in pattern_hits.items():
            if not query_indices:
                continue

            pattern = ISSUE_PATTERNS[pattern_key]
            dim_name = pattern["dimension"]

            # Calculate avg dimension score for affected queries
            avg_score = self._avg_dimension_score(records, query_indices, dim_name)
            affected_pct = (len(query_indices) / total) * 100
            severity = calculate_severity(affected_pct, avg_score)

            # Collect example queries (max 3)
            examples = [records[i].query.text for i in sorted(query_indices)[:3]]

            findings.append(
                Finding(
                    id=f"F{finding_id:03d}",
                    observation=pattern["observation"],
                    affected_queries=len(query_indices),
                    total_queries=total,
                    severity=severity,
                    affected_dimension=dim_name,
                    avg_dimension_score=round(avg_score, 2),
                    example_queries=examples,
                    suggestion=pattern["suggestion"],
                    category=pattern["category"],
                )
            )
            finding_id += 1

        # Step 3: Catch-all for unmatched issues appearing in 2+ queries
        for issue_text, query_indices in unmatched.items():
            if len(query_indices) < 2:
                continue

            # Use results_relevance as default dimension for unmatched issues
            avg_score = self._avg_dimension_score(records, query_indices, "results_relevance")
            affected_pct = (len(query_indices) / total) * 100
            severity = calculate_severity(affected_pct, avg_score)

            examples = [records[i].query.text for i in sorted(query_indices)[:3]]

            # Capitalize first letter for display
            display_text = issue_text[0].upper() + issue_text[1:] if issue_text else issue_text

            findings.append(
                Finding(
                    id=f"F{finding_id:03d}",
                    observation=display_text,
                    affected_queries=len(query_indices),
                    total_queries=total,
                    severity=severity,
                    affected_dimension="results_relevance",
                    avg_dimension_score=round(avg_score, 2),
                    example_queries=examples,
                    suggestion="",
                    category=Category.RELEVANCE,
                )
            )
            finding_id += 1

        # Step 4: Sort by severity then affected count (descending)
        findings.sort(key=lambda f: (_SEVERITY_ORDER[f.severity], -f.affected_queries))

        summary = self._build_summary(findings, total)

        return FindingsReport(
            findings=findings,
            scope_limitations=SCOPE_LIMITATIONS,
            total_queries_analyzed=total,
            summary=summary,
        )

    def export_to_csv(self, report: FindingsReport) -> str:
        """Export findings to CSV format.

        Args:
            report: Findings report to export.

        Returns:
            CSV string.
        """
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(
            [
                "ID",
                "Observation",
                "Affected Queries",
                "Total Queries",
                "Affected %",
                "Severity",
                "Dimension",
                "Avg Dimension Score",
                "Category",
                "Example Queries",
                "Suggestion",
            ]
        )

        for finding in report.findings:
            writer.writerow(
                [
                    finding.id,
                    finding.observation,
                    finding.affected_queries,
                    finding.total_queries,
                    f"{finding.affected_pct:.1f}",
                    finding.severity.value,
                    finding.affected_dimension,
                    f"{finding.avg_dimension_score:.2f}",
                    finding.category.value,
                    "; ".join(finding.example_queries),
                    finding.suggestion,
                ]
            )

        return output.getvalue()

    @staticmethod
    def _avg_dimension_score(
        records: list[AuditRecord], query_indices: set[int], dimension: str
    ) -> float:
        """Calculate average dimension score for a set of affected queries."""
        scores: list[float] = []
        for idx in query_indices:
            record = records[idx]
            dim_diagnosis = getattr(record.judge, dimension, None)
            if dim_diagnosis is not None:
                scores.append(float(dim_diagnosis.score))
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    @staticmethod
    def _build_summary(findings: list["Finding"], total: int) -> str:
        """Build executive summary from findings."""
        if not findings:
            return (
                f"No recurring search quality issues were identified across "
                f"{total} analyzed queries."
            )

        critical = sum(1 for f in findings if f.severity == Severity.CRITICAL)
        high = sum(1 for f in findings if f.severity == Severity.HIGH)

        summary = (
            f"Analysis of {total} queries identified {len(findings)} " f"search quality findings."
        )

        if critical > 0:
            summary += f" {critical} critical issue{'s' if critical > 1 else ''} require{'s' if critical == 1 else ''} immediate attention."

        if high > 0:
            summary += (
                f" {high} high-severity issue{'s' if high > 1 else ''} should be addressed soon."
            )

        return summary
