"""Tests for maturity assessment framework."""

from datetime import datetime

import pytest

from agentic_search_audit.analysis.benchmarks import (
    Industry,
    IndustryBenchmarks,
    get_industry_benchmark,
)
from agentic_search_audit.analysis.maturity import (
    DimensionScore,
    MaturityEvaluator,
    MaturityLevel,
    MaturityReport,
)
from agentic_search_audit.core.types import (
    AuditRecord,
    PageArtifacts,
    Query,
    ResultItem,
)
from tests.helpers import make_fqi_judge_score


class TestMaturityLevel:
    """Tests for MaturityLevel enum."""

    def test_level_values(self):
        """Test maturity level numeric values."""
        assert MaturityLevel.L1_BASIC == 1
        assert MaturityLevel.L2_FUNCTIONAL == 2
        assert MaturityLevel.L3_ENHANCED == 3
        assert MaturityLevel.L4_INTELLIGENT == 4
        assert MaturityLevel.L5_AGENTIC == 5

    def test_level_comparison(self):
        """Test maturity level comparison."""
        assert MaturityLevel.L1_BASIC < MaturityLevel.L5_AGENTIC
        assert MaturityLevel.L3_ENHANCED > MaturityLevel.L2_FUNCTIONAL


class TestMaturityEvaluator:
    """Tests for MaturityEvaluator class."""

    @pytest.fixture
    def evaluator(self):
        """Create evaluator instance."""
        return MaturityEvaluator()

    @pytest.fixture
    def sample_records(self):
        """Create sample audit records for testing."""
        records = []
        for i in range(5):
            record = AuditRecord(
                site="https://example.com",
                query=Query(id=f"q{i}", text=f"test query {i}"),
                items=[
                    ResultItem(rank=1, title="Product 1", price="$10"),
                    ResultItem(rank=2, title="Product 2", price="$20"),
                ],
                page=PageArtifacts(
                    url="https://example.com",
                    final_url="https://example.com/search",
                    html_path="/tmp/test.html",
                    screenshot_path="/tmp/test.png",
                    ts=datetime.now(),
                ),
                judge=make_fqi_judge_score(
                    query_understanding_score=3.8 + i * 0.1,
                    results_relevance_score=3.5 + i * 0.1,
                    result_presentation_score=3.6 + i * 0.1,
                    advanced_features_score=3.2 + i * 0.1,
                    error_handling_score=3.4 + i * 0.1,
                    rationale="Good search results",
                    issues=["Minor relevance issue"],
                    improvements=["Add more filters"],
                ),
            )
            records.append(record)
        return records

    @pytest.fixture
    def low_score_records(self):
        """Create sample records with low scores."""
        records = []
        for i in range(3):
            record = AuditRecord(
                site="https://example.com",
                query=Query(id=f"q{i}", text=f"test query {i}"),
                items=[],  # No results
                page=PageArtifacts(
                    url="https://example.com",
                    final_url="https://example.com/search",
                    html_path="/tmp/test.html",
                    screenshot_path="/tmp/test.png",
                    ts=datetime.now(),
                ),
                judge=make_fqi_judge_score(
                    query_understanding_score=1.2,
                    results_relevance_score=1.5,
                    result_presentation_score=1.5,
                    advanced_features_score=1.8,
                    error_handling_score=1.6,
                    rationale="Poor search results",
                    issues=["Typo not handled", "No results found", "Broken filters"],
                    improvements=["Add spell correction", "Improve synonym matching"],
                ),
            )
            records.append(record)
        return records

    def test_evaluate_with_good_records(self, evaluator, sample_records):
        """Test evaluation with good quality records."""
        report = evaluator.evaluate(sample_records)

        assert isinstance(report, MaturityReport)
        assert report.overall_level in [
            MaturityLevel.L3_ENHANCED,
            MaturityLevel.L4_INTELLIGENT,
        ]
        assert 3.0 <= report.overall_score <= 4.5
        assert len(report.dimensions) == 5
        assert report.executive_summary != ""

    def test_evaluate_with_low_scores(self, evaluator, low_score_records):
        """Test evaluation with low quality records."""
        report = evaluator.evaluate(low_score_records)

        assert report.overall_level in [
            MaturityLevel.L1_BASIC,
            MaturityLevel.L2_FUNCTIONAL,
        ]
        assert report.overall_score < 2.5
        assert len(report.weaknesses) > 0
        assert len(report.priority_improvements) > 0

    def test_evaluate_empty_records(self, evaluator):
        """Test evaluation with no records."""
        report = evaluator.evaluate([])

        assert report.overall_level == MaturityLevel.L1_BASIC
        assert report.overall_score == 0.0
        assert len(report.dimensions) == 0

    def test_dimension_weights_sum_to_one(self, evaluator):
        """Test that dimension weights sum to 1.0."""
        total_weight = sum(evaluator.DIMENSION_WEIGHTS.values())
        assert abs(total_weight - 1.0) < 0.001

    def test_score_to_level_boundaries(self, evaluator):
        """Test score to level conversion at boundaries."""
        assert evaluator._score_to_level(0.5) == MaturityLevel.L1_BASIC
        assert evaluator._score_to_level(1.5) == MaturityLevel.L2_FUNCTIONAL
        assert evaluator._score_to_level(2.5) == MaturityLevel.L3_ENHANCED
        assert evaluator._score_to_level(3.5) == MaturityLevel.L4_INTELLIGENT
        assert evaluator._score_to_level(4.5) == MaturityLevel.L5_AGENTIC

    def test_identify_strengths(self, evaluator, sample_records):
        """Test strength identification."""
        report = evaluator.evaluate(sample_records)
        # With good scores, should identify some strengths
        assert isinstance(report.strengths, list)

    def test_identify_weaknesses(self, evaluator, low_score_records):
        """Test weakness identification."""
        report = evaluator.evaluate(low_score_records)
        assert len(report.weaknesses) > 0

    def test_prioritize_improvements(self, evaluator, sample_records):
        """Test improvement prioritization."""
        report = evaluator.evaluate(sample_records)
        assert isinstance(report.priority_improvements, list)
        # Should have at most 5 improvements
        assert len(report.priority_improvements) <= 5

    def test_executive_summary_content(self, evaluator, sample_records):
        """Test executive summary contains key information."""
        report = evaluator.evaluate(sample_records)

        assert str(len(sample_records)) in report.executive_summary
        assert "Maturity Level" in report.executive_summary
        assert str(report.overall_level.value) in report.executive_summary


class TestDimensionScore:
    """Tests for DimensionScore dataclass."""

    def test_creation(self):
        """Test dimension score creation."""
        score = DimensionScore(
            name="Test Dimension",
            score=3.5,
            level=MaturityLevel.L4_INTELLIGENT,
            findings=["Finding 1"],
            recommendations=["Recommendation 1"],
        )

        assert score.name == "Test Dimension"
        assert score.score == 3.5
        assert score.level == MaturityLevel.L4_INTELLIGENT
        assert len(score.findings) == 1
        assert len(score.recommendations) == 1

    def test_default_lists(self):
        """Test default empty lists."""
        score = DimensionScore(
            name="Test",
            score=3.0,
            level=MaturityLevel.L3_ENHANCED,
        )

        assert score.findings == []
        assert score.recommendations == []


class TestIndustryBenchmarks:
    """Tests for industry benchmarks."""

    def test_get_benchmark_by_enum(self):
        """Test getting benchmark by enum."""
        benchmark = get_industry_benchmark(Industry.ECOMMERCE)
        assert benchmark.industry == Industry.ECOMMERCE
        assert benchmark.name == "E-commerce (General)"

    def test_get_benchmark_by_string(self):
        """Test getting benchmark by string."""
        benchmark = get_industry_benchmark("fashion")
        assert benchmark.industry == Industry.FASHION

    def test_get_benchmark_invalid_string(self):
        """Test getting benchmark with invalid string falls back to general."""
        benchmark = get_industry_benchmark("invalid_industry")
        assert benchmark.industry == Industry.GENERAL

    def test_list_industries(self):
        """Test listing all industries."""
        industries = IndustryBenchmarks.list_industries()
        assert "ecommerce" in industries
        assert "fashion" in industries
        assert "general" in industries

    def test_compare_to_industry(self):
        """Test comparing scores to industry benchmark."""
        scores = {
            "query_understanding": 4.0,
            "results_relevance": 3.5,
            "result_presentation": 3.8,
            "advanced_features": 3.6,
            "error_handling": 3.6,
            "fqi": 3.7,
        }

        result = IndustryBenchmarks.compare_to_industry(scores, Industry.ECOMMERCE)

        assert result["industry"] == "ecommerce"
        assert "comparisons" in result
        assert "query_understanding" in result["comparisons"]
        assert "percentile" in result["comparisons"]["query_understanding"]

    def test_benchmark_compare_method(self):
        """Test benchmark compare method directly."""
        benchmark = get_industry_benchmark(Industry.FASHION)
        scores = {"results_relevance": 4.5, "fqi": 3.0}

        comparison = benchmark.compare(scores)

        assert "results_relevance" in comparison
        assert comparison["results_relevance"]["status"] == "top_performer"
        assert "fqi" in comparison

    def test_percentile_rating(self):
        """Test percentile rating strings."""
        assert "Top 10%" in IndustryBenchmarks.get_percentile_rating(95)
        assert "Top 25%" in IndustryBenchmarks.get_percentile_rating(80)
        assert "Top 50%" in IndustryBenchmarks.get_percentile_rating(55)
        assert "Bottom 50%" in IndustryBenchmarks.get_percentile_rating(30)
        assert "Bottom 25%" in IndustryBenchmarks.get_percentile_rating(10)

    def test_benchmark_has_required_fields(self):
        """Test all benchmarks have required fields."""
        for industry in Industry:
            benchmark = get_industry_benchmark(industry)

            assert benchmark.results_relevance_avg > 0
            assert benchmark.results_relevance_top_quartile > benchmark.results_relevance_avg
            assert benchmark.sample_size > 0
            assert benchmark.last_updated != ""
