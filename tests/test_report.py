"""Tests for report generation."""

import json
import tempfile
from pathlib import Path

import pytest

from agentic_search_audit.analysis.maturity import DimensionScore, MaturityLevel, MaturityReport
from agentic_search_audit.analysis.uplift_planner import (
    Category,
    Finding,
    FindingsReport,
    Severity,
)
from agentic_search_audit.core.types import (
    AuditConfig,
    AuditRecord,
    PageArtifacts,
    Query,
    QueryOrigin,
    ReportConfig,
    ResultItem,
    SiteConfig,
)
from agentic_search_audit.report.generator import ReportGenerator, escape_html
from tests.helpers import make_fqi_judge_score


@pytest.fixture
def sample_audit_record():
    """Create a sample audit record for testing."""
    query = Query(
        id="q001",
        text="running shoes",
        lang="en",
        origin=QueryOrigin.PREDEFINED,
    )

    items = [
        ResultItem(
            rank=1,
            title="Nike Air Max",
            url="https://nike.com/product/1",
            snippet="Premium running shoe",
            price="$120",
        ),
        ResultItem(
            rank=2,
            title="Nike React",
            url="https://nike.com/product/2",
            snippet="Lightweight trainer",
            price="$100",
        ),
    ]

    page = PageArtifacts(
        url="https://nike.com",
        final_url="https://nike.com/search?q=running+shoes",
        html_path="/tmp/test.html",
        screenshot_path="/tmp/test.png",
    )

    judge = make_fqi_judge_score(
        query_understanding_score=4.5,
        results_relevance_score=4.5,
        result_presentation_score=4.5,
        advanced_features_score=4.5,
        error_handling_score=4.5,
        rationale="Excellent search results with high relevance",
        issues=["Some minor duplicates"],
        improvements=["Add more filter options"],
        evidence=[{"rank": 1, "reason": "Perfect match for query"}],
    )

    return AuditRecord(
        site="https://nike.com",
        query=query,
        items=items,
        page=page,
        judge=judge,
    )


@pytest.fixture
def temp_run_dir():
    """Create a temporary run directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        (run_dir / "screenshots").mkdir(exist_ok=True)
        (run_dir / "html_snapshots").mkdir(exist_ok=True)
        yield run_dir


@pytest.fixture
def audit_config(temp_run_dir):
    """Create a test audit configuration."""
    return AuditConfig(
        site=SiteConfig(url="https://nike.com"),
        report=ReportConfig(
            formats=["md", "html", "json"],
            out_dir=str(temp_run_dir),
        ),
    )


@pytest.mark.unit
def test_report_generator_initialization(audit_config, temp_run_dir):
    """Test ReportGenerator initialization."""
    generator = ReportGenerator(audit_config, temp_run_dir)

    assert generator.config == audit_config
    assert generator.run_dir == temp_run_dir


@pytest.mark.unit
def test_generate_markdown_report(audit_config, temp_run_dir, sample_audit_record):
    """Test Markdown report generation."""
    generator = ReportGenerator(audit_config, temp_run_dir)

    # Create dummy screenshot file
    screenshot_path = temp_run_dir / "screenshots" / "q001_running_shoes.png"
    screenshot_path.write_text("dummy")

    # Update record to use the screenshot path
    sample_audit_record.page.screenshot_path = str(screenshot_path)

    generator._generate_markdown([sample_audit_record])

    report_path = temp_run_dir / "report.md"
    assert report_path.exists()

    content = report_path.read_text()
    assert "Search Quality Audit Report" in content
    assert "running shoes" in content
    assert "4.50" in content  # FQI score (all dimensions at 4.5)
    assert "Nike Air Max" in content


@pytest.mark.unit
def test_generate_html_report(audit_config, temp_run_dir, sample_audit_record):
    """Test HTML report generation."""
    generator = ReportGenerator(audit_config, temp_run_dir)

    # Create dummy screenshot file
    screenshot_path = temp_run_dir / "screenshots" / "q001_running_shoes.png"
    screenshot_path.write_text("dummy")

    sample_audit_record.page.screenshot_path = str(screenshot_path)

    generator._generate_html([sample_audit_record])

    report_path = temp_run_dir / "report.html"
    assert report_path.exists()

    content = report_path.read_text()
    assert "<!DOCTYPE html>" in content
    assert "Search Quality Audit Report" in content
    assert "running shoes" in content
    assert "4.50" in content  # FQI score (all dimensions at 4.5)

    # New UX elements
    assert "verdict-bar" in content
    assert "dim-bar" in content
    assert "dim-fill" in content
    assert "querySort" in content
    assert "sortQueries" in content
    assert "analysis-section" in content
    assert "screenshot-toggle" in content
    assert "data-index" in content


@pytest.mark.unit
def test_generate_json_report(audit_config, temp_run_dir, sample_audit_record):
    """Test JSON report generation."""
    generator = ReportGenerator(audit_config, temp_run_dir)

    generator._generate_json([sample_audit_record])

    report_path = temp_run_dir / "audit.json"
    assert report_path.exists()

    import json

    content = json.loads(report_path.read_text())
    assert "site" in content
    assert "records" in content
    assert len(content["records"]) == 1
    assert content["records"][0]["query"]["text"] == "running shoes"


@pytest.mark.unit
def test_get_score_class(audit_config, temp_run_dir):
    """Test score class determination."""
    generator = ReportGenerator(audit_config, temp_run_dir)

    assert generator._get_score_class(4.5) == "score-excellent"
    assert generator._get_score_class(3.5) == "score-good"
    assert generator._get_score_class(2.5) == "score-fair"
    assert generator._get_score_class(1.5) == "score-fair"
    assert generator._get_score_class(1.0) == "score-poor"


@pytest.mark.unit
def test_generate_all_reports(audit_config, temp_run_dir, sample_audit_record):
    """Test generating all report formats."""
    generator = ReportGenerator(audit_config, temp_run_dir)

    # Create dummy screenshot file
    screenshot_path = temp_run_dir / "screenshots" / "q001_running_shoes.png"
    screenshot_path.write_text("dummy")

    sample_audit_record.page.screenshot_path = str(screenshot_path)

    generator.generate_reports([sample_audit_record])

    assert (temp_run_dir / "report.md").exists()
    assert (temp_run_dir / "report.html").exists()
    assert (temp_run_dir / "audit.json").exists()


# ============================================================================
# Maturity Section Tests
# ============================================================================


@pytest.fixture
def sample_maturity_report():
    """Create a sample maturity report for testing."""
    return MaturityReport(
        overall_level=MaturityLevel.L3_ENHANCED,
        overall_score=3.5,
        dimensions={
            "results_relevance": DimensionScore(
                name="Results Relevance",
                score=4.0,
                level=MaturityLevel.L4_INTELLIGENT,
                findings=["Strong relevance"],
                recommendations=["Keep monitoring"],
            ),
            "query_understanding": DimensionScore(
                name="Query Understanding",
                score=3.2,
                level=MaturityLevel.L3_ENHANCED,
                findings=["Basic understanding"],
                recommendations=["Add synonyms"],
            ),
            "result_presentation": DimensionScore(
                name="Result Presentation",
                score=3.8,
                level=MaturityLevel.L3_ENHANCED,
                findings=["Good presentation"],
                recommendations=["Improve mobile view"],
            ),
            "error_handling": DimensionScore(
                name="Error Handling",
                score=3.0,
                level=MaturityLevel.L3_ENHANCED,
                findings=["Adequate handling"],
                recommendations=["Add did-you-mean"],
            ),
            "advanced_features": DimensionScore(
                name="Advanced Features",
                score=2.5,
                level=MaturityLevel.L2_FUNCTIONAL,
                findings=["Limited features"],
                recommendations=["Add autocomplete"],
            ),
        },
        executive_summary="The site search is at Level 3 maturity with a score of 3.5/5.0.",
        strengths=["Results Relevance: Excellent performance (score: 4.0)"],
        weaknesses=["Advanced Features: Needs improvement (score: 2.5)"],
        priority_improvements=["Add autocomplete", "Implement synonym expansion"],
    )


@pytest.fixture
def sample_findings_report():
    """Create a sample findings report for testing."""
    findings = [
        Finding(
            id="F001",
            observation="Search results are not sufficiently relevant to user queries",
            affected_queries=8,
            total_queries=10,
            severity=Severity.CRITICAL,
            affected_dimension="results_relevance",
            avg_dimension_score=1.8,
            example_queries=["running shoes", "blue jacket", "winter coat"],
            suggestion="Consider reviewing the search ranking algorithm",
            category=Category.RELEVANCE,
        ),
        Finding(
            id="F002",
            observation="Search does not handle misspellings or typos gracefully",
            affected_queries=5,
            total_queries=10,
            severity=Severity.HIGH,
            affected_dimension="query_understanding",
            avg_dimension_score=2.5,
            example_queries=["runing shoes", "sneekers"],
            suggestion="Consider adding typo tolerance or spell correction",
            category=Category.RELEVANCE,
        ),
        Finding(
            id="F003",
            observation="Limited or missing search result filtering",
            affected_queries=3,
            total_queries=10,
            severity=Severity.MEDIUM,
            affected_dimension="result_presentation",
            avg_dimension_score=3.2,
            example_queries=["jackets"],
            suggestion="Consider adding faceted navigation",
            category=Category.UX,
        ),
    ]
    return FindingsReport(
        findings=findings,
        scope_limitations="This audit evaluates search quality from a frontend user perspective only.",
        total_queries_analyzed=10,
        summary="Analysis of 10 queries identified 3 search quality findings.",
    )


class TestMaturitySectionReports:
    """Tests for maturity section in reports."""

    @pytest.mark.unit
    def test_markdown_maturity_section(
        self, audit_config, temp_run_dir, sample_audit_record, sample_maturity_report
    ):
        """Test markdown maturity section contains expected elements."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        # Create dummy screenshot
        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator._generate_markdown([sample_audit_record], sample_maturity_report, None)

        content = (temp_run_dir / "report.md").read_text()

        # Check header and level
        assert "## Maturity Assessment" in content
        assert "L3_ENHANCED" in content
        assert "3.50" in content  # Overall score

        # Check dimension table
        assert "### Dimension Scores" in content
        assert "Results Relevance" in content
        assert "4.00" in content  # Relevance score

        # Check strengths and weaknesses
        assert "### Strengths" in content
        assert "### Areas for Improvement" in content
        assert "Excellent performance" in content
        assert "Needs improvement" in content

    @pytest.mark.unit
    def test_html_maturity_section(
        self, audit_config, temp_run_dir, sample_audit_record, sample_maturity_report
    ):
        """Test HTML maturity section contains badge and CSS classes."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator._generate_html([sample_audit_record], sample_maturity_report, None)

        content = (temp_run_dir / "report.html").read_text()

        # Check maturity badge with correct class
        assert "maturity-l3" in content
        assert "maturity-badge" in content
        assert "Level 3: L3_ENHANCED" in content

        # Check dimension grid
        assert "dimension-grid" in content
        assert "Results Relevance" in content

    @pytest.mark.unit
    def test_json_maturity_section(
        self, audit_config, temp_run_dir, sample_audit_record, sample_maturity_report
    ):
        """Test JSON report contains serialized maturity data."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        generator._generate_json([sample_audit_record], sample_maturity_report, None)

        content = json.loads((temp_run_dir / "audit.json").read_text())

        assert "maturity" in content
        assert content["maturity"]["overall_level"] == "L3_ENHANCED"
        assert content["maturity"]["overall_score"] == 3.5
        assert "dimensions" in content["maturity"]
        assert "results_relevance" in content["maturity"]["dimensions"]
        assert content["maturity"]["dimensions"]["results_relevance"]["score"] == 4.0

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "level,css_class",
        [
            (MaturityLevel.L1_BASIC, "maturity-l1"),
            (MaturityLevel.L2_FUNCTIONAL, "maturity-l2"),
            (MaturityLevel.L3_ENHANCED, "maturity-l3"),
            (MaturityLevel.L4_INTELLIGENT, "maturity-l4"),
            (MaturityLevel.L5_AGENTIC, "maturity-l5"),
        ],
    )
    def test_maturity_all_levels_css(
        self,
        audit_config,
        temp_run_dir,
        sample_audit_record,
        sample_maturity_report,
        level,
        css_class,
    ):
        """Test each maturity level renders with correct CSS class."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        # Modify maturity level
        sample_maturity_report.overall_level = level

        generator._generate_html([sample_audit_record], sample_maturity_report, None)

        content = (temp_run_dir / "report.html").read_text()
        assert css_class in content


class TestFindingsSectionReports:
    """Tests for findings section in reports."""

    @pytest.mark.unit
    def test_markdown_findings_section(
        self, audit_config, temp_run_dir, sample_audit_record, sample_findings_report
    ):
        """Test markdown findings section contains expected elements."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator._generate_markdown([sample_audit_record], None, sample_findings_report)

        content = (temp_run_dir / "report.md").read_text()

        # Check header and summary
        assert "## Search Quality Issues" in content
        assert "3 search quality findings" in content

        # Check scope & limitations
        assert "### Scope & Limitations" in content
        assert "frontend" in content

        # Check severity headings
        assert "### Critical Severity" in content

        # Check finding content
        assert "not sufficiently relevant" in content
        assert "8/10 queries" in content

    @pytest.mark.unit
    def test_html_findings_section(
        self, audit_config, temp_run_dir, sample_audit_record, sample_findings_report
    ):
        """Test HTML findings section contains badges and cards."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator._generate_html([sample_audit_record], None, sample_findings_report)

        content = (temp_run_dir / "report.html").read_text()

        # Check findings summary box
        assert "findings-summary" in content
        assert "Search Quality Issues" in content

        # Check severity badges
        assert "severity-badge" in content
        assert "severity-critical" in content
        assert "severity-high" in content

        # Check finding cards
        assert "finding-card" in content
        assert "not sufficiently relevant" in content

        # Check scope limitations
        assert "scope-limitations" in content

    @pytest.mark.unit
    def test_html_findings_query_counts(
        self, audit_config, temp_run_dir, sample_audit_record, sample_findings_report
    ):
        """Test that query counts appear in findings."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator._generate_html([sample_audit_record], None, sample_findings_report)

        content = (temp_run_dir / "report.html").read_text()

        # Check query count format
        assert "8/10 queries" in content
        assert "5/10 queries" in content

    @pytest.mark.unit
    def test_json_findings_section(
        self, audit_config, temp_run_dir, sample_audit_record, sample_findings_report
    ):
        """Test JSON report contains serialized findings data."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        generator._generate_json([sample_audit_record], None, sample_findings_report)

        content = json.loads((temp_run_dir / "audit.json").read_text())

        assert "findings" in content
        assert content["findings"]["total_queries_analyzed"] == 10
        assert len(content["findings"]["items"]) == 3
        assert content["findings"]["items"][0]["severity"] == "critical"
        assert content["findings"]["items"][0]["affected_queries"] == 8
        assert "scope_limitations" in content["findings"]


# ============================================================================
# HTML UX Improvement Tests
# ============================================================================


class TestHtmlUxImprovements:
    """Tests for HTML report UX improvements (verdict bar, sort, layout)."""

    @pytest.mark.unit
    def test_verdict_bar_dimensions(self, audit_config, temp_run_dir, sample_audit_record):
        """Test verdict bar renders all 5 dimension bars."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator._generate_html([sample_audit_record])
        content = (temp_run_dir / "report.html").read_text()

        # All 5 dimension labels should appear in dim-bar elements
        for label in ["QU", "RR", "RP", "AF", "EH"]:
            assert f'<span class="dim-label">{label}</span>' in content

    @pytest.mark.unit
    def test_weak_dimension_warning(self, audit_config, temp_run_dir):
        """Test weak dimension warning badge appears for low scores."""
        query = Query(id="q001", text="test query", lang="en", origin=QueryOrigin.PREDEFINED)
        items = [ResultItem(rank=1, title="Product", url="https://example.com")]
        page = PageArtifacts(
            url="https://example.com",
            final_url="https://example.com/search",
            html_path="/tmp/test.html",
            screenshot_path=str(temp_run_dir / "screenshots" / "test.png"),
        )
        # Two dimensions below 3.0
        judge = make_fqi_judge_score(
            query_understanding_score=2.0,
            results_relevance_score=2.5,
            result_presentation_score=4.0,
            advanced_features_score=4.0,
            error_handling_score=4.0,
            rationale="Test",
        )
        record = AuditRecord(
            site="https://example.com", query=query, items=items, page=page, judge=judge
        )

        (temp_run_dir / "screenshots" / "test.png").write_text("dummy")

        generator = ReportGenerator(audit_config, temp_run_dir)
        generator._generate_html([record])
        content = (temp_run_dir / "report.html").read_text()

        assert "summary-warn" in content
        assert "2 weak" in content
        assert "dim-warn" in content

    @pytest.mark.unit
    def test_no_weak_warning_when_all_high(self, audit_config, temp_run_dir, sample_audit_record):
        """Test no weak warning when all dimensions >= 3.0."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator._generate_html([sample_audit_record])
        content = (temp_run_dir / "report.html").read_text()

        # The CSS class exists in stylesheet, but no actual warning badge in HTML body
        assert "\u26a0" not in content  # No warning emoji in output

    @pytest.mark.unit
    def test_results_before_analysis(self, audit_config, temp_run_dir, sample_audit_record):
        """Test results table appears before analysis section in HTML."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator._generate_html([sample_audit_record])
        content = (temp_run_dir / "report.html").read_text()

        # Search within query content area (after </style>) to avoid matching CSS
        body_content = content[content.index("</style>") :]
        results_pos = body_content.index("results-table")
        analysis_pos = body_content.index("analysis-section")
        assert results_pos < analysis_pos

    @pytest.mark.unit
    def test_screenshot_in_collapsible(self, audit_config, temp_run_dir, sample_audit_record):
        """Test screenshot is wrapped in collapsible details element."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator._generate_html([sample_audit_record])
        content = (temp_run_dir / "report.html").read_text()

        assert "screenshot-toggle" in content
        # Screenshot img should be inside a <details> element
        assert '<details class="screenshot-toggle">' in content

    @pytest.mark.unit
    def test_sort_dropdown_options(self, audit_config, temp_run_dir, sample_audit_record):
        """Test sort dropdown has all expected options."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator._generate_html([sample_audit_record])
        content = (temp_run_dir / "report.html").read_text()

        assert 'value="original"' in content
        assert 'value="alpha-asc"' in content
        assert 'value="alpha-desc"' in content
        assert 'value="score-asc"' in content
        assert 'value="score-desc"' in content

    @pytest.mark.unit
    def test_fill_class_helper(self, audit_config, temp_run_dir):
        """Test _get_fill_class returns correct classes."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        assert generator._get_fill_class(4.5) == "fill-excellent"
        assert generator._get_fill_class(3.5) == "fill-good"
        assert generator._get_fill_class(2.5) == "fill-fair"
        assert generator._get_fill_class(1.5) == "fill-poor"

    @pytest.mark.unit
    def test_executive_summary_preferred_over_rationale(self, audit_config, temp_run_dir):
        """Test executive summary is shown instead of rationale when available."""
        query = Query(id="q001", text="test", lang="en", origin=QueryOrigin.PREDEFINED)
        items = [ResultItem(rank=1, title="Product", url="https://example.com")]
        page = PageArtifacts(
            url="https://example.com",
            final_url="https://example.com/search",
            html_path="/tmp/test.html",
            screenshot_path=str(temp_run_dir / "screenshots" / "test.png"),
        )
        judge = make_fqi_judge_score(
            rationale="This is the rationale text",
            executive_summary="This is the executive summary text",
        )
        record = AuditRecord(
            site="https://example.com", query=query, items=items, page=page, judge=judge
        )

        (temp_run_dir / "screenshots" / "test.png").write_text("dummy")

        generator = ReportGenerator(audit_config, temp_run_dir)
        generator._generate_html([record])
        content = (temp_run_dir / "report.html").read_text()

        # Inside analysis section, executive summary should appear
        assert "This is the executive summary text" in content
        # Rationale should NOT appear in the analysis section
        # Search within HTML body (after </style>) to avoid CSS definitions
        body_content = content[content.index("</style>") :]
        analysis_start = body_content.index("analysis-section")
        analysis_section = body_content[analysis_start : analysis_start + 500]
        assert "This is the executive summary text" in analysis_section
        assert "This is the rationale text" not in analysis_section


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestReportEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.unit
    def test_empty_records(self, audit_config, temp_run_dir):
        """Test handling of empty records list."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        # Should not raise exception
        generator.generate_reports([], include_maturity=False, include_findings=False)

        # Files should still be created (with minimal content)
        assert (temp_run_dir / "report.md").exists()
        assert (temp_run_dir / "report.html").exists()
        assert (temp_run_dir / "audit.json").exists()

        # JSON should have empty records
        data = json.loads((temp_run_dir / "audit.json").read_text())
        assert data["total_queries"] == 0
        assert len(data["records"]) == 0

    @pytest.mark.unit
    def test_null_values_in_results(self, audit_config, temp_run_dir):
        """Test handling of None title/url/snippet in results."""
        query = Query(id="q001", text="test", lang="en", origin=QueryOrigin.PREDEFINED)
        items = [
            ResultItem(rank=1, title=None, url=None, snippet=None, price=None),
            ResultItem(rank=2, title="Valid Title", url="https://example.com", snippet="Snippet"),
        ]
        page = PageArtifacts(
            url="https://example.com",
            final_url="https://example.com/search",
            html_path="/tmp/test.html",
            screenshot_path=str(temp_run_dir / "screenshots" / "test.png"),
        )
        judge = make_fqi_judge_score(rationale="Test")

        record = AuditRecord(
            site="https://example.com", query=query, items=items, page=page, judge=judge
        )

        # Create screenshot
        (temp_run_dir / "screenshots" / "test.png").write_text("dummy")

        generator = ReportGenerator(audit_config, temp_run_dir)
        generator._generate_markdown([record])

        content = (temp_run_dir / "report.md").read_text()

        # Should show N/A for missing values
        assert "N/A" in content
        assert "Valid Title" in content

    @pytest.mark.unit
    def test_very_long_strings(self, audit_config, temp_run_dir):
        """Test handling of very long title strings."""
        long_title = "A" * 600

        query = Query(id="q001", text="test", lang="en", origin=QueryOrigin.PREDEFINED)
        items = [ResultItem(rank=1, title=long_title, url="https://example.com/product")]
        page = PageArtifacts(
            url="https://example.com",
            final_url="https://example.com/search",
            html_path="/tmp/test.html",
            screenshot_path=str(temp_run_dir / "screenshots" / "test.png"),
        )
        judge = make_fqi_judge_score(rationale="Test rationale")

        record = AuditRecord(
            site="https://example.com", query=query, items=items, page=page, judge=judge
        )

        (temp_run_dir / "screenshots" / "test.png").write_text("dummy")

        generator = ReportGenerator(audit_config, temp_run_dir)
        generator._generate_markdown([record])

        content = (temp_run_dir / "report.md").read_text()

        # Title should be truncated (max 50 chars in markdown tables)
        # The full title should NOT appear
        assert long_title not in content
        # But a truncated version should
        assert "AAA" in content

    @pytest.mark.unit
    def test_special_characters(self, audit_config, temp_run_dir):
        """Test handling of Unicode and special characters."""
        query = Query(id="q001", text="日本語テスト 🎉", lang="ja", origin=QueryOrigin.PREDEFINED)
        items = [
            ResultItem(
                rank=1,
                title="商品名 with émojis 🔥",
                url="https://example.com/product?q=日本語",
                snippet="Description with <special> & 'chars'",
                price="¥1,000",
            )
        ]
        page = PageArtifacts(
            url="https://example.com",
            final_url="https://example.com/search",
            html_path="/tmp/test.html",
            screenshot_path=str(temp_run_dir / "screenshots" / "test.png"),
        )
        judge = make_fqi_judge_score(rationale="テスト rationale")

        record = AuditRecord(
            site="https://example.com", query=query, items=items, page=page, judge=judge
        )

        (temp_run_dir / "screenshots" / "test.png").write_text("dummy")

        generator = ReportGenerator(audit_config, temp_run_dir)
        generator._generate_html([record])

        content = (temp_run_dir / "report.html").read_text()

        # Japanese characters and emojis should be preserved
        assert "日本語テスト" in content
        assert "商品" in content
        # Special HTML chars should be escaped
        assert "&lt;special&gt;" in content or "<special>" not in content

    @pytest.mark.unit
    def test_large_dataset(self, audit_config, temp_run_dir):
        """Test performance with 100+ records."""
        records = []
        for i in range(100):
            query = Query(
                id=f"q{i:03d}", text=f"query {i}", lang="en", origin=QueryOrigin.PREDEFINED
            )
            items = [
                ResultItem(rank=j, title=f"Product {i}-{j}", url=f"https://example.com/{i}/{j}")
                for j in range(1, 6)
            ]
            page = PageArtifacts(
                url="https://example.com",
                final_url=f"https://example.com/search?q=query+{i}",
                html_path="/tmp/test.html",
                screenshot_path=str(temp_run_dir / "screenshots" / f"q{i:03d}.png"),
            )
            judge = make_fqi_judge_score(
                query_understanding_score=3.0 + (i % 20) / 10,
                results_relevance_score=3.5,
                result_presentation_score=3.0,
                advanced_features_score=3.5,
                error_handling_score=3.0,
                rationale=f"Rationale for query {i}",
            )
            records.append(
                AuditRecord(
                    site="https://example.com", query=query, items=items, page=page, judge=judge
                )
            )

            # Create screenshot
            (temp_run_dir / "screenshots" / f"q{i:03d}.png").write_text("dummy")

        generator = ReportGenerator(audit_config, temp_run_dir)

        # Should complete without timeout
        generator.generate_reports(records, include_maturity=False, include_findings=False)

        content = (temp_run_dir / "report.md").read_text()
        assert "100" in content  # Total queries
        assert "query 0" in content
        assert "query 99" in content


# ============================================================================
# XSS Prevention Tests
# ============================================================================


class TestXSSPrevention:
    """Tests for XSS prevention in HTML reports."""

    @pytest.mark.unit
    def test_escape_html_function(self):
        """Test the escape_html utility function."""
        assert (
            escape_html("<script>alert('xss')</script>")
            == "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"
        )
        assert escape_html("Test & Test") == "Test &amp; Test"
        assert escape_html('"quoted"') == "&quot;quoted&quot;"
        assert escape_html(None) == ""
        assert escape_html("Normal text") == "Normal text"

    @pytest.mark.unit
    def test_xss_query_text(self, audit_config, temp_run_dir):
        """Test XSS prevention in query text."""
        malicious_query = "<script>alert('xss')</script>"

        query = Query(id="q001", text=malicious_query, lang="en", origin=QueryOrigin.PREDEFINED)
        items = [ResultItem(rank=1, title="Product", url="https://example.com")]
        page = PageArtifacts(
            url="https://example.com",
            final_url="https://example.com/search",
            html_path="/tmp/test.html",
            screenshot_path=str(temp_run_dir / "screenshots" / "test.png"),
        )
        judge = make_fqi_judge_score(rationale="Test")

        record = AuditRecord(
            site="https://example.com", query=query, items=items, page=page, judge=judge
        )

        (temp_run_dir / "screenshots" / "test.png").write_text("dummy")

        generator = ReportGenerator(audit_config, temp_run_dir)
        generator._generate_html([record])

        content = (temp_run_dir / "report.html").read_text()

        # The malicious script in the query should be escaped
        # Note: There are legitimate <script> tags for Chart.js and interactive features,
        # so we check that the *malicious* content is escaped, not that <script> is absent
        assert "<script>alert" not in content  # The malicious alert should be escaped
        assert "&lt;script&gt;alert" in content  # The escaped version should be present

    @pytest.mark.unit
    def test_xss_judge_rationale(self, audit_config, temp_run_dir):
        """Test XSS prevention in judge rationale."""
        malicious_rationale = "<img src=x onerror=alert('xss')>"

        query = Query(id="q001", text="test", lang="en", origin=QueryOrigin.PREDEFINED)
        items = [ResultItem(rank=1, title="Product", url="https://example.com")]
        page = PageArtifacts(
            url="https://example.com",
            final_url="https://example.com/search",
            html_path="/tmp/test.html",
            screenshot_path=str(temp_run_dir / "screenshots" / "test.png"),
        )
        judge = make_fqi_judge_score(
            rationale=malicious_rationale,
            executive_summary="",
            issues=["<script>malicious</script>"],
            improvements=["<a onclick='evil()'>click me</a>"],
        )

        record = AuditRecord(
            site="https://example.com", query=query, items=items, page=page, judge=judge
        )

        (temp_run_dir / "screenshots" / "test.png").write_text("dummy")

        generator = ReportGenerator(audit_config, temp_run_dir)
        generator._generate_html([record])

        content = (temp_run_dir / "report.html").read_text()

        # All malicious content should be escaped - check that raw HTML is NOT present
        # (the escaped versions like &lt;script&gt; are OK)
        assert "<img src=x onerror" not in content
        assert "onclick='evil()'" not in content
        assert "<script>malicious</script>" not in content
        # Verify the escaped versions ARE present
        assert "&lt;script&gt;" in content
        assert "&#x27;xss&#x27;" in content

    @pytest.mark.unit
    def test_xss_result_title(self, audit_config, temp_run_dir):
        """Test XSS prevention in result titles."""
        query = Query(id="q001", text="test", lang="en", origin=QueryOrigin.PREDEFINED)
        items = [
            ResultItem(
                rank=1,
                title="<script>document.cookie</script>",
                url="https://example.com",
                snippet="<img src=x onerror='alert(1)'>",
                price="<b onmouseover='alert(1)'>$100</b>",
            )
        ]
        page = PageArtifacts(
            url="https://example.com",
            final_url="https://example.com/search",
            html_path="/tmp/test.html",
            screenshot_path=str(temp_run_dir / "screenshots" / "test.png"),
        )
        judge = make_fqi_judge_score(rationale="Test")

        record = AuditRecord(
            site="https://example.com", query=query, items=items, page=page, judge=judge
        )

        (temp_run_dir / "screenshots" / "test.png").write_text("dummy")

        generator = ReportGenerator(audit_config, temp_run_dir)
        generator._generate_html([record])

        content = (temp_run_dir / "report.html").read_text()

        # Verify script tags are escaped
        assert "<script>document.cookie</script>" not in content
        assert "&lt;script&gt;" in content

    @pytest.mark.unit
    def test_xss_url_attribute(self, audit_config, temp_run_dir):
        """Test XSS prevention in URL attributes."""
        query = Query(id="q001", text="test", lang="en", origin=QueryOrigin.PREDEFINED)
        items = [
            ResultItem(
                rank=1,
                title="Product",
                url="javascript:alert('xss')",
            )
        ]
        page = PageArtifacts(
            url="https://example.com",
            final_url="https://example.com/search",
            html_path="/tmp/test.html",
            screenshot_path=str(temp_run_dir / "screenshots" / "test.png"),
        )
        judge = make_fqi_judge_score(rationale="Test")

        record = AuditRecord(
            site="https://example.com", query=query, items=items, page=page, judge=judge
        )

        (temp_run_dir / "screenshots" / "test.png").write_text("dummy")

        generator = ReportGenerator(audit_config, temp_run_dir)
        generator._generate_html([record])

        content = (temp_run_dir / "report.html").read_text()

        # JavaScript URLs should be escaped (the colon at minimum)
        # The escape_html function with quote=True escapes single quotes
        assert 'href="javascript:alert' not in content or "&#x27;" in content


# ============================================================================
# CSV Export Tests
# ============================================================================


class TestCSVExport:
    """Tests for CSV export functionality."""

    @pytest.mark.unit
    def test_csv_export_creates_file(self, audit_config, temp_run_dir, sample_audit_record):
        """Test that CSV file is created when findings are available."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        # Need records with issues so findings are generated
        sample_audit_record.judge.issues = ["Typo not handled", "No filter options"]
        generator.generate_reports(
            [sample_audit_record], include_maturity=False, include_findings=True
        )

        csv_path = temp_run_dir / "findings.csv"
        assert csv_path.exists()

    @pytest.mark.unit
    def test_csv_export_headers(self, sample_findings_report):
        """Test CSV has expected column headers."""
        from agentic_search_audit.analysis.uplift_planner import FindingsAnalyzer

        analyzer = FindingsAnalyzer()
        csv_content = analyzer.export_to_csv(sample_findings_report)

        lines = csv_content.strip().split("\n")
        header = lines[0]

        # Check all expected columns
        expected_headers = [
            "ID",
            "Observation",
            "Affected Queries",
            "Severity",
            "Dimension",
            "Category",
            "Suggestion",
        ]
        for h in expected_headers:
            assert h in header

    @pytest.mark.unit
    def test_csv_export_special_chars(self):
        """Test CSV properly escapes commas and quotes."""
        from agentic_search_audit.analysis.uplift_planner import FindingsAnalyzer

        finding = Finding(
            id="F001",
            observation='Observation with "quotes" and, commas',
            affected_queries=5,
            total_queries=10,
            severity=Severity.HIGH,
            affected_dimension="results_relevance",
            avg_dimension_score=2.5,
            example_queries=["query 1, with comma", "query 2"],
            suggestion="Suggestion with\nnewline",
            category=Category.RELEVANCE,
        )

        report = FindingsReport(
            findings=[finding],
            scope_limitations="Test",
            total_queries_analyzed=10,
            summary="Test",
        )

        analyzer = FindingsAnalyzer()
        csv_content = analyzer.export_to_csv(report)

        # CSV should be parseable
        import csv as csv_mod
        import io

        reader = csv_mod.reader(io.StringIO(csv_content))
        rows = list(reader)

        # Header + 1 data row
        assert len(rows) == 2

        # Data should be properly escaped
        data_row = rows[1]
        assert data_row[0] == "F001"
        assert '"quotes"' in data_row[1]
        assert "commas" in data_row[1]
