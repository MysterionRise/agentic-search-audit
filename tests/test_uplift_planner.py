"""Tests for conversion uplift planner."""

from datetime import datetime

import pytest

from agentic_search_audit.analysis.uplift_planner import (
    Category,
    Effort,
    Priority,
    Recommendation,
    UpliftPlan,
    UpliftPlanner,
)
from agentic_search_audit.core.types import (
    AuditRecord,
    JudgeScore,
    PageArtifacts,
    Query,
    ResultItem,
)


class TestRecommendation:
    """Tests for Recommendation dataclass."""

    def test_creation(self):
        """Test recommendation creation."""
        rec = Recommendation(
            id="test_001",
            title="Test Recommendation",
            description="A test recommendation",
            category=Category.RELEVANCE,
            priority=Priority.HIGH,
            effort=Effort.MODERATE,
            expected_uplift_pct=10.0,
            confidence=0.8,
        )

        assert rec.id == "test_001"
        assert rec.priority == Priority.HIGH
        assert rec.expected_uplift_pct == 10.0

    def test_roi_score_calculation(self):
        """Test ROI score calculation."""
        # Quick win with high uplift
        quick_win = Recommendation(
            id="qw_001",
            title="Quick Win",
            description="Quick win recommendation",
            category=Category.UX,
            priority=Priority.HIGH,
            effort=Effort.QUICK_WIN,
            expected_uplift_pct=5.0,
            confidence=0.9,
        )

        # Major effort with higher uplift
        major = Recommendation(
            id="maj_001",
            title="Major Initiative",
            description="Major initiative",
            category=Category.RELEVANCE,
            priority=Priority.MEDIUM,
            effort=Effort.MAJOR,
            expected_uplift_pct=15.0,
            confidence=0.7,
        )

        # Quick win should have higher ROI despite lower uplift
        assert quick_win.roi_score > major.roi_score

    def test_roi_score_formula(self):
        """Test ROI score formula correctness."""
        rec = Recommendation(
            id="test",
            title="Test",
            description="Test",
            category=Category.TECHNICAL,
            priority=Priority.LOW,
            effort=Effort.MODERATE,  # weight = 2
            expected_uplift_pct=10.0,
            confidence=0.5,
        )

        # ROI = (uplift * confidence) / effort_weight
        # = (10.0 * 0.5) / 2 = 2.5
        assert rec.roi_score == 2.5


class TestUpliftPlanner:
    """Tests for UpliftPlanner class."""

    @pytest.fixture
    def planner(self):
        """Create planner instance."""
        return UpliftPlanner()

    @pytest.fixture
    def sample_records(self):
        """Create sample audit records."""
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
                judge=JudgeScore(
                    overall=3.5,
                    relevance=3.8,
                    diversity=3.2,
                    result_quality=3.6,
                    navigability=3.4,
                    rationale="Good search results",
                    issues=["Minor issue"],
                    improvements=["Add filters"],
                ),
            )
            records.append(record)
        return records

    @pytest.fixture
    def poor_records(self):
        """Create records with poor performance."""
        records = []
        for i in range(5):
            record = AuditRecord(
                site="https://example.com",
                query=Query(id=f"q{i}", text=f"test query {i}"),
                items=[] if i < 2 else [ResultItem(rank=1, title="Product")],  # High zero-result rate
                page=PageArtifacts(
                    url="https://example.com",
                    final_url="https://example.com/search",
                    html_path="/tmp/test.html",
                    screenshot_path="/tmp/test.png",
                    ts=datetime.now(),
                ),
                judge=JudgeScore(
                    overall=1.5,
                    relevance=1.8,
                    diversity=1.5,
                    result_quality=1.6,
                    navigability=1.4,
                    rationale="Poor search results",
                    issues=["Typo not handled", "No results", "Missing filters"],
                    improvements=["Add spell correction", "Add filters"],
                ),
            )
            records.append(record)
        return records

    def test_generate_plan_basic(self, planner, sample_records):
        """Test basic plan generation."""
        plan = planner.generate_plan(sample_records)

        assert isinstance(plan, UpliftPlan)
        assert len(plan.recommendations) > 0
        assert plan.total_potential_uplift > 0
        assert plan.summary != ""

    def test_generate_plan_with_poor_records(self, planner, poor_records):
        """Test plan generation with poor performance records."""
        plan = planner.generate_plan(poor_records)

        # Should identify critical issues
        critical_recs = [r for r in plan.recommendations if r.priority == Priority.CRITICAL]
        assert len(critical_recs) > 0

        # Should have higher urgency recommendations
        assert any(r.priority in [Priority.CRITICAL, Priority.HIGH] for r in plan.recommendations)

    def test_recommendations_sorted_by_roi(self, planner, sample_records):
        """Test that recommendations are sorted by ROI score."""
        plan = planner.generate_plan(sample_records)

        for i in range(len(plan.recommendations) - 1):
            assert plan.recommendations[i].roi_score >= plan.recommendations[i + 1].roi_score

    def test_quick_wins_identified(self, planner, sample_records):
        """Test that quick wins are correctly identified."""
        plan = planner.generate_plan(sample_records)

        for rec in plan.quick_wins:
            assert rec.effort == Effort.QUICK_WIN

    def test_strategic_initiatives_identified(self, planner, sample_records):
        """Test that strategic initiatives are correctly identified."""
        plan = planner.generate_plan(sample_records)

        for rec in plan.strategic_initiatives:
            assert rec.effort in [Effort.SIGNIFICANT, Effort.MAJOR]

    def test_phases_generated(self, planner, sample_records):
        """Test that implementation phases are generated."""
        plan = planner.generate_plan(sample_records)

        assert isinstance(plan.phases, list)
        # Should have at least some phases
        if plan.recommendations:
            assert len(plan.phases) > 0

    def test_max_recommendations_limit(self, planner, sample_records):
        """Test that max recommendations limit is respected."""
        plan = planner.generate_plan(sample_records, max_recommendations=5)
        assert len(plan.recommendations) <= 5

    def test_total_uplift_capped(self, planner, sample_records):
        """Test that total uplift is capped at reasonable maximum."""
        plan = planner.generate_plan(sample_records)
        assert plan.total_potential_uplift <= 50.0

    def test_export_to_csv(self, planner, sample_records):
        """Test CSV export functionality."""
        plan = planner.generate_plan(sample_records)
        csv_output = planner.export_to_csv(plan)

        assert isinstance(csv_output, str)
        assert "ID" in csv_output  # Header
        assert "Title" in csv_output
        assert "Priority" in csv_output

        # Check that recommendations are in CSV
        for rec in plan.recommendations:
            assert rec.id in csv_output

    def test_empty_records(self, planner):
        """Test handling of empty records."""
        plan = planner.generate_plan([])

        assert isinstance(plan, UpliftPlan)
        # Should still generate some general recommendations
        assert plan.total_potential_uplift >= 0


class TestPriority:
    """Tests for Priority enum."""

    def test_priority_values(self):
        """Test priority string values."""
        assert Priority.CRITICAL.value == "critical"
        assert Priority.HIGH.value == "high"
        assert Priority.MEDIUM.value == "medium"
        assert Priority.LOW.value == "low"


class TestEffort:
    """Tests for Effort enum."""

    def test_effort_values(self):
        """Test effort string values."""
        assert Effort.QUICK_WIN.value == "quick_win"
        assert Effort.MODERATE.value == "moderate"
        assert Effort.SIGNIFICANT.value == "significant"
        assert Effort.MAJOR.value == "major"


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
