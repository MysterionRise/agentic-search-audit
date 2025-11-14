"""Tests for report generation."""

import tempfile
from pathlib import Path

import pytest

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
from agentic_search_audit.report.generator import ReportGenerator


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
