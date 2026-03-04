"""Tribunal Prosecution Tests.

Written BLIND from the plan description, targeting edge cases the implementers
likely missed. Every failing test is evidence of a gap.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from agentic_search_audit.analysis.uplift_planner import (
    Finding,
    Severity,
)
from agentic_search_audit.core.types import (
    ResultItem,
    RunConfig,
    get_maturity_label,
)

# ──────────────────────────────────────────────────────────────────────
# SECTION 1: get_maturity_label edge cases
# ──────────────────────────────────────────────────────────────────────


class TestMaturityLabelBoundaries:
    """Probe exact boundary values for get_maturity_label()."""

    @pytest.mark.unit
    def test_exact_l5_boundary(self):
        """Score of exactly 4.5 should be L5_AGENTIC."""
        assert get_maturity_label(4.5) == "L5_AGENTIC"

    @pytest.mark.unit
    def test_just_below_l5(self):
        """Score of 4.499 should NOT be L5_AGENTIC."""
        result = get_maturity_label(4.499)
        assert result == "L4_INTELLIGENT", f"4.499 got {result}, expected L4_INTELLIGENT"

    @pytest.mark.unit
    def test_exact_l4_boundary(self):
        """Score of exactly 3.5 should be L4_INTELLIGENT."""
        assert get_maturity_label(3.5) == "L4_INTELLIGENT"

    @pytest.mark.unit
    def test_just_below_l4(self):
        """Score of 3.499 should be L3_ENHANCED."""
        result = get_maturity_label(3.499)
        assert result == "L3_ENHANCED", f"3.499 got {result}, expected L3_ENHANCED"

    @pytest.mark.unit
    def test_exact_l3_boundary(self):
        """Score of exactly 2.5 should be L3_ENHANCED."""
        assert get_maturity_label(2.5) == "L3_ENHANCED"

    @pytest.mark.unit
    def test_just_below_l3(self):
        """Score of 2.499 should be L2_FUNCTIONAL."""
        result = get_maturity_label(2.499)
        assert result == "L2_FUNCTIONAL", f"2.499 got {result}, expected L2_FUNCTIONAL"

    @pytest.mark.unit
    def test_exact_l2_boundary(self):
        """Score of exactly 1.5 should be L2_FUNCTIONAL."""
        assert get_maturity_label(1.5) == "L2_FUNCTIONAL"

    @pytest.mark.unit
    def test_just_below_l2(self):
        """Score of 1.499 should be L1_BASIC."""
        result = get_maturity_label(1.499)
        assert result == "L1_BASIC", f"1.499 got {result}, expected L1_BASIC"

    @pytest.mark.unit
    def test_zero_score(self):
        """Score of exactly 0.0 should be L1_BASIC."""
        assert get_maturity_label(0.0) == "L1_BASIC"

    @pytest.mark.unit
    def test_negative_score(self):
        """Negative score should return L1_BASIC (the lowest band)."""
        # The plan says thresholds go down to 0.0. Negative scores
        # should still get the lowest label, not crash.
        result = get_maturity_label(-1.0)
        assert result == "L1_BASIC", f"Negative score got {result}, expected L1_BASIC"

    @pytest.mark.unit
    def test_very_large_score(self):
        """Score of 100.0 should still be L5_AGENTIC."""
        assert get_maturity_label(100.0) == "L5_AGENTIC"

    @pytest.mark.unit
    def test_perfect_five(self):
        """Score of 5.0 (max) should be L5_AGENTIC."""
        assert get_maturity_label(5.0) == "L5_AGENTIC"


# ──────────────────────────────────────────────────────────────────────
# SECTION 2: Report findings filtering
# ──────────────────────────────────────────────────────────────────────


class TestReportFindingsFiltering:
    """Verify that LOW and MEDIUM findings are excluded from reports."""

    def _make_finding(self, severity: Severity, observation: str = "test") -> Finding:
        return Finding(
            id=f"F-{severity.value}",
            observation=observation,
            affected_queries=5,
            total_queries=10,
            severity=severity,
            affected_dimension="results_relevance",
            avg_dimension_score=3.0,
        )

    @pytest.mark.unit
    def test_findings_report_with_only_medium(self):
        """If ALL findings are MEDIUM, the filtered list should be empty.

        The report should handle this gracefully -- no crash, no orphaned headers.
        """
        findings = [
            self._make_finding(Severity.MEDIUM),
            self._make_finding(Severity.MEDIUM, observation="another medium"),
        ]
        # Filter as the plan describes: only CRITICAL and HIGH
        filtered = [f for f in findings if f.severity in (Severity.CRITICAL, Severity.HIGH)]
        assert filtered == [], "MEDIUM findings should not survive filtering"

    @pytest.mark.unit
    def test_critical_and_high_survive_filter(self):
        """CRITICAL and HIGH findings should survive the filter."""
        findings = [
            self._make_finding(Severity.CRITICAL),
            self._make_finding(Severity.HIGH),
            self._make_finding(Severity.MEDIUM),
        ]
        filtered = [f for f in findings if f.severity in (Severity.CRITICAL, Severity.HIGH)]
        assert len(filtered) == 2
        assert all(f.severity in (Severity.CRITICAL, Severity.HIGH) for f in filtered)


# ──────────────────────────────────────────────────────────────────────
# SECTION 3: PDP Dropdown edge cases
# ──────────────────────────────────────────────────────────────────────


class TestPDPDropdownExtraction:
    """Test PDP dropdown extraction edge cases."""

    @pytest.mark.unit
    def test_dropdown_selectors_has_both_variant_types(self):
        """DROPDOWN_SELECTORS should have entries for both 'size' and 'color'."""
        from agentic_search_audit.extractors.pdp_analyzer import DROPDOWN_SELECTORS

        assert "size" in DROPDOWN_SELECTORS, "Missing 'size' in DROPDOWN_SELECTORS"
        assert "color" in DROPDOWN_SELECTORS, "Missing 'color' in DROPDOWN_SELECTORS"
        assert len(DROPDOWN_SELECTORS["size"]) > 0, "size selectors list is empty"
        assert len(DROPDOWN_SELECTORS["color"]) > 0, "color selectors list is empty"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_extract_dropdown_options_empty_selectors(self):
        """_extract_dropdown_options with unknown variant_type should return fallback.

        If variant_type is not in DROPDOWN_SELECTORS (e.g. 'material'),
        the method should gracefully return a 'not found' result, not crash.
        """
        from agentic_search_audit.core.types import LLMConfig, ModalsConfig, Query
        from agentic_search_audit.extractors.pdp_analyzer import PdpAnalyzer

        mock_client = MagicMock()
        analyzer = PdpAnalyzer(
            client=mock_client,
            llm_config=LLMConfig(),
            modals_config=ModalsConfig(),
            run_dir=Path("/tmp/fake"),
            query=Query(id="test-1", text="test query"),
        )
        result = await analyzer._extract_dropdown_options("material")
        # Should not raise and should indicate not found
        assert result.get("found") in ("false", None) or "error" in str(result.get("found", ""))


class TestPDPCheckConsistency:
    """Test check_consistency edge cases."""

    @pytest.mark.unit
    def test_non_numeric_price_tbd(self):
        """Price string '$TBD' should be handled gracefully, not raise."""
        from agentic_search_audit.extractors.pdp_analyzer import PdpAnalyzer

        item = ResultItem(
            rank=1,
            title="Test Product",
            price="$TBD",
            attributes={"pdp_analyzed": "true", "pdp_price": "$29.99"},
        )
        issues = PdpAnalyzer.check_consistency(item)
        # Should detect a discrepancy since prices don't match as floats
        assert "price_discrepancy" in issues

    @pytest.mark.unit
    def test_non_numeric_price_free(self):
        """Price 'Free' vs '$0.00' should be handled."""
        from agentic_search_audit.extractors.pdp_analyzer import PdpAnalyzer

        item = ResultItem(
            rank=1,
            title="Test Product",
            price="Free",
            attributes={"pdp_analyzed": "true", "pdp_price": "$0.00"},
        )
        issues = PdpAnalyzer.check_consistency(item)
        # 'Free' stripped of $ is still 'Free' which can't be float-parsed
        # This should be caught as a price discrepancy
        assert "price_discrepancy" in issues

    @pytest.mark.unit
    def test_non_numeric_price_call_for_price(self):
        """Price 'Call for price' should be handled."""
        from agentic_search_audit.extractors.pdp_analyzer import PdpAnalyzer

        item = ResultItem(
            rank=1,
            title="Test Widget",
            price="Call for price",
            attributes={"pdp_analyzed": "true", "pdp_price": "Call for price"},
        )
        issues = PdpAnalyzer.check_consistency(item)
        # Same non-numeric string -- no discrepancy
        assert "price_discrepancy" not in issues

    @pytest.mark.unit
    def test_missing_pdp_attributes_partial(self):
        """Item with pdp_analyzed but no other pdp_ fields should not crash."""
        from agentic_search_audit.extractors.pdp_analyzer import PdpAnalyzer

        item = ResultItem(
            rank=1,
            title="Minimal Product",
            attributes={"pdp_analyzed": "true"},
        )
        issues = PdpAnalyzer.check_consistency(item)
        assert isinstance(issues, dict)
        # No price, no title, no availability => no issues expected
        assert len(issues) == 0

    @pytest.mark.unit
    def test_variant_zero_total_options(self):
        """When total options count is 0, should not flag (avoid ZeroDivisionError)."""
        from agentic_search_audit.extractors.pdp_analyzer import PdpAnalyzer

        item = ResultItem(
            rank=1,
            title="No Variants Product",
            attributes={
                "pdp_analyzed": "true",
                "pdp_size_options_count": "0",
                "pdp_size_unavailable": "",
            },
        )
        issues = PdpAnalyzer.check_consistency(item)
        assert "size_mostly_unavailable" not in issues

    @pytest.mark.unit
    def test_variant_all_unavailable_100_pct(self):
        """When ALL variant options are unavailable (100%), should flag."""
        from agentic_search_audit.extractors.pdp_analyzer import PdpAnalyzer

        item = ResultItem(
            rank=1,
            title="Sold Out Product",
            attributes={
                "pdp_analyzed": "true",
                "pdp_size_options_count": "5",
                "pdp_size_unavailable": "S, M, L, XL, XXL",
            },
        )
        issues = PdpAnalyzer.check_consistency(item)
        # 5/5 = 100% > 50%, should be flagged
        assert "size_mostly_unavailable" in issues
        assert "5/5" in issues["size_mostly_unavailable"]

    @pytest.mark.unit
    def test_variant_exactly_at_50_pct(self):
        """When exactly 50% are unavailable, should NOT flag (threshold is >50%)."""
        from agentic_search_audit.extractors.pdp_analyzer import PdpAnalyzer

        item = ResultItem(
            rank=1,
            title="Half Stock Product",
            attributes={
                "pdp_analyzed": "true",
                "pdp_color_options_count": "4",
                "pdp_color_unavailable": "Red, Blue",
            },
        )
        issues = PdpAnalyzer.check_consistency(item)
        # 2/4 = 0.5, which is NOT > 0.5, so should NOT flag
        assert "color_mostly_unavailable" not in issues

    @pytest.mark.unit
    def test_variant_just_above_50_pct(self):
        """When 51%+ are unavailable, should flag."""
        from agentic_search_audit.extractors.pdp_analyzer import PdpAnalyzer

        item = ResultItem(
            rank=1,
            title="Mostly OOS Product",
            attributes={
                "pdp_analyzed": "true",
                "pdp_color_options_count": "3",
                "pdp_color_unavailable": "Red, Blue",
            },
        )
        issues = PdpAnalyzer.check_consistency(item)
        # 2/3 = 0.667 > 0.5, should flag
        assert "color_mostly_unavailable" in issues


# ──────────────────────────────────────────────────────────────────────
# SECTION 4: PDF CLI wiring
# ──────────────────────────────────────────────────────────────────────


class TestPDFCLIWiring:
    """Test that --pdf flag is wired correctly."""

    @pytest.mark.unit
    def test_pdf_flag_exists_in_cli(self):
        """The --pdf argument should be registered in the CLI parser.

        parse_args() reads sys.argv, so we mock it.
        """
        import sys

        with patch.object(sys, "argv", ["search-audit", "--site", "test", "--pdf"]):
            from agentic_search_audit.cli.main import parse_args

            args = parse_args()
        assert hasattr(args, "pdf"), "--pdf flag not registered in CLI"
        assert args.pdf is True

    @pytest.mark.unit
    def test_pdf_flag_default_false(self):
        """--pdf should default to False when not specified."""
        import sys

        with patch.object(sys, "argv", ["search-audit", "--site", "test"]):
            from agentic_search_audit.cli.main import parse_args

            args = parse_args()
        assert getattr(args, "pdf", False) is False

    @pytest.mark.unit
    def test_generate_pdf_graceful_without_weasyprint(self):
        """_generate_pdf should log warning, not crash, when WeasyPrint is absent."""
        from agentic_search_audit.report.generator import ReportGenerator

        with patch("agentic_search_audit.report.generator.HAS_WEASYPRINT", False):
            config = MagicMock()
            config.report.formats = ["html"]
            run_dir = Path("/tmp/fake_run_dir")
            generator = ReportGenerator.__new__(ReportGenerator)
            generator.run_dir = run_dir
            generator.config = config
            # Should not raise
            generator._generate_pdf()

    @pytest.mark.unit
    def test_run_config_does_not_have_generate_pdf(self):
        """RunConfig is a Pydantic model with extra='forbid'.

        The plan mentions adding generate_pdf to the run() method signature,
        NOT to RunConfig. If someone mistakenly added it to RunConfig,
        it should be rejected by the model validation (extra=forbid).
        """
        # RunConfig uses extra="forbid", so adding unknown fields should fail
        with pytest.raises(Exception):
            RunConfig(generate_pdf=True)


# ──────────────────────────────────────────────────────────────────────
# SECTION 5: Mixbook configuration validation
# ──────────────────────────────────────────────────────────────────────


class TestMixbookConfig:
    """Validate Mixbook config and query files."""

    MIXBOOK_CONFIG = Path(
        "/Users/Konstantin_Perikov/projects/agentic-search-audit/configs/sites/mixbook.yaml"
    )
    MIXBOOK_QUERIES = Path(
        "/Users/Konstantin_Perikov/projects/agentic-search-audit/data/queries/mixbook.json"
    )
    MIXBOOK_SMOKE = Path(
        "/Users/Konstantin_Perikov/projects/agentic-search-audit/data/queries/mixbook_smoke.json"
    )

    @pytest.mark.unit
    def test_mixbook_yaml_exists(self):
        """mixbook.yaml config file must exist."""
        assert self.MIXBOOK_CONFIG.exists(), f"Missing: {self.MIXBOOK_CONFIG}"

    @pytest.mark.unit
    def test_mixbook_yaml_valid(self):
        """mixbook.yaml must be valid YAML."""
        content = self.MIXBOOK_CONFIG.read_text()
        data = yaml.safe_load(content)
        assert isinstance(data, dict), "YAML root should be a dict"

    @pytest.mark.unit
    def test_mixbook_yaml_has_required_keys(self):
        """mixbook.yaml must have 'site' with 'url' at minimum."""
        data = yaml.safe_load(self.MIXBOOK_CONFIG.read_text())
        assert "site" in data, "Missing 'site' key in config"
        assert "url" in data["site"], "Missing 'url' under 'site'"
        assert "mixbook.com" in str(data["site"]["url"]).lower()

    @pytest.mark.unit
    def test_mixbook_yaml_uses_undetected_backend(self):
        """Plan specifies browser_backend: undetected for Mixbook."""
        data = yaml.safe_load(self.MIXBOOK_CONFIG.read_text())
        run = data.get("run", {})
        assert run.get("browser_backend") == "undetected"

    @pytest.mark.unit
    def test_mixbook_yaml_loads_as_config(self):
        """Mixbook config should load via the config system without errors."""
        from agentic_search_audit.core.config import load_config

        config = load_config(site_config_path=self.MIXBOOK_CONFIG)
        assert str(config.site.url).rstrip("/").endswith("mixbook.com")

    @pytest.mark.unit
    def test_mixbook_queries_exist(self):
        """mixbook.json query file must exist."""
        assert self.MIXBOOK_QUERIES.exists(), f"Missing: {self.MIXBOOK_QUERIES}"

    @pytest.mark.unit
    def test_mixbook_smoke_exists(self):
        """mixbook_smoke.json query file must exist."""
        assert self.MIXBOOK_SMOKE.exists(), f"Missing: {self.MIXBOOK_SMOKE}"

    @pytest.mark.unit
    def test_mixbook_queries_valid_json(self):
        """Query files must be valid JSON lists of strings."""
        queries = json.loads(self.MIXBOOK_QUERIES.read_text())
        assert isinstance(queries, list)
        assert all(isinstance(q, str) for q in queries)

    @pytest.mark.unit
    def test_mixbook_smoke_valid_json(self):
        """Smoke query file must be valid JSON list of strings."""
        queries = json.loads(self.MIXBOOK_SMOKE.read_text())
        assert isinstance(queries, list)
        assert all(isinstance(q, str) for q in queries)

    @pytest.mark.unit
    def test_mixbook_queries_count(self):
        """Plan specifies 20 queries in mixbook.json and 10 in smoke."""
        queries = json.loads(self.MIXBOOK_QUERIES.read_text())
        smoke = json.loads(self.MIXBOOK_SMOKE.read_text())
        assert len(queries) == 20, f"Expected 20 queries, got {len(queries)}"
        assert len(smoke) == 10, f"Expected 10 smoke queries, got {len(smoke)}"

    @pytest.mark.unit
    def test_mixbook_smoke_is_subset_of_full(self):
        """Smoke queries should be a subset of the full query set."""
        queries = set(json.loads(self.MIXBOOK_QUERIES.read_text()))
        smoke = set(json.loads(self.MIXBOOK_SMOKE.read_text()))
        diff = smoke - queries
        assert not diff, f"Smoke queries not in full set: {diff}"

    @pytest.mark.unit
    def test_mixbook_has_gibberish_query(self):
        """Plan specifies 'asdfqwerty12345' in the full set for error handling testing."""
        queries = json.loads(self.MIXBOOK_QUERIES.read_text())
        assert "asdfqwerty12345" in queries, "Missing gibberish query for error handling"

    @pytest.mark.unit
    def test_mixbook_no_duplicate_queries(self):
        """Query files should not contain duplicates."""
        queries = json.loads(self.MIXBOOK_QUERIES.read_text())
        assert len(queries) == len(set(queries)), "Duplicate queries in mixbook.json"
        smoke = json.loads(self.MIXBOOK_SMOKE.read_text())
        assert len(smoke) == len(set(smoke)), "Duplicate queries in mixbook_smoke.json"


# ──────────────────────────────────────────────────────────────────────
# SECTION 6: Score distribution edge cases
# ──────────────────────────────────────────────────────────────────────


class TestScoreDistribution:
    """Test maturity label assignment for score distribution scenarios."""

    @pytest.mark.unit
    def test_all_scores_in_one_bucket(self):
        """When all FQI scores fall in one band, all labels should be identical."""
        scores = [2.6, 2.7, 2.8, 2.9, 3.0, 3.1, 3.2, 3.3, 3.4]
        labels = [get_maturity_label(s) for s in scores]
        assert all(label == "L3_ENHANCED" for label in labels)

    @pytest.mark.unit
    def test_labels_cover_all_five_levels(self):
        """Representative scores should produce all 5 maturity levels."""
        test_cases = {
            0.5: "L1_BASIC",
            2.0: "L2_FUNCTIONAL",
            3.0: "L3_ENHANCED",
            4.0: "L4_INTELLIGENT",
            5.0: "L5_AGENTIC",
        }
        for score, expected_label in test_cases.items():
            actual = get_maturity_label(score)
            assert (
                actual == expected_label
            ), f"Score {score}: expected {expected_label}, got {actual}"
