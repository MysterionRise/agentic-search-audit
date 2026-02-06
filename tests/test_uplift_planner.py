"""Tests for observation-based findings analyzer."""

import csv
import io
from datetime import datetime

import pytest

from agentic_search_audit.analysis.uplift_planner import (
    Category,
    Finding,
    FindingsAnalyzer,
    FindingsReport,
    Severity,
    calculate_severity,
)
from agentic_search_audit.core.types import (
    AuditRecord,
    PageArtifacts,
    Query,
    ResultItem,
)
from tests.helpers import make_fqi_judge_score


def _make_record(
    query_text: str, issues: list[str], index: int = 0, **score_overrides
) -> AuditRecord:
    """Helper to create an AuditRecord with specified issues."""
    return AuditRecord(
        site="https://example.com",
        query=Query(id=f"q{index}", text=query_text),
        items=[ResultItem(rank=1, title="Product 1", price="$10")],
        page=PageArtifacts(
            url="https://example.com",
            final_url="https://example.com/search",
            html_path="/tmp/test.html",
            screenshot_path="/tmp/test.png",
            ts=datetime.now(),
        ),
        judge=make_fqi_judge_score(issues=issues, **score_overrides),
    )


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self):
        """Test severity string values."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"

    def test_severity_is_str_enum(self):
        """Test Severity is a string enum."""
        assert isinstance(Severity.CRITICAL, str)


class TestCategory:
    """Tests for Category enum."""

    def test_category_values(self):
        """Test category string values."""
        assert Category.RELEVANCE.value == "relevance"
        assert Category.UX.value == "user_experience"
        assert Category.CONVERSION.value == "conversion"
        assert Category.TECHNICAL.value == "technical"
        assert Category.CONTENT.value == "content"
        assert Category.PERSONALIZATION.value == "personalization"


class TestCalculateSeverity:
    """Tests for calculate_severity function."""

    def test_critical_high_pct(self):
        """Test >75% affected -> CRITICAL."""
        assert calculate_severity(80.0, 3.5) == Severity.CRITICAL

    def test_critical_low_score(self):
        """Test avg_dim_score <2.0 -> CRITICAL."""
        assert calculate_severity(10.0, 1.5) == Severity.CRITICAL

    def test_high_pct(self):
        """Test >50% affected -> HIGH."""
        assert calculate_severity(60.0, 3.5) == Severity.HIGH

    def test_high_low_score(self):
        """Test avg_dim_score <3.0 -> HIGH."""
        assert calculate_severity(10.0, 2.5) == Severity.HIGH

    def test_medium_pct(self):
        """Test >25% affected -> MEDIUM."""
        assert calculate_severity(30.0, 3.5) == Severity.MEDIUM

    def test_low(self):
        """Test <25% affected with good score -> LOW."""
        assert calculate_severity(10.0, 4.0) == Severity.LOW

    def test_boundary_75(self):
        """Test exactly 75% is not CRITICAL (>75 required)."""
        assert calculate_severity(75.0, 3.5) == Severity.HIGH

    def test_boundary_50(self):
        """Test exactly 50% is not HIGH (>50 required)."""
        assert calculate_severity(50.0, 3.5) == Severity.MEDIUM

    def test_boundary_25(self):
        """Test exactly 25% is not MEDIUM (>25 required)."""
        assert calculate_severity(25.0, 3.5) == Severity.LOW

    def test_boundary_score_2(self):
        """Test exactly 2.0 is not CRITICAL (<2.0 required)."""
        assert calculate_severity(10.0, 2.0) == Severity.HIGH


class TestFinding:
    """Tests for Finding dataclass."""

    def test_affected_pct(self):
        """Test affected percentage calculation."""
        finding = Finding(
            id="F001",
            observation="Test",
            affected_queries=3,
            total_queries=10,
            severity=Severity.MEDIUM,
            affected_dimension="results_relevance",
            avg_dimension_score=3.0,
        )
        assert finding.affected_pct == 30.0

    def test_affected_pct_zero_total(self):
        """Test affected percentage with zero total queries."""
        finding = Finding(
            id="F001",
            observation="Test",
            affected_queries=0,
            total_queries=0,
            severity=Severity.LOW,
            affected_dimension="results_relevance",
            avg_dimension_score=0.0,
        )
        assert finding.affected_pct == 0.0


class TestFindingsAnalyzer:
    """Tests for FindingsAnalyzer class."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance."""
        return FindingsAnalyzer()

    def test_empty_records(self, analyzer):
        """Test analysis with no records."""
        report = analyzer.analyze([])

        assert isinstance(report, FindingsReport)
        assert len(report.findings) == 0
        assert report.total_queries_analyzed == 0
        assert "No queries" in report.summary

    def test_no_issues(self, analyzer):
        """Test records with no issues produce no findings."""
        records = [_make_record("running shoes", [], index=i) for i in range(5)]
        report = analyzer.analyze(records)

        assert len(report.findings) == 0
        assert report.total_queries_analyzed == 5
        assert "No recurring" in report.summary

    def test_typo_pattern_detected(self, analyzer):
        """Test that typo-related issues are grouped."""
        records = [
            _make_record("runing shoes", ["Typo not handled"], index=0),
            _make_record("sneekers", ["Misspelling ignored"], index=1),
            _make_record("jackets", [], index=2),
        ]
        report = analyzer.analyze(records)

        typo_findings = [f for f in report.findings if "typo" in f.observation.lower()]
        assert len(typo_findings) == 1
        assert typo_findings[0].affected_queries == 2
        assert typo_findings[0].total_queries == 3

    def test_multiple_patterns_detected(self, analyzer):
        """Test that multiple issue patterns are detected."""
        records = [
            _make_record(
                "test query",
                ["Typo not handled", "No filter options available"],
                index=i,
            )
            for i in range(4)
        ]
        report = analyzer.analyze(records)

        # Should have at least typo and filter findings
        pattern_observations = {f.observation for f in report.findings}
        assert any(
            "typo" in obs.lower() or "misspell" in obs.lower() for obs in pattern_observations
        )
        assert any("filter" in obs.lower() for obs in pattern_observations)

    def test_severity_ordering(self, analyzer):
        """Test findings are sorted by severity then affected count."""
        records = [
            _make_record(
                f"query {i}",
                ["Irrelevant results", "Typo not handled"],
                index=i,
                query_understanding_score=1.5,
                results_relevance_score=1.5,
            )
            for i in range(10)
        ]
        report = analyzer.analyze(records)

        # Verify sorted by severity order
        severity_order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]
        last_severity_idx = -1
        for finding in report.findings:
            idx = severity_order.index(finding.severity)
            assert idx >= last_severity_idx
            last_severity_idx = idx

    def test_example_queries_max_3(self, analyzer):
        """Test that example queries are limited to 3."""
        records = [_make_record(f"query {i}", ["Typo not handled"], index=i) for i in range(10)]
        report = analyzer.analyze(records)

        for finding in report.findings:
            assert len(finding.example_queries) <= 3

    def test_affected_count_accuracy(self, analyzer):
        """Test that affected counts are deduplicated per query."""
        # Same query index should only be counted once per pattern
        # even if it has multiple issues matching the same pattern
        records = [
            _make_record(
                "test query",
                ["Typo not handled", "Spelling error detected"],
                index=0,
            ),
            _make_record("another query", ["Typo ignored"], index=1),
        ]
        report = analyzer.analyze(records)

        typo_findings = [f for f in report.findings if "typo" in f.observation.lower()]
        assert len(typo_findings) == 1
        # Query 0 matched twice but should count as 1
        assert typo_findings[0].affected_queries == 2

    def test_catchall_novel_issues(self, analyzer):
        """Test that unmatched issues appearing in 2+ queries become findings."""
        records = [
            _make_record("query 1", ["custom unusual problem xyz"], index=0),
            _make_record("query 2", ["custom unusual problem xyz"], index=1),
            _make_record("query 3", ["one-off issue"], index=2),
        ]
        report = analyzer.analyze(records)

        # The novel issue should appear as a finding
        novel = [f for f in report.findings if "unusual" in f.observation.lower()]
        assert len(novel) == 1
        assert novel[0].affected_queries == 2

        # The one-off issue should NOT appear
        oneoff = [f for f in report.findings if "one-off" in f.observation.lower()]
        assert len(oneoff) == 0

    def test_scope_limitations_present(self, analyzer):
        """Test that scope limitations are included."""
        records = [_make_record("test", ["Typo issue"], index=0)]
        report = analyzer.analyze(records)

        assert report.scope_limitations != ""
        assert "frontend" in report.scope_limitations.lower()

    def test_summary_critical_count(self, analyzer):
        """Test summary mentions critical issue count."""
        records = [
            _make_record(
                f"query {i}",
                ["Irrelevant results"],
                index=i,
                results_relevance_score=1.5,
            )
            for i in range(10)
        ]
        report = analyzer.analyze(records)

        assert "critical" in report.summary.lower()

    def test_csv_export(self, analyzer):
        """Test CSV export functionality."""
        records = [
            _make_record(f"query {i}", ["Typo not handled", "No filter options"], index=i)
            for i in range(5)
        ]
        report = analyzer.analyze(records)
        csv_output = analyzer.export_to_csv(report)

        assert isinstance(csv_output, str)

        # Parse and verify
        reader = csv.reader(io.StringIO(csv_output))
        rows = list(reader)

        # Header row
        header = rows[0]
        assert "ID" in header
        assert "Observation" in header
        assert "Affected Queries" in header
        assert "Severity" in header
        assert "Suggestion" in header

        # Data rows match findings count
        assert len(rows) - 1 == len(report.findings)

        # Verify finding IDs are in CSV
        for finding in report.findings:
            assert any(finding.id in row[0] for row in rows[1:])

    def test_csv_export_empty(self, analyzer):
        """Test CSV export with no findings."""
        report = analyzer.analyze([])
        csv_output = analyzer.export_to_csv(report)

        reader = csv.reader(io.StringIO(csv_output))
        rows = list(reader)

        # Only header row
        assert len(rows) == 1

    def test_dimension_score_tracking(self, analyzer):
        """Test that avg dimension score is correctly calculated."""
        records = [
            _make_record(
                "query 1",
                ["Typo not handled"],
                index=0,
                query_understanding_score=2.0,
            ),
            _make_record(
                "query 2",
                ["Misspelling ignored"],
                index=1,
                query_understanding_score=4.0,
            ),
        ]
        report = analyzer.analyze(records)

        typo_findings = [f for f in report.findings if "typo" in f.observation.lower()]
        assert len(typo_findings) == 1
        # Average of 2.0 and 4.0
        assert typo_findings[0].avg_dimension_score == 3.0
        assert typo_findings[0].affected_dimension == "query_understanding"
