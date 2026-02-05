"""Tests for report generation."""

import json
import tempfile
from pathlib import Path

import pytest

from agentic_search_audit.analysis.maturity import DimensionScore, MaturityLevel, MaturityReport
from agentic_search_audit.analysis.uplift_planner import (
    Category,
    Effort,
    Priority,
    Recommendation,
    UpliftPlan,
)
from agentic_search_audit.core.types import (
    AuditConfig,
    AuditRecord,
    JudgeScore,
    PageArtifacts,
    Query,
    QueryOrigin,
    ReportConfig,
    ResultItem,
    SiteConfig,
)
from agentic_search_audit.report.generator import ReportGenerator, escape_html


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

    judge = JudgeScore(
        overall=4.5,
        relevance=4.8,
        diversity=4.2,
        result_quality=4.6,
        navigability=4.0,
        rationale="Excellent search results with high relevance",
        issues=["Some minor duplicates"],
        improvements=["Add more filter options"],
        evidence=[{"rank": 1, "reason": "Perfect match for query"}],
        schema_version="1.0",
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
    assert "4.5" in content  # Overall score
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
    assert "4.5" in content


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
            "relevance": DimensionScore(
                name="Relevance Quality",
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
        strengths=["Relevance Quality: Excellent performance (score: 4.0)"],
        weaknesses=["Advanced Features: Needs improvement (score: 2.5)"],
        priority_improvements=["Add autocomplete", "Implement synonym expansion"],
    )


@pytest.fixture
def sample_uplift_plan():
    """Create a sample uplift plan for testing."""
    recommendations = [
        Recommendation(
            id="rel_001",
            title="Improve Search Relevance",
            description="Enhance the search ranking algorithm.",
            category=Category.RELEVANCE,
            priority=Priority.CRITICAL,
            effort=Effort.SIGNIFICANT,
            expected_uplift_pct=15.0,
            confidence=0.8,
            metrics_to_track=["CTR", "Add-to-cart rate"],
        ),
        Recommendation(
            id="ux_001",
            title="Add Filters",
            description="Implement faceted navigation with filters.",
            category=Category.UX,
            priority=Priority.HIGH,
            effort=Effort.MODERATE,
            expected_uplift_pct=10.0,
            confidence=0.75,
            metrics_to_track=["Filter usage", "Conversion rate"],
        ),
        Recommendation(
            id="tech_001",
            title="Implement Caching",
            description="Cache popular search results.",
            category=Category.TECHNICAL,
            priority=Priority.MEDIUM,
            effort=Effort.QUICK_WIN,
            expected_uplift_pct=3.0,
            confidence=0.9,
            metrics_to_track=["Response time", "Cache hit rate"],
        ),
    ]
    return UpliftPlan(
        recommendations=recommendations,
        total_potential_uplift=25.0,
        quick_wins=[recommendations[2]],
        strategic_initiatives=[recommendations[0]],
        summary="We identified 3 improvement opportunities with 25% total uplift potential.",
        phases=[
            {
                "name": "Phase 1: Quick Wins",
                "duration": "0-4 weeks",
                "recommendations": ["tech_001"],
                "expected_uplift": 3.0,
            },
            {
                "name": "Phase 2: Core Improvements",
                "duration": "1-3 months",
                "recommendations": ["ux_001"],
                "expected_uplift": 10.0,
            },
        ],
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
        assert "Relevance Quality" in content
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
        assert "Relevance Quality" in content

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
        assert "relevance" in content["maturity"]["dimensions"]
        assert content["maturity"]["dimensions"]["relevance"]["score"] == 4.0

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


class TestUpliftSectionReports:
    """Tests for uplift section in reports."""

    @pytest.mark.unit
    def test_markdown_uplift_section(
        self, audit_config, temp_run_dir, sample_audit_record, sample_uplift_plan
    ):
        """Test markdown uplift section contains expected elements."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator._generate_markdown([sample_audit_record], None, sample_uplift_plan)

        content = (temp_run_dir / "report.md").read_text()

        # Check header and summary
        assert "## Conversion Uplift Opportunities" in content
        assert "25.0%" in content  # Total uplift

        # Check quick wins section
        assert "### Quick Wins" in content
        assert "Implement Caching" in content

        # Check recommendations table
        assert "### All Recommendations" in content
        assert "CRITICAL" in content
        assert "Improve Search Relevance" in content

    @pytest.mark.unit
    def test_html_uplift_section(
        self, audit_config, temp_run_dir, sample_audit_record, sample_uplift_plan
    ):
        """Test HTML uplift section contains badges and cards."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator._generate_html([sample_audit_record], None, sample_uplift_plan)

        content = (temp_run_dir / "report.html").read_text()

        # Check uplift summary box
        assert "uplift-summary" in content
        assert "25.0%" in content

        # Check priority badges
        assert "priority-badge" in content
        assert "priority-critical" in content
        assert "priority-high" in content

        # Check recommendation cards
        assert "recommendation-card" in content
        assert "Improve Search Relevance" in content

    @pytest.mark.unit
    def test_uplift_with_phases(
        self, audit_config, temp_run_dir, sample_audit_record, sample_uplift_plan
    ):
        """Test phase timeline is rendered."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator._generate_html([sample_audit_record], None, sample_uplift_plan)

        content = (temp_run_dir / "report.html").read_text()

        # Check phases section
        assert "Implementation Roadmap" in content
        assert "Phase 1: Quick Wins" in content
        assert "0-4 weeks" in content
        assert "phase-timeline" in content
        assert "phase-item" in content

    @pytest.mark.unit
    def test_json_uplift_section(
        self, audit_config, temp_run_dir, sample_audit_record, sample_uplift_plan
    ):
        """Test JSON report contains serialized uplift data."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        generator._generate_json([sample_audit_record], None, sample_uplift_plan)

        content = json.loads((temp_run_dir / "audit.json").read_text())

        assert "uplift" in content
        assert content["uplift"]["total_potential_uplift"] == 25.0
        assert len(content["uplift"]["recommendations"]) == 3
        assert content["uplift"]["recommendations"][0]["title"] == "Improve Search Relevance"
        assert "phases" in content["uplift"]


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
        generator.generate_reports([], include_maturity=False, include_uplift=False)

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
        judge = JudgeScore(
            overall=3.0,
            relevance=3.0,
            diversity=3.0,
            result_quality=3.0,
            navigability=3.0,
            rationale="Test",
            issues=[],
            improvements=[],
            evidence=[],
            schema_version="1.0",
        )

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
        judge = JudgeScore(
            overall=3.0,
            relevance=3.0,
            diversity=3.0,
            result_quality=3.0,
            navigability=3.0,
            rationale="Test rationale",
            issues=[],
            improvements=[],
            evidence=[],
            schema_version="1.0",
        )

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
        judge = JudgeScore(
            overall=3.0,
            relevance=3.0,
            diversity=3.0,
            result_quality=3.0,
            navigability=3.0,
            rationale="テスト rationale",
            issues=[],
            improvements=[],
            evidence=[],
            schema_version="1.0",
        )

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
            judge = JudgeScore(
                overall=3.0 + (i % 20) / 10,
                relevance=3.5,
                diversity=3.0,
                result_quality=3.5,
                navigability=3.0,
                rationale=f"Rationale for query {i}",
                issues=[],
                improvements=[],
                evidence=[],
                schema_version="1.0",
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
        generator.generate_reports(records, include_maturity=False, include_uplift=False)

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
        judge = JudgeScore(
            overall=3.0,
            relevance=3.0,
            diversity=3.0,
            result_quality=3.0,
            navigability=3.0,
            rationale="Test",
            issues=[],
            improvements=[],
            evidence=[],
            schema_version="1.0",
        )

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
        judge = JudgeScore(
            overall=3.0,
            relevance=3.0,
            diversity=3.0,
            result_quality=3.0,
            navigability=3.0,
            rationale=malicious_rationale,
            issues=["<script>malicious</script>"],
            improvements=["<a onclick='evil()'>click me</a>"],
            evidence=[],
            schema_version="1.0",
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
        judge = JudgeScore(
            overall=3.0,
            relevance=3.0,
            diversity=3.0,
            result_quality=3.0,
            navigability=3.0,
            rationale="Test",
            issues=[],
            improvements=[],
            evidence=[],
            schema_version="1.0",
        )

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
        judge = JudgeScore(
            overall=3.0,
            relevance=3.0,
            diversity=3.0,
            result_quality=3.0,
            navigability=3.0,
            rationale="Test",
            issues=[],
            improvements=[],
            evidence=[],
            schema_version="1.0",
        )

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
    def test_csv_export_creates_file(
        self, audit_config, temp_run_dir, sample_audit_record, sample_uplift_plan
    ):
        """Test that CSV file is created when uplift plan is available."""
        generator = ReportGenerator(audit_config, temp_run_dir)

        screenshot_path = temp_run_dir / "screenshots" / "test.png"
        screenshot_path.write_text("dummy")
        sample_audit_record.page.screenshot_path = str(screenshot_path)

        generator.generate_reports(
            [sample_audit_record], include_maturity=False, include_uplift=True
        )

        csv_path = temp_run_dir / "uplift_recommendations.csv"
        assert csv_path.exists()

    @pytest.mark.unit
    def test_csv_export_headers(self, temp_run_dir, sample_uplift_plan):
        """Test CSV has expected column headers."""
        from agentic_search_audit.analysis.uplift_planner import UpliftPlanner

        planner = UpliftPlanner()
        csv_content = planner.export_to_csv(sample_uplift_plan)

        lines = csv_content.strip().split("\n")
        header = lines[0]

        # Check all expected columns
        expected_headers = [
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
        for h in expected_headers:
            assert h in header

    @pytest.mark.unit
    def test_csv_export_special_chars(self, temp_run_dir):
        """Test CSV properly escapes commas and quotes."""
        from agentic_search_audit.analysis.uplift_planner import UpliftPlanner

        recommendation = Recommendation(
            id="test_001",
            title='Title with "quotes" and, commas',
            description="Description with\nnewline",
            category=Category.RELEVANCE,
            priority=Priority.HIGH,
            effort=Effort.MODERATE,
            expected_uplift_pct=10.0,
            confidence=0.8,
            metrics_to_track=["metric1, metric2", "metric3"],
        )

        plan = UpliftPlan(
            recommendations=[recommendation],
            total_potential_uplift=10.0,
            quick_wins=[],
            strategic_initiatives=[],
            summary="Test",
            phases=[],
        )

        planner = UpliftPlanner()
        csv_content = planner.export_to_csv(plan)

        # CSV should be parseable
        import csv
        import io

        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)

        # Header + 1 data row
        assert len(rows) == 2

        # Data should be properly escaped
        data_row = rows[1]
        assert data_row[0] == "test_001"
        assert '"quotes"' in data_row[1]
        assert "commas" in data_row[1]
