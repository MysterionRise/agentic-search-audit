"""Tests for competitor comparison module."""

from pathlib import Path

import pytest

from agentic_search_audit.core.comparison import (
    ComparisonResult,
    QueryComparison,
    build_comparison,
    find_shared_queries,
)
from agentic_search_audit.core.types import AuditRecord, PageArtifacts, Query
from agentic_search_audit.report.comparison_report import ComparisonReportGenerator
from tests.helpers import make_fqi_judge_score


def _make_record(query_text: str, fqi_dims: dict[str, float], site: str = "site-a") -> AuditRecord:
    """Create a minimal AuditRecord for testing.

    Args:
        query_text: The query text.
        fqi_dims: Dimension score overrides (shorthand keys like query_understanding_score).
        site: Site name.

    Returns:
        AuditRecord instance.
    """
    judge = make_fqi_judge_score(**fqi_dims)
    return AuditRecord(
        site=site,
        query=Query(id="q1", text=query_text),
        items=[],
        page=PageArtifacts(
            url=f"https://{site}.com",
            final_url=f"https://{site}.com/search?q={query_text}",
            html_path="/tmp/test.html",
            screenshot_path="/tmp/test.png",
        ),
        judge=judge,
    )


class TestFindSharedQueries:
    """Tests for find_shared_queries."""

    @pytest.mark.unit
    def test_finds_overlap(self) -> None:
        """Should find queries present in both sets."""
        queries_a = [
            Query(id="a1", text="photo books"),
            Query(id="a2", text="canvas prints"),
            Query(id="a3", text="wall art"),
        ]
        queries_b = [
            Query(id="b1", text="photo books"),
            Query(id="b2", text="canvas prints"),
            Query(id="b3", text="mugs"),
        ]
        shared = find_shared_queries(queries_a, queries_b)
        assert set(shared) == {"photo books", "canvas prints"}

    @pytest.mark.unit
    def test_case_insensitive_matching(self) -> None:
        """Should match queries regardless of case."""
        queries_a = [Query(id="a1", text="Photo Books")]
        queries_b = [Query(id="b1", text="photo books")]
        shared = find_shared_queries(queries_a, queries_b)
        assert len(shared) == 1
        # Returns original casing from queries_a
        assert shared[0] == "Photo Books"

    @pytest.mark.unit
    def test_no_overlap(self) -> None:
        """Should return empty list when no shared queries exist."""
        queries_a = [Query(id="a1", text="photo books")]
        queries_b = [Query(id="b1", text="canvas prints")]
        shared = find_shared_queries(queries_a, queries_b)
        assert shared == []

    @pytest.mark.unit
    def test_empty_inputs(self) -> None:
        """Should handle empty query lists."""
        assert find_shared_queries([], []) == []
        assert find_shared_queries([Query(id="a1", text="test")], []) == []
        assert find_shared_queries([], [Query(id="b1", text="test")]) == []


class TestBuildComparison:
    """Tests for build_comparison."""

    @pytest.mark.unit
    def test_basic_comparison(self) -> None:
        """Should build a comparison with correct aggregates."""
        a_records = [
            _make_record("photo books", {"query_understanding_score": 4.0}, site="mixbook"),
            _make_record("canvas prints", {"query_understanding_score": 3.0}, site="mixbook"),
        ]
        b_records = [
            _make_record("photo books", {"query_understanding_score": 3.0}, site="shutterfly"),
            _make_record("canvas prints", {"query_understanding_score": 4.0}, site="shutterfly"),
        ]

        result = build_comparison(
            site_a_name="mixbook",
            site_b_name="shutterfly",
            site_a_records=a_records,
            site_b_records=b_records,
            shared_queries=["photo books", "canvas prints"],
        )

        assert isinstance(result, ComparisonResult)
        assert len(result.query_comparisons) == 2
        assert result.site_a_name == "mixbook"
        assert result.site_b_name == "shutterfly"

    @pytest.mark.unit
    def test_winner_determination(self) -> None:
        """Should correctly determine per-query and overall winners."""
        a_records = [
            _make_record(
                "photo books",
                {"query_understanding_score": 5.0, "results_relevance_score": 5.0},
                site="mixbook",
            ),
        ]
        b_records = [
            _make_record(
                "photo books",
                {"query_understanding_score": 2.0, "results_relevance_score": 2.0},
                site="shutterfly",
            ),
        ]

        result = build_comparison(
            site_a_name="mixbook",
            site_b_name="shutterfly",
            site_a_records=a_records,
            site_b_records=b_records,
            shared_queries=["photo books"],
        )

        assert result.overall_winner == "mixbook"
        assert result.query_comparisons[0].winner == "mixbook"
        assert result.query_comparisons[0].delta > 0

    @pytest.mark.unit
    def test_tie_score(self) -> None:
        """Should handle tie scores."""
        a_records = [_make_record("photo books", {}, site="mixbook")]
        b_records = [_make_record("photo books", {}, site="shutterfly")]

        result = build_comparison(
            site_a_name="mixbook",
            site_b_name="shutterfly",
            site_a_records=a_records,
            site_b_records=b_records,
            shared_queries=["photo books"],
        )

        assert result.overall_winner == "tie"
        assert result.query_comparisons[0].winner == "tie"
        assert result.query_comparisons[0].delta == 0.0

    @pytest.mark.unit
    def test_empty_shared_queries(self) -> None:
        """Should handle case with no shared queries."""
        result = build_comparison(
            site_a_name="mixbook",
            site_b_name="shutterfly",
            site_a_records=[],
            site_b_records=[],
            shared_queries=[],
        )

        assert result.query_comparisons == []
        assert result.site_a_avg_fqi == 0.0
        assert result.site_b_avg_fqi == 0.0
        assert result.overall_winner == "tie"

    @pytest.mark.unit
    def test_dimension_comparison(self) -> None:
        """Should compute per-dimension averages."""
        a_records = [
            _make_record(
                "photo books",
                {"query_understanding_score": 4.0, "error_handling_score": 2.0},
                site="mixbook",
            ),
        ]
        b_records = [
            _make_record(
                "photo books",
                {"query_understanding_score": 3.0, "error_handling_score": 5.0},
                site="shutterfly",
            ),
        ]

        result = build_comparison(
            site_a_name="mixbook",
            site_b_name="shutterfly",
            site_a_records=a_records,
            site_b_records=b_records,
            shared_queries=["photo books"],
        )

        qu_a, qu_b = result.dimension_comparison["query_understanding"]
        assert qu_a == 4.0
        assert qu_b == 3.0

        eh_a, eh_b = result.dimension_comparison["error_handling"]
        assert eh_a == 2.0
        assert eh_b == 5.0

    @pytest.mark.unit
    def test_maturity_labels_set(self) -> None:
        """Should set maturity labels based on average FQI."""
        a_records = [_make_record("photo books", {}, site="mixbook")]
        b_records = [_make_record("photo books", {}, site="shutterfly")]

        result = build_comparison(
            site_a_name="mixbook",
            site_b_name="shutterfly",
            site_a_records=a_records,
            site_b_records=b_records,
            shared_queries=["photo books"],
        )

        # Both have default scores (3.5 across all dims), FQI should be 3.5 -> Good/L4
        assert result.site_a_maturity != ""
        assert result.site_b_maturity != ""

    @pytest.mark.unit
    def test_missing_records_skipped(self) -> None:
        """Should skip queries where one site has no matching record."""
        a_records = [
            _make_record("photo books", {}, site="mixbook"),
        ]
        b_records = [
            # No "photo books" record, only "canvas prints"
            _make_record("canvas prints", {}, site="shutterfly"),
        ]

        result = build_comparison(
            site_a_name="mixbook",
            site_b_name="shutterfly",
            site_a_records=a_records,
            site_b_records=b_records,
            shared_queries=["photo books", "canvas prints"],
        )

        # Neither query has matching records on both sides
        assert len(result.query_comparisons) == 0


class TestComparisonReportGenerator:
    """Tests for ComparisonReportGenerator."""

    @pytest.mark.unit
    def test_generate_creates_files(self, tmp_path: Path) -> None:
        """Should generate both markdown and HTML reports."""
        result = ComparisonResult(
            site_a_name="mixbook",
            site_b_name="shutterfly",
            site_a_avg_fqi=3.8,
            site_b_avg_fqi=3.2,
            site_a_maturity="L4_INTELLIGENT",
            site_b_maturity="L3_ENHANCED",
            query_comparisons=[
                QueryComparison(
                    query_text="photo books",
                    site_a_fqi=4.0,
                    site_b_fqi=3.0,
                    delta=1.0,
                    site_a_dimensions={"query_understanding": 4.0},
                    site_b_dimensions={"query_understanding": 3.0},
                    winner="mixbook",
                ),
            ],
            dimension_comparison={
                "query_understanding": (4.0, 3.0),
                "results_relevance": (3.5, 3.5),
                "result_presentation": (3.5, 3.0),
                "advanced_features": (3.8, 3.2),
                "error_handling": (4.0, 3.0),
            },
            overall_winner="mixbook",
        )

        gen = ComparisonReportGenerator(result, tmp_path)
        gen.generate()

        assert (tmp_path / "comparison_report.md").exists()
        assert (tmp_path / "comparison_report.html").exists()

    @pytest.mark.unit
    def test_markdown_content(self, tmp_path: Path) -> None:
        """Markdown report should contain key content."""
        result = ComparisonResult(
            site_a_name="SiteA",
            site_b_name="SiteB",
            site_a_avg_fqi=4.0,
            site_b_avg_fqi=3.0,
            site_a_maturity="L4_INTELLIGENT",
            site_b_maturity="L3_ENHANCED",
            query_comparisons=[
                QueryComparison(
                    query_text="test query",
                    site_a_fqi=4.0,
                    site_b_fqi=3.0,
                    delta=1.0,
                    site_a_dimensions={},
                    site_b_dimensions={},
                    winner="SiteA",
                ),
            ],
            dimension_comparison={
                "query_understanding": (4.0, 3.0),
                "results_relevance": (4.0, 3.0),
                "result_presentation": (4.0, 3.0),
                "advanced_features": (4.0, 3.0),
                "error_handling": (4.0, 3.0),
            },
            overall_winner="SiteA",
        )

        gen = ComparisonReportGenerator(result, tmp_path)
        gen.generate()

        md_content = (tmp_path / "comparison_report.md").read_text()
        assert "SiteA" in md_content
        assert "SiteB" in md_content
        assert "test query" in md_content
        assert "Overall Winner: SiteA" in md_content

    @pytest.mark.unit
    def test_html_content(self, tmp_path: Path) -> None:
        """HTML report should contain key content."""
        result = ComparisonResult(
            site_a_name="Alpha",
            site_b_name="Beta",
            site_a_avg_fqi=3.5,
            site_b_avg_fqi=3.5,
            site_a_maturity="L4_INTELLIGENT",
            site_b_maturity="L4_INTELLIGENT",
            query_comparisons=[],
            dimension_comparison={
                "query_understanding": (3.5, 3.5),
                "results_relevance": (3.5, 3.5),
                "result_presentation": (3.5, 3.5),
                "advanced_features": (3.5, 3.5),
                "error_handling": (3.5, 3.5),
            },
            overall_winner="tie",
        )

        gen = ComparisonReportGenerator(result, tmp_path)
        gen.generate()

        html_content = (tmp_path / "comparison_report.html").read_text()
        assert "Alpha" in html_content
        assert "Beta" in html_content
        assert "<!DOCTYPE html>" in html_content
        assert "Overall Winner: tie" in html_content
