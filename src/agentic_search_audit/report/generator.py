"""Report generation for audit results."""

import html
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TextIO

from ..analysis.benchmarks import Industry
from ..analysis.maturity import MaturityEvaluator, MaturityReport
from ..analysis.uplift_planner import FindingsAnalyzer, FindingsReport, Severity
from ..core.types import AuditConfig, AuditRecord, ExpertInsight, get_fqi_band

logger = logging.getLogger(__name__)

# Check for optional PDF support
try:
    import weasyprint  # type: ignore[import-not-found]

    HAS_WEASYPRINT = True
except ImportError:
    HAS_WEASYPRINT = False
    weasyprint = None  # type: ignore[assignment]


def escape_html(text: str | None) -> str:
    """Escape HTML special characters to prevent XSS.

    Args:
        text: Text to escape (can be None)

    Returns:
        HTML-escaped text, or empty string if None
    """
    if text is None:
        return ""
    return html.escape(str(text), quote=True)


class ReportGenerator:
    """Generates human-readable reports from audit results."""

    def __init__(self, config: AuditConfig, run_dir: Path, industry: Industry = Industry.GENERAL):
        """Initialize report generator.

        Args:
            config: Audit configuration
            run_dir: Run output directory
            industry: Industry for benchmark comparison
        """
        self.config = config
        self.run_dir = run_dir
        self.industry = industry
        self.maturity_evaluator = MaturityEvaluator()
        self.findings_analyzer = FindingsAnalyzer()

    def generate_reports(
        self,
        records: list[AuditRecord],
        include_maturity: bool = True,
        include_findings: bool = True,
        generate_pdf: bool = False,
        expert_insights: list[ExpertInsight] | None = None,
    ) -> None:
        """Generate all configured report formats.

        Args:
            records: List of audit records
            include_maturity: Include maturity assessment section
            include_findings: Include findings section
            generate_pdf: Generate PDF version of the HTML report
            expert_insights: Optional list of expert commentary insights
        """
        logger.info(f"Generating reports in {self.run_dir}")

        # Generate maturity and findings analysis
        maturity_report = None
        findings_report = None

        if include_maturity and records:
            maturity_report = self.maturity_evaluator.evaluate(records)
            logger.info(
                f"Maturity assessment: Level {maturity_report.overall_level.name} "
                f"(score: {maturity_report.overall_score:.2f})"
            )

        if include_findings and records:
            findings_report = self.findings_analyzer.analyze(records)
            logger.info(
                f"Findings: {len(findings_report.findings)} issues identified "
                f"across {findings_report.total_queries_analyzed} queries"
            )

        insights = expert_insights or []

        if "md" in self.config.report.formats:
            self._generate_markdown(records, maturity_report, findings_report, insights)

        if "html" in self.config.report.formats:
            self._generate_html(records, maturity_report, findings_report, insights)

        if "json" in self.config.report.formats:
            self._generate_json(records, maturity_report, findings_report, insights)

        # Generate PDF if requested
        if generate_pdf:
            self._generate_pdf()

        # Export findings to CSV if available
        if findings_report and findings_report.findings:
            csv_path = self.run_dir / "findings.csv"
            csv_content = self.findings_analyzer.export_to_csv(findings_report)
            csv_path.write_text(csv_content, encoding="utf-8")
            logger.info(f"Exported findings to {csv_path}")

        logger.info("Reports generated successfully")

    def _generate_markdown(
        self,
        records: list[AuditRecord],
        maturity_report: MaturityReport | None = None,
        findings_report: FindingsReport | None = None,
        expert_insights: list[ExpertInsight] | None = None,
    ) -> None:
        """Generate Markdown report.

        Args:
            records: Audit records
            maturity_report: Maturity assessment report
            findings_report: Findings analysis report
            expert_insights: Optional expert commentary insights
        """
        report_path = self.run_dir / "report.md"
        logger.info(f"Generating Markdown report: {report_path}")

        with open(report_path, "w", encoding="utf-8") as f:
            # Header
            f.write("# Search Quality Audit Report\n\n")
            f.write(f"**Site:** {self.config.site.url}\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Total Queries:** {len(records)}\n\n")

            # Executive Summary (if maturity report available)
            if maturity_report:
                f.write("## Executive Summary\n\n")
                f.write(f"{maturity_report.executive_summary}\n\n")

            # Summary statistics
            if records:
                avg_fqi = sum(r.judge.fqi for r in records) / len(records)
                avg_qu = sum(r.judge.query_understanding.score for r in records) / len(records)
                avg_rr = sum(r.judge.results_relevance.score for r in records) / len(records)
                avg_rp = sum(r.judge.result_presentation.score for r in records) / len(records)
                avg_af = sum(r.judge.advanced_features.score for r in records) / len(records)
                avg_eh = sum(r.judge.error_handling.score for r in records) / len(records)

                f.write("## Summary\n\n")
                f.write("| Metric | Average Score |\n")
                f.write("|--------|---------------|\n")
                f.write(f"| FQI | {avg_fqi:.2f} |\n")
                f.write(f"| QU | {avg_qu:.2f} |\n")
                f.write(f"| RR | {avg_rr:.2f} |\n")
                f.write(f"| RP | {avg_rp:.2f} |\n")
                f.write(f"| AF | {avg_af:.2f} |\n")
                f.write(f"| EH | {avg_eh:.2f} |\n\n")

            # Maturity Assessment Section
            if maturity_report:
                self._write_markdown_maturity_section(f, maturity_report)

            # Findings Section
            if findings_report:
                self._write_markdown_findings_section(f, findings_report)

            # Expert Insights Section
            if expert_insights:
                self._write_markdown_expert_section(f, expert_insights)

            # Score distribution
            f.write("## Score Distribution\n\n")
            score_ranges = {
                "Broken (0-1.5)": 0,
                "Critical (1.5-2.5)": 0,
                "Weak (2.5-3.5)": 0,
                "Good (3.5-4.5)": 0,
                "Excellent (4.5-5)": 0,
            }
            for record in records:
                score = record.judge.fqi
                if score >= 4.5:
                    score_ranges["Excellent (4.5-5)"] += 1
                elif score >= 3.5:
                    score_ranges["Good (3.5-4.5)"] += 1
                elif score >= 2.5:
                    score_ranges["Weak (2.5-3.5)"] += 1
                elif score >= 1.5:
                    score_ranges["Critical (1.5-2.5)"] += 1
                else:
                    score_ranges["Broken (0-1.5)"] += 1

            for range_label, count in score_ranges.items():
                f.write(f"- {range_label}: {count} queries\n")
            f.write("\n")

            # Per-query details
            f.write("## Query Details\n\n")

            for i, record in enumerate(records, 1):
                f.write(f"### {i}. {record.query.text}\n\n")

                # FQI score with band
                band = get_fqi_band(record.judge.fqi)
                f.write(f"**FQI:** {record.judge.fqi:.2f} ({band})\n\n")

                # Dimension breakdown with diagnosis
                f.write("**Dimension Scores:**\n")
                f.write(
                    f"- Query Understanding: {record.judge.query_understanding.score:.2f}"
                    f" - {record.judge.query_understanding.diagnosis}\n"
                )
                f.write(
                    f"- Results Relevance: {record.judge.results_relevance.score:.2f}"
                    f" - {record.judge.results_relevance.diagnosis}\n"
                )
                f.write(
                    f"- Result Presentation: {record.judge.result_presentation.score:.2f}"
                    f" - {record.judge.result_presentation.diagnosis}\n"
                )
                f.write(
                    f"- Advanced Features: {record.judge.advanced_features.score:.2f}"
                    f" - {record.judge.advanced_features.diagnosis}\n"
                )
                f.write(
                    f"- Error Handling: {record.judge.error_handling.score:.2f}"
                    f" - {record.judge.error_handling.diagnosis}\n\n"
                )

                # Executive Summary
                if record.judge.executive_summary:
                    f.write(f"**Executive Summary:** {record.judge.executive_summary}\n\n")

                # Rationale
                f.write(f"**Rationale:** {record.judge.rationale}\n\n")

                # Issues
                if record.judge.issues:
                    f.write("**Issues:**\n")
                    for issue in record.judge.issues:
                        f.write(f"- {issue}\n")
                    f.write("\n")

                # Improvements
                if record.judge.improvements:
                    f.write("**Suggested Improvements:**\n")
                    for improvement in record.judge.improvements:
                        f.write(f"- {improvement}\n")
                    f.write("\n")

                # Top results
                if record.items:
                    f.write(f"**Top {len(record.items)} Results:**\n\n")
                    f.write("| Rank | Title | Price | URL |\n")
                    f.write("|------|-------|-------|-----|\n")
                    for item in record.items[:10]:
                        title = (item.title or "N/A")[:50]
                        price = item.price or "N/A"
                        url = (item.url or "N/A")[:60]
                        f.write(f"| {item.rank} | {title} | {price} | {url} |\n")
                else:
                    f.write("**Results:** No results found for this query.\n")
                f.write("\n")

                # Screenshot
                screenshot_rel = Path(record.page.screenshot_path).relative_to(self.run_dir)
                f.write(f"**Screenshot:** [{screenshot_rel}]({screenshot_rel})\n\n")

                # PDP Analysis section (if any items have PDP data)
                pdp_items = [
                    item for item in record.items if item.attributes.get("pdp_analyzed") == "true"
                ]
                if pdp_items:
                    f.write("**PDP Analysis:**\n\n")
                    f.write(
                        "| Rank | PDP Title | PDP Price | Search Price"
                        " | Match | Availability | Rating |\n"
                    )
                    f.write(
                        "|------|-----------|-----------|"
                        "--------------|-------|--------------|--------|\n"
                    )
                    for item in pdp_items:
                        attrs = item.attributes
                        pdp_title = (attrs.get("pdp_title", "N/A") or "N/A")[:40]
                        pdp_price = attrs.get("pdp_price", "N/A") or "N/A"
                        search_price = item.price or "N/A"
                        # Simple price match check
                        price_match = "Yes" if pdp_price == search_price else "No"
                        availability = attrs.get("pdp_availability", "N/A") or "N/A"
                        rating = attrs.get("pdp_rating", "N/A") or "N/A"
                        f.write(
                            f"| {item.rank} | {pdp_title} | {pdp_price}"
                            f" | {search_price} | {price_match}"
                            f" | {availability} | {rating} |\n"
                        )
                    f.write("\n")

                f.write("---\n\n")

        logger.info(f"Markdown report saved to {report_path}")

    def _write_markdown_maturity_section(
        self, f: "TextIO", maturity_report: MaturityReport
    ) -> None:
        """Write maturity assessment section to markdown file."""
        f.write("## Maturity Assessment\n\n")
        f.write(
            f"**Overall Maturity Level:** {maturity_report.overall_level.name} "
            f"(Level {maturity_report.overall_level.value}/5)\n\n"
        )
        f.write(f"**Overall Score:** {maturity_report.overall_score:.2f}/5.00\n\n")

        # Dimension scores table
        if maturity_report.dimensions:
            f.write("### Dimension Scores\n\n")
            f.write("| Dimension | Score | Level |\n")
            f.write("|-----------|-------|-------|\n")
            for dim_name, dim_score in maturity_report.dimensions.items():
                f.write(f"| {dim_score.name} | {dim_score.score:.2f} | {dim_score.level.name} |\n")
            f.write("\n")

        # Strengths
        if maturity_report.strengths:
            f.write("### Strengths\n\n")
            for strength in maturity_report.strengths:
                f.write(f"- {strength}\n")
            f.write("\n")

        # Weaknesses
        if maturity_report.weaknesses:
            f.write("### Areas for Improvement\n\n")
            for weakness in maturity_report.weaknesses:
                f.write(f"- {weakness}\n")
            f.write("\n")

    def _write_markdown_findings_section(
        self, f: "TextIO", findings_report: FindingsReport
    ) -> None:
        """Write findings section to markdown file."""
        f.write("## Search Quality Issues\n\n")
        f.write(f"{findings_report.summary}\n\n")

        # Scope & Limitations
        f.write("### Scope & Limitations\n\n")
        f.write(f"> {findings_report.scope_limitations}\n\n")

        # Group findings by severity
        for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
            group = [f for f in findings_report.findings if f.severity == severity]
            if not group:
                continue

            f.write(f"### {severity.value.title()} Severity\n\n")
            for finding in group:
                f.write(
                    f"**{finding.observation}** "
                    f"({finding.affected_queries}/{finding.total_queries} queries)\n"
                )
                f.write(
                    f"- Dimension: {finding.affected_dimension} "
                    f"(avg score: {finding.avg_dimension_score:.1f})\n"
                )
                if finding.example_queries:
                    examples = ", ".join(f'"{q}"' for q in finding.example_queries)
                    f.write(f"- Examples: {examples}\n")
                if finding.suggestion:
                    f.write(f"- Suggestion: {finding.suggestion}\n")
                f.write("\n")

    def _write_markdown_expert_section(
        self, f: "TextIO", expert_insights: list[ExpertInsight]
    ) -> None:
        """Write expert insights section to markdown file."""
        f.write("## Expert Insights\n\n")

        for insight in expert_insights:
            risk_icon = {
                "low": "LOW",
                "medium": "MEDIUM",
                "high": "HIGH",
                "critical": "CRITICAL",
            }.get(insight.risk_level, "N/A")

            f.write(f"### {insight.expert_name}\n\n")
            f.write(f"**{insight.headline}** | Risk: {risk_icon}\n\n")
            f.write(f"{insight.commentary}\n\n")

            if insight.key_observations:
                f.write("**Key Observations:**\n")
                for obs in insight.key_observations:
                    f.write(f"- {obs}\n")
                f.write("\n")

            if insight.recommendations:
                f.write("**Recommendations:**\n")
                for rec in insight.recommendations:
                    f.write(f"- {rec}\n")
                f.write("\n")

            f.write("---\n\n")

    def _generate_html(
        self,
        records: list[AuditRecord],
        maturity_report: MaturityReport | None = None,
        findings_report: FindingsReport | None = None,
        expert_insights: list[ExpertInsight] | None = None,
    ) -> None:
        """Generate HTML report.

        Args:
            records: Audit records
            maturity_report: Maturity assessment report
            findings_report: Findings analysis report
            expert_insights: Optional expert commentary insights
        """
        report_path = self.run_dir / "report.html"
        logger.info(f"Generating HTML report: {report_path}")

        # Calculate summary stats
        avg_fqi = sum(r.judge.fqi for r in records) / len(records) if records else 0
        avg_qu = (
            sum(r.judge.query_understanding.score for r in records) / len(records) if records else 0
        )
        avg_rr = (
            sum(r.judge.results_relevance.score for r in records) / len(records) if records else 0
        )
        avg_rp = (
            sum(r.judge.result_presentation.score for r in records) / len(records) if records else 0
        )
        avg_af = (
            sum(r.judge.advanced_features.score for r in records) / len(records) if records else 0
        )
        avg_eh = sum(r.judge.error_handling.score for r in records) / len(records) if records else 0

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Search Quality Audit Report</title>
    <!-- Chart.js CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        /* CSS Variables for theming */
        :root {
            --bg-primary: #f5f5f5;
            --bg-card: white;
            --text-primary: #333;
            --text-secondary: #666;
            --border-color: #eee;
            --shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        /* Dark mode */
        [data-theme="dark"] {
            --bg-primary: #1a1a2e;
            --bg-card: #16213e;
            --text-primary: #eee;
            --text-secondary: #aaa;
            --border-color: #333;
            --shadow: 0 2px 4px rgba(0,0,0,0.3);
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: var(--bg-primary);
            color: var(--text-primary);
            transition: background 0.3s, color 0.3s;
        }

        /* Theme toggle button */
        .theme-toggle {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 10px 15px;
            border: none;
            border-radius: 20px;
            background: var(--bg-card);
            color: var(--text-primary);
            cursor: pointer;
            box-shadow: var(--shadow);
            z-index: 1000;
            font-size: 14px;
        }
        .theme-toggle:hover {
            opacity: 0.8;
        }

        /* Filter controls */
        .filter-controls {
            background: var(--bg-card);
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            align-items: center;
        }
        .filter-controls label {
            font-weight: 500;
        }
        .filter-controls select, .filter-controls input {
            padding: 8px 12px;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            background: var(--bg-primary);
            color: var(--text-primary);
        }

        .header {
            background: var(--bg-card);
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
        }
        .summary {
            background: var(--bg-card);
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
        }
        .summary table {
            width: 100%;
            border-collapse: collapse;
        }
        .summary th, .summary td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }

        /* Charts container */
        .charts-section {
            background: var(--bg-card);
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
        }
        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 30px;
        }
        .chart-container {
            position: relative;
            height: 300px;
        }

        .query-card {
            background: var(--bg-card);
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
        }
        .query-title {
            font-size: 1.5em;
            margin-bottom: 15px;
            color: var(--text-primary);
        }

        /* Collapsible sections */
        details.query-details {
            background: var(--bg-card);
            border-radius: 8px;
            margin-bottom: 15px;
            box-shadow: var(--shadow);
            overflow: hidden;
        }
        details.query-details summary {
            padding: 20px 25px;
            cursor: pointer;
            font-weight: 600;
            font-size: 1.1em;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-card);
        }
        details.query-details summary:hover {
            background: var(--bg-primary);
        }
        details.query-details summary::after {
            content: '+';
            font-size: 1.5em;
            font-weight: 300;
        }
        details.query-details[open] summary::after {
            content: '\u2212';
        }
        details.query-details .query-content {
            padding: 0 25px 25px 25px;
        }
        .summary-scores {
            display: flex;
            gap: 15px;
            font-size: 0.9em;
        }
        .summary-scores .score-badge {
            padding: 4px 10px;
            border-radius: 12px;
            background: #e9ecef;
        }
        [data-theme="dark"] .summary-scores .score-badge {
            background: #333;
        }

        .score-excellent { border-left-color: #28a745; }
        .score-good { border-left-color: #17a2b8; }
        .score-fair { border-left-color: #ffc107; }
        .score-poor { border-left-color: #dc3545; }

        /* FQI badge */
        .fqi-badge {
            display: inline-block;
            padding: 6px 14px;
            border-radius: 16px;
            font-weight: bold;
            font-size: 0.85em;
            margin-left: 8px;
        }
        .fqi-excellent { background: #d4edda; color: #155724; }
        .fqi-good { background: #cce5ff; color: #004085; }
        .fqi-weak { background: #fff3cd; color: #856404; }
        .fqi-critical { background: #f8d7da; color: #721c24; }
        .fqi-broken { background: #dc3545; color: white; }

        /* Verdict Bar */
        .verdict-bar {
            display: flex;
            align-items: center;
            gap: 20px;
            padding: 12px 15px;
            background: var(--bg-primary);
            border-radius: 6px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        .verdict-fqi {
            display: flex;
            align-items: center;
            gap: 8px;
            min-width: 140px;
        }
        .verdict-score {
            font-size: 1.8em;
            font-weight: bold;
        }
        .dimension-bars {
            display: flex;
            gap: 12px;
            flex: 1;
            flex-wrap: wrap;
        }
        .dim-bar {
            display: flex;
            align-items: center;
            gap: 4px;
            min-width: 100px;
        }
        .dim-label {
            font-size: 0.75em;
            font-weight: 600;
            color: var(--text-secondary);
            width: 22px;
        }
        .dim-track {
            width: 60px;
            height: 8px;
            background: var(--border-color);
            border-radius: 4px;
            overflow: hidden;
        }
        .dim-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s;
        }
        .dim-fill.fill-excellent { background: #28a745; }
        .dim-fill.fill-good { background: #17a2b8; }
        .dim-fill.fill-fair { background: #ffc107; }
        .dim-fill.fill-poor { background: #dc3545; }
        .dim-score {
            font-size: 0.8em;
            font-weight: 600;
            min-width: 24px;
        }
        .dim-warn {
            background: rgba(220, 53, 69, 0.08);
            border-radius: 4px;
            padding: 2px 6px;
        }
        .dim-warn .dim-score { color: #dc3545; font-weight: 700; }

        /* Analysis section */
        .analysis-section {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid var(--border-color);
        }
        .analysis-section h4 {
            margin: 0 0 10px 0;
            color: var(--text-secondary);
        }

        /* Collapsible screenshot */
        .screenshot-toggle summary {
            cursor: pointer;
            font-weight: 600;
            color: var(--text-secondary);
            padding: 8px 0;
        }

        /* Summary warning badge */
        .summary-warn {
            color: #dc3545;
            font-weight: 600;
            font-size: 0.85em;
        }

        /* Sortable tables */
        .results-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        .results-table th, .results-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }
        .results-table th {
            background: var(--bg-primary);
            font-weight: 600;
            cursor: pointer;
            user-select: none;
        }
        .results-table th:hover {
            background: var(--border-color);
        }
        .results-table th.sort-asc::after { content: ' \u2191'; }
        .results-table th.sort-desc::after { content: ' \u2193'; }

        .no-results-message {
            padding: 20px;
            background: var(--bg-primary);
            border: 1px dashed var(--border-color);
            border-radius: 6px;
            text-align: center;
            color: var(--text-secondary);
            margin: 20px 0;
        }

        .screenshot {
            max-width: 100%;
            border-radius: 6px;
            margin: 20px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .issues, .improvements {
            margin: 15px 0;
        }
        .issues ul, .improvements ul {
            margin: 10px 0;
            padding-left: 20px;
        }
        .issues li {
            color: #dc3545;
            margin: 5px 0;
        }
        .improvements li {
            color: #28a745;
            margin: 5px 0;
        }
        /* Maturity Assessment Styles */
        .maturity-section {
            background: var(--bg-card);
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
        }
        .maturity-badge {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            margin: 10px 0;
        }
        .maturity-l1 { background: #f8d7da; color: #721c24; }
        .maturity-l2 { background: #fff3cd; color: #856404; }
        .maturity-l3 { background: #d4edda; color: #155724; }
        .maturity-l4 { background: #cce5ff; color: #004085; }
        .maturity-l5 { background: #d1ecf1; color: #0c5460; }
        .dimension-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .dimension-item {
            background: var(--bg-primary);
            padding: 15px;
            border-radius: 6px;
            text-align: center;
        }
        .dimension-name {
            font-size: 0.9em;
            color: var(--text-secondary);
            margin-bottom: 5px;
        }
        .dimension-score {
            font-size: 1.5em;
            font-weight: bold;
        }
        /* Findings Section Styles */
        .findings-section {
            background: var(--bg-card);
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
        }
        .findings-summary {
            background: var(--bg-primary);
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #667eea;
        }
        .findings-number {
            font-size: 2.5em;
            font-weight: bold;
            color: var(--text-primary);
        }
        .scope-limitations {
            background: var(--bg-primary);
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            border-left: 4px solid #aaa;
            font-size: 0.9em;
            color: var(--text-secondary);
        }
        .scope-limitations h4 {
            margin: 0 0 8px 0;
            color: var(--text-secondary);
        }
        .finding-card {
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 10px;
            background: var(--bg-card);
        }
        .finding-card.severity-critical {
            border-left: 4px solid #dc3545;
        }
        .finding-card.severity-high {
            border-left: 4px solid #fd7e14;
        }
        .finding-card.severity-medium {
            border-left: 4px solid #ffc107;
        }
        .finding-card.severity-low {
            border-left: 4px solid #28a745;
        }
        .severity-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75em;
            font-weight: bold;
            text-transform: uppercase;
        }
        .severity-critical { background: #dc3545; color: white; }
        .severity-high { background: #fd7e14; color: white; }
        .severity-medium { background: #ffc107; color: #333; }
        .severity-low { background: #28a745; color: white; }

        /* Mobile Responsive Styles */
        @media (max-width: 768px) {
            body {
                padding: 10px;
            }
            .header, .summary, .query-card, .maturity-section, .findings-section, .charts-section {
                padding: 15px;
            }
            .theme-toggle {
                top: 10px;
                right: 10px;
                padding: 8px 12px;
                font-size: 12px;
            }
            .filter-controls {
                flex-direction: column;
                gap: 10px;
            }
            .charts-grid {
                grid-template-columns: 1fr;
            }
            .chart-container {
                height: 250px;
            }
            .verdict-bar {
                gap: 12px;
                padding: 10px 12px;
            }
            .dimension-bars {
                gap: 8px;
            }
            .dimension-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            .results-table {
                display: block;
                overflow-x: auto;
                white-space: nowrap;
            }
            .summary-scores {
                flex-wrap: wrap;
                gap: 8px;
            }
            details.query-details summary {
                padding: 15px;
                font-size: 1em;
            }
            details.query-details .query-content {
                padding: 0 15px 15px 15px;
            }
            .findings-number {
                font-size: 2em;
            }
            h1 {
                font-size: 1.5em;
            }
            h2 {
                font-size: 1.3em;
            }
            h3 {
                font-size: 1.1em;
            }
        }

        @media (max-width: 480px) {
            .dimension-bars {
                flex-direction: column;
            }
            .dimension-grid {
                grid-template-columns: 1fr;
            }
        }

        /* Print styles */
        @media print {
            .theme-toggle, .filter-controls {
                display: none;
            }
            body {
                background: white;
                color: black;
            }
            .query-card, .maturity-section, .findings-section {
                break-inside: avoid;
            }
        }
    </style>
</head>
<body>
    <button class="theme-toggle" onclick="toggleTheme()">Dark Mode</button>
""")

            # Header
            f.write(f"""
    <div class="header">
        <h1>Search Quality Audit Report</h1>
        <p><strong>Site:</strong> {escape_html(str(self.config.site.url))}</p>
        <p><strong>Date:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        <p><strong>Total Queries:</strong> {len(records)}</p>
    </div>
""")
            # FQI Hero Score
            if records:
                fqi_band = get_fqi_band(avg_fqi)
                fqi_band_class = self._get_fqi_band_class(fqi_band)
                f.write(f"""
    <div class="summary" style="text-align: center; padding: 30px;">
        <div style="font-size: 3.5em; font-weight: bold; margin-bottom: 5px;">{avg_fqi:.2f}</div>
        <div style="font-size: 1.2em; margin-bottom: 10px;">Overall Findability Quality Index</div>
        <span class="fqi-badge {fqi_band_class}" style="font-size: 1.1em; padding: 8px 20px;">{escape_html(fqi_band)}</span>
        <div style="margin-top: 15px; color: var(--text-secondary); font-size: 0.9em;">
            Based on {len(records)} queries across 5 quality dimensions
        </div>
    </div>
""")

            # Filter controls (only show if there are records)
            if records:
                f.write("""
    <div class="filter-controls">
        <label>Sort:</label>
        <select id="querySort" onchange="sortQueries()">
            <option value="original">Original Order</option>
            <option value="alpha-asc">A &rarr; Z</option>
            <option value="alpha-desc">Z &rarr; A</option>
            <option value="score-asc">Score &uarr;</option>
            <option value="score-desc">Score &darr;</option>
        </select>
        <label>Filter by FQI band:</label>
        <select id="scoreFilter" onchange="filterQueries()">
            <option value="all">All Bands</option>
            <option value="0-1.5">Broken (0-1.5)</option>
            <option value="1.5-2.5">Critical (1.5-2.5)</option>
            <option value="2.5-3.5">Weak (2.5-3.5)</option>
            <option value="3.5-4.5">Good (3.5-4.5)</option>
            <option value="4.5-5">Excellent (4.5-5)</option>
        </select>
        <label>Search:</label>
        <input type="text" id="querySearch" placeholder="Search queries..." oninput="filterQueries()">
    </div>
""")

            # Summary
            f.write(f"""
    <div class="summary">
        <h2>Summary</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Average Score</th>
            </tr>
            <tr>
                <td>FQI</td>
                <td>{avg_fqi:.2f}</td>
            </tr>
            <tr>
                <td>QU</td>
                <td>{avg_qu:.2f}</td>
            </tr>
            <tr>
                <td>RR</td>
                <td>{avg_rr:.2f}</td>
            </tr>
            <tr>
                <td>RP</td>
                <td>{avg_rp:.2f}</td>
            </tr>
            <tr>
                <td>AF</td>
                <td>{avg_af:.2f}</td>
            </tr>
            <tr>
                <td>EH</td>
                <td>{avg_eh:.2f}</td>
            </tr>
        </table>
    </div>
""")

            # Charts section
            if records:
                self._write_html_score_charts(f, records, avg_qu, avg_rr, avg_rp, avg_af, avg_eh)

            # Maturity Assessment Section
            if maturity_report:
                self._write_html_maturity_section(f, maturity_report)

            # Findings Section
            if findings_report:
                self._write_html_findings_section(f, findings_report)

            # Expert Insights Section
            if expert_insights:
                self._write_html_expert_section(f, expert_insights)

            # Query details header
            if records:
                f.write("    <h2>Query Details</h2>\n")
                f.write('    <div id="queryContainer">\n')
            for i, record in enumerate(records):
                fqi_score = record.judge.fqi
                score_class = self._get_score_class(fqi_score)
                fqi_band = get_fqi_band(fqi_score)
                fqi_band_class = self._get_fqi_band_class(fqi_band)
                screenshot_rel = Path(record.page.screenshot_path).relative_to(self.run_dir)
                query_escaped = escape_html(record.query.text.lower())

                # Count weak dimensions for summary warning
                dim_scores = [
                    record.judge.query_understanding.score,
                    record.judge.results_relevance.score,
                    record.judge.result_presentation.score,
                    record.judge.advanced_features.score,
                    record.judge.error_handling.score,
                ]
                weak_count = sum(1 for s in dim_scores if s < 3.0)

                weak_badge = ""
                if weak_count > 0:
                    weak_badge = f'<span class="summary-warn">' f"\u26a0 {weak_count} weak</span>"

                f.write(f"""
    <details class="query-details" data-score="{fqi_score:.2f}" data-query="{query_escaped}" data-index="{i}">
        <summary>
            <span>{i + 1}. {escape_html(record.query.text)}</span>
            <span class="summary-scores">
                <span class="score-badge {score_class}">FQI: {fqi_score:.2f}</span>
                <span class="fqi-badge {fqi_band_class}">{escape_html(fqi_band)}</span>
                <span class="score-badge">QU: {record.judge.query_understanding.score:.1f}</span>
                <span class="score-badge">RR: {record.judge.results_relevance.score:.1f}</span>
                {weak_badge}
            </span>
        </summary>
        <div class="query-content">
""")

                # --- Verdict Bar ---
                dimensions = [
                    ("QU", record.judge.query_understanding),
                    ("RR", record.judge.results_relevance),
                    ("RP", record.judge.result_presentation),
                    ("AF", record.judge.advanced_features),
                    ("EH", record.judge.error_handling),
                ]

                f.write(f"""        <div class="verdict-bar">
            <div class="verdict-fqi">
                <span class="verdict-score {score_class}">{fqi_score:.2f}</span>
                <span class="fqi-badge {fqi_band_class}">{escape_html(fqi_band)}</span>
            </div>
            <div class="dimension-bars">
""")
                for dim_label, dim in dimensions:
                    dim_score = dim.score
                    fill_class = self._get_fill_class(dim_score)
                    warn_class = "dim-warn" if dim_score < 3.0 else ""
                    width_pct = dim_score / 5.0 * 100
                    diagnosis_escaped = escape_html(dim.diagnosis)
                    f.write(
                        f'                <div class="dim-bar {warn_class}"'
                        f' title="{diagnosis_escaped}">\n'
                        f'                    <span class="dim-label">{dim_label}</span>\n'
                        f'                    <div class="dim-track">\n'
                        f'                        <div class="dim-fill {fill_class}"'
                        f' style="width: {width_pct:.0f}%"></div>\n'
                        f"                    </div>\n"
                        f'                    <span class="dim-score">{dim_score:.1f}</span>\n'
                        f"                </div>\n"
                    )
                f.write("            </div>\n        </div>\n")

                # --- Results table (moved up, before analysis) ---
                if record.items:
                    f.write("""
        <h3>Top Results</h3>
        <table class="results-table">
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Title</th>
                    <th>Price</th>
                    <th>URL</th>
                </tr>
            </thead>
            <tbody>
""")

                    for item in record.items[:10]:
                        title = escape_html((item.title or "N/A")[:80])
                        price = escape_html(item.price or "N/A")
                        url = (item.url or "")[:80]
                        url_escaped = escape_html(url)
                        url_display = escape_html(url[:50]) + "..." if url else "N/A"
                        f.write(f"""
                <tr>
                    <td>{item.rank}</td>
                    <td>{title}</td>
                    <td>{price}</td>
                    <td><a href="{url_escaped}" target="_blank" rel="noopener noreferrer">{url_display}</a></td>
                </tr>
""")

                    f.write("""
            </tbody>
        </table>
""")
                else:
                    f.write("""
        <div class="no-results-message">
            <p>No results found for this query.</p>
        </div>
""")

                # --- Analysis section ---
                f.write('        <div class="analysis-section">\n')
                f.write("            <h4>Analysis</h4>\n")

                # Show executive_summary if available, otherwise rationale
                if record.judge.executive_summary:
                    f.write(f"            <p>{escape_html(record.judge.executive_summary)}</p>\n")
                else:
                    f.write(f"            <p>{escape_html(record.judge.rationale)}</p>\n")

                if record.judge.issues:
                    f.write('            <div class="issues">\n')
                    f.write("                <strong>Issues:</strong>\n")
                    f.write("                <ul>\n")
                    for issue in record.judge.issues:
                        f.write(f"                    <li>{escape_html(issue)}</li>\n")
                    f.write("                </ul>\n")
                    f.write("            </div>\n")

                if record.judge.improvements:
                    f.write('            <div class="improvements">\n')
                    f.write("                <strong>Suggested Improvements:</strong>\n")
                    f.write("                <ul>\n")
                    for improvement in record.judge.improvements:
                        f.write(f"                    <li>{escape_html(improvement)}</li>\n")
                    f.write("                </ul>\n")
                    f.write("            </div>\n")

                f.write("        </div>\n")

                # --- Screenshot in collapsible ---
                f.write(f"""
        <details class="screenshot-toggle">
            <summary>Screenshot</summary>
            <img src="{screenshot_rel}" alt="Screenshot" class="screenshot" loading="lazy">
        </details>
""")

                # PDP Analysis in HTML
                pdp_items = [
                    item for item in record.items if item.attributes.get("pdp_analyzed") == "true"
                ]
                if pdp_items:
                    f.write("""
        <details class="screenshot-toggle">
            <summary>PDP Analysis</summary>
            <table class="results-table">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>PDP Title</th>
                        <th>PDP Price</th>
                        <th>Search Price</th>
                        <th>Match</th>
                        <th>Availability</th>
                        <th>Rating</th>
                    </tr>
                </thead>
                <tbody>
""")
                    for item in pdp_items:
                        attrs = item.attributes
                        pdp_title = escape_html((attrs.get("pdp_title", "N/A") or "N/A")[:60])
                        pdp_price = escape_html(attrs.get("pdp_price", "N/A") or "N/A")
                        search_price = escape_html(item.price or "N/A")
                        price_match = "Yes" if attrs.get("pdp_price") == item.price else "No"
                        match_style = (
                            "color: #28a745;" if price_match == "Yes" else "color: #dc3545;"
                        )
                        availability = escape_html(attrs.get("pdp_availability", "N/A") or "N/A")
                        rating = escape_html(attrs.get("pdp_rating", "N/A") or "N/A")

                        f.write(f"""
                    <tr>
                        <td>{item.rank}</td>
                        <td>{pdp_title}</td>
                        <td>{pdp_price}</td>
                        <td>{search_price}</td>
                        <td style="{match_style}">{price_match}</td>
                        <td>{availability}</td>
                        <td>{rating}</td>
                    </tr>
""")

                    f.write("""
                </tbody>
            </table>
""")

                    # Show PDP screenshots
                    for item in pdp_items:
                        pdp_ss = item.attributes.get("pdp_screenshot_path", "")
                        if pdp_ss:
                            try:
                                pdp_ss_rel = Path(pdp_ss).relative_to(self.run_dir)
                                f.write(
                                    f"            <details><summary>"
                                    f"PDP Screenshot (Rank {item.rank})"
                                    f"</summary>"
                                    f'<img src="{pdp_ss_rel}"'
                                    f' alt="PDP Screenshot"'
                                    f' class="screenshot"'
                                    f' loading="lazy"></details>\n'
                                )
                            except ValueError:
                                pass

                    f.write("        </details>\n")

                f.write("""        </div>
    </details>
""")

            # Close query container
            if records:
                f.write("    </div>\n")

            # JavaScript for interactivity
            f.write(self._get_html_javascript(records))

            f.write("""
</body>
</html>
""")

        logger.info(f"HTML report saved to {report_path}")

    def _write_html_maturity_section(self, f: TextIO, maturity_report: MaturityReport) -> None:
        """Write maturity assessment section to HTML file."""
        level_class = f"maturity-l{maturity_report.overall_level.value}"

        f.write(f"""
    <div class="maturity-section">
        <h2>Maturity Assessment</h2>
        <p><span class="maturity-badge {level_class}">
            Level {maturity_report.overall_level.value}: {escape_html(maturity_report.overall_level.name)}
        </span></p>
        <p><strong>Overall Score:</strong> {maturity_report.overall_score:.2f}/5.00</p>
        <p>{escape_html(maturity_report.executive_summary)}</p>

        <h3>Dimension Scores</h3>
        <div class="dimension-grid">
""")

        for dim_name, dim_score in maturity_report.dimensions.items():
            score_class = self._get_score_class(dim_score.score)
            f.write(f"""
            <div class="dimension-item {score_class}">
                <div class="dimension-name">{escape_html(dim_score.name)}</div>
                <div class="dimension-score">{dim_score.score:.1f}</div>
                <div style="font-size: 0.8em; color: #666;">{escape_html(dim_score.level.name)}</div>
            </div>
""")

        f.write("        </div>\n")

        # Strengths and Weaknesses
        if maturity_report.strengths:
            f.write("        <h3>Strengths</h3>\n        <ul>\n")
            for strength in maturity_report.strengths:
                f.write(f"            <li style='color: #28a745;'>{escape_html(strength)}</li>\n")
            f.write("        </ul>\n")

        if maturity_report.weaknesses:
            f.write("        <h3>Areas for Improvement</h3>\n        <ul>\n")
            for weakness in maturity_report.weaknesses:
                f.write(f"            <li style='color: #dc3545;'>{escape_html(weakness)}</li>\n")
            f.write("        </ul>\n")

        f.write("    </div>\n")

    def _write_html_findings_section(self, f: TextIO, findings_report: FindingsReport) -> None:
        """Write findings section to HTML file."""
        total_findings = len(findings_report.findings)

        f.write(f"""
    <div class="findings-section">
        <h2>Search Quality Issues</h2>

        <div class="findings-summary">
            <div class="findings-number">{total_findings}</div>
            <div>Issues Identified Across {findings_report.total_queries_analyzed} Queries</div>
            <p style="margin-top: 15px; font-size: 0.9em;">{escape_html(findings_report.summary)}</p>
        </div>

        <div class="scope-limitations">
            <h4>Scope &amp; Limitations</h4>
            <p>{escape_html(findings_report.scope_limitations)}</p>
        </div>
""")

        # Group findings by severity
        for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
            group = [fi for fi in findings_report.findings if fi.severity == severity]
            if not group:
                continue

            severity_value = escape_html(severity.value)
            f.write(f"        <h3>{severity.value.title()} Severity</h3>\n")
            for finding in group:
                f.write(f"""
        <div class="finding-card severity-{severity_value}">
            <span class="severity-badge severity-{severity_value}">{severity_value}</span>
            <strong>{escape_html(finding.observation)}</strong>
            <span style="float: right;">
                {finding.affected_queries}/{finding.total_queries} queries
            </span>
            <p style="margin: 10px 0 5px 0; color: #666;">
                Dimension: {escape_html(finding.affected_dimension)}
                (avg score: {finding.avg_dimension_score:.1f})
            </p>
""")
                if finding.example_queries:
                    examples = ", ".join(
                        f"&ldquo;{escape_html(q)}&rdquo;" for q in finding.example_queries
                    )
                    f.write(
                        f'            <p style="font-size: 0.85em; color: #888;">'
                        f"Examples: {examples}</p>\n"
                    )
                if finding.suggestion:
                    f.write(
                        f'            <p style="font-size: 0.9em; font-style: italic;">'
                        f"{escape_html(finding.suggestion)}</p>\n"
                    )
                f.write("        </div>\n")

        f.write("    </div>\n")

    def _write_html_expert_section(self, f: TextIO, expert_insights: list[ExpertInsight]) -> None:
        """Write expert insights section to HTML file."""
        f.write("""
    <div class="expert-section" style="margin: 30px 0;">
        <h2>Expert Insights</h2>
        <p style="color: var(--text-secondary); margin-bottom: 20px;">
            Specialized analysis from domain experts
        </p>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px;">
""")

        risk_colors = {
            "low": "#28a745",
            "medium": "#ffc107",
            "high": "#fd7e14",
            "critical": "#dc3545",
        }

        for insight in expert_insights:
            risk_color = risk_colors.get(insight.risk_level, "#6c757d")
            expert_escaped = escape_html(insight.expert_name)
            headline_escaped = escape_html(insight.headline)
            commentary_escaped = escape_html(insight.commentary)

            f.write(f"""
            <div style="background: var(--card-bg, #fff); border: 1px solid var(--border-color, #dee2e6); border-radius: 8px; padding: 20px; border-left: 4px solid {risk_color};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h3 style="margin: 0; font-size: 1.1em;">{expert_escaped}</h3>
                    <span style="background: {risk_color}; color: white; padding: 2px 10px; border-radius: 12px; font-size: 0.8em; text-transform: uppercase;">
                        {escape_html(insight.risk_level)} risk
                    </span>
                </div>
                <p style="font-weight: 600; font-size: 1.05em; margin-bottom: 10px;">{headline_escaped}</p>
                <p style="color: var(--text-secondary); line-height: 1.6; white-space: pre-line;">{commentary_escaped}</p>
""")

            if insight.key_observations:
                f.write(
                    '                <div style="margin-top: 12px;">\n'
                    "                    <strong>Key Observations:</strong>\n"
                    '                    <ul style="margin: 5px 0; padding-left: 20px;">\n'
                )
                for obs in insight.key_observations:
                    f.write(f"                        <li>{escape_html(obs)}</li>\n")
                f.write("                    </ul>\n                </div>\n")

            if insight.recommendations:
                f.write(
                    '                <div style="margin-top: 12px;">\n'
                    "                    <strong>Recommendations:</strong>\n"
                    '                    <ul style="margin: 5px 0; padding-left: 20px;">\n'
                )
                for rec in insight.recommendations:
                    f.write(
                        f'                        <li style="color: var(--text-primary);">'
                        f"{escape_html(rec)}</li>\n"
                    )
                f.write("                    </ul>\n                </div>\n")

            f.write("            </div>\n")

        f.write("        </div>\n    </div>\n")

    def _generate_json(
        self,
        records: list[AuditRecord],
        maturity_report: MaturityReport | None = None,
        findings_report: FindingsReport | None = None,
        expert_insights: list[ExpertInsight] | None = None,
    ) -> None:
        """Generate JSON report.

        Args:
            records: Audit records
            maturity_report: Maturity assessment report
            findings_report: Findings analysis report
            expert_insights: Optional expert commentary insights
        """
        report_path = self.run_dir / "audit.json"
        logger.info(f"Generating JSON report: {report_path}")

        data = {
            "site": str(self.config.site.url),
            "timestamp": datetime.now().isoformat(),
            "total_queries": len(records),
            "records": [r.model_dump(mode="json") for r in records],
        }

        # Add maturity assessment
        if maturity_report:
            data["maturity"] = {
                "overall_level": maturity_report.overall_level.name,
                "overall_level_value": maturity_report.overall_level.value,
                "overall_score": maturity_report.overall_score,
                "executive_summary": maturity_report.executive_summary,
                "dimensions": {
                    name: {
                        "name": dim.name,
                        "score": dim.score,
                        "level": dim.level.name,
                        "findings": dim.findings,
                        "recommendations": dim.recommendations,
                    }
                    for name, dim in maturity_report.dimensions.items()
                },
                "strengths": maturity_report.strengths,
                "weaknesses": maturity_report.weaknesses,
                "priority_improvements": maturity_report.priority_improvements,
            }

        # Add findings
        if findings_report:
            data["findings"] = {
                "total_queries_analyzed": findings_report.total_queries_analyzed,
                "summary": findings_report.summary,
                "scope_limitations": findings_report.scope_limitations,
                "items": [
                    {
                        "id": finding.id,
                        "observation": finding.observation,
                        "affected_queries": finding.affected_queries,
                        "total_queries": finding.total_queries,
                        "affected_pct": round(finding.affected_pct, 1),
                        "severity": finding.severity.value,
                        "affected_dimension": finding.affected_dimension,
                        "avg_dimension_score": finding.avg_dimension_score,
                        "category": finding.category.value,
                        "example_queries": finding.example_queries,
                        "suggestion": finding.suggestion,
                    }
                    for finding in findings_report.findings
                ],
            }

        # Add expert insights
        if expert_insights:
            data["expert_insights"] = [i.model_dump() for i in expert_insights]

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(f"JSON report saved to {report_path}")

    def _get_score_class(self, score: float) -> str:
        """Get CSS class for score.

        Args:
            score: Score value (0-5)

        Returns:
            CSS class name
        """
        if score >= 4.5:
            return "score-excellent"
        elif score >= 3.5:
            return "score-good"
        elif score >= 2.5:
            return "score-fair"
        elif score >= 1.5:
            return "score-fair"
        else:
            return "score-poor"

    def _get_fqi_band(self, score: float) -> str:
        """Get FQI band label for a score.

        Args:
            score: FQI score value (0-5)

        Returns:
            Band label string
        """
        return get_fqi_band(score)

    def _get_fill_class(self, score: float) -> str:
        """Get CSS fill class for dimension bar.

        Args:
            score: Score value (0-5)

        Returns:
            CSS fill class name
        """
        if score >= 4.5:
            return "fill-excellent"
        elif score >= 3.5:
            return "fill-good"
        elif score >= 2.5:
            return "fill-fair"
        else:
            return "fill-poor"

    def _get_fqi_band_class(self, band: str) -> str:
        """Get CSS class for FQI band label.

        Args:
            band: FQI band label (Excellent, Good, Weak, Critical, Broken)

        Returns:
            CSS class name
        """
        band_lower = band.lower()
        if band_lower == "excellent":
            return "fqi-excellent"
        elif band_lower == "good":
            return "fqi-good"
        elif band_lower == "weak":
            return "fqi-weak"
        elif band_lower == "critical":
            return "fqi-critical"
        else:
            return "fqi-broken"

    def _write_html_score_charts(
        self,
        f: TextIO,
        records: list[AuditRecord],
        avg_qu: float,
        avg_rr: float,
        avg_rp: float,
        avg_af: float,
        avg_eh: float,
    ) -> None:
        """Write Chart.js score visualizations to HTML file.

        Args:
            f: File handle
            records: Audit records
            avg_qu: Average query understanding score
            avg_rr: Average results relevance score
            avg_rp: Average result presentation score
            avg_af: Average advanced features score
            avg_eh: Average error handling score
        """
        # Calculate FQI band distribution for histogram
        band_distribution = {
            "Broken": 0,
            "Critical": 0,
            "Weak": 0,
            "Good": 0,
            "Excellent": 0,
        }
        for record in records:
            band = get_fqi_band(record.judge.fqi)
            band_distribution[band] += 1

        f.write(f"""
    <div class="charts-section">
        <h2>Score Visualizations</h2>
        <div class="charts-grid">
            <div>
                <h3>FQI Dimension Scores (Radar)</h3>
                <div class="chart-container">
                    <canvas id="radarChart"></canvas>
                </div>
            </div>
            <div>
                <h3>FQI Band Distribution</h3>
                <div class="chart-container">
                    <canvas id="histogramChart"></canvas>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Radar Chart - FQI Dimension Scores
        const radarCtx = document.getElementById('radarChart').getContext('2d');
        new Chart(radarCtx, {{
            type: 'radar',
            data: {{
                labels: ['Query Understanding', 'Results Relevance', 'Result Presentation', 'Advanced Features', 'Error Handling'],
                datasets: [{{
                    label: 'Average Scores',
                    data: [{avg_qu:.2f}, {avg_rr:.2f}, {avg_rp:.2f}, {avg_af:.2f}, {avg_eh:.2f}],
                    backgroundColor: 'rgba(102, 126, 234, 0.2)',
                    borderColor: 'rgba(102, 126, 234, 1)',
                    borderWidth: 2,
                    pointBackgroundColor: 'rgba(102, 126, 234, 1)',
                    pointRadius: 4
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    r: {{
                        beginAtZero: true,
                        max: 5,
                        ticks: {{
                            stepSize: 1
                        }}
                    }}
                }},
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }}
            }}
        }});

        // Histogram Chart - FQI Band Distribution
        const histCtx = document.getElementById('histogramChart').getContext('2d');
        new Chart(histCtx, {{
            type: 'bar',
            data: {{
                labels: ['Broken', 'Critical', 'Weak', 'Good', 'Excellent'],
                datasets: [{{
                    label: 'Number of Queries',
                    data: [{band_distribution["Broken"]}, {band_distribution["Critical"]}, {band_distribution["Weak"]}, {band_distribution["Good"]}, {band_distribution["Excellent"]}],
                    backgroundColor: [
                        'rgba(220, 53, 69, 0.7)',
                        'rgba(255, 127, 14, 0.7)',
                        'rgba(255, 193, 7, 0.7)',
                        'rgba(23, 162, 184, 0.7)',
                        'rgba(40, 167, 69, 0.7)'
                    ],
                    borderColor: [
                        'rgba(220, 53, 69, 1)',
                        'rgba(255, 127, 14, 1)',
                        'rgba(255, 193, 7, 1)',
                        'rgba(23, 162, 184, 1)',
                        'rgba(40, 167, 69, 1)'
                    ],
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            stepSize: 1
                        }}
                    }}
                }},
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }}
            }}
        }});
    </script>
""")

    def _get_html_javascript(self, records: list[AuditRecord]) -> str:
        """Generate JavaScript for interactive features.

        Args:
            records: Audit records (used for data attributes)

        Returns:
            JavaScript code as string
        """
        return """
    <script>
        // Theme toggle
        function toggleTheme() {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', newTheme);

            const btn = document.querySelector('.theme-toggle');
            btn.textContent = newTheme === 'dark' ? 'Light Mode' : 'Dark Mode';

            // Save preference
            localStorage.setItem('theme', newTheme);
        }

        // Load saved theme
        document.addEventListener('DOMContentLoaded', function() {
            const savedTheme = localStorage.getItem('theme');
            if (savedTheme) {
                document.documentElement.setAttribute('data-theme', savedTheme);
                const btn = document.querySelector('.theme-toggle');
                btn.textContent = savedTheme === 'dark' ? 'Light Mode' : 'Dark Mode';
            }
        });

        // Sort queries
        function sortQueries() {
            var sortBy = document.getElementById('querySort').value;
            var container = document.getElementById('queryContainer');
            var queries = Array.from(container.querySelectorAll('.query-details'));

            queries.sort(function(a, b) {
                if (sortBy === 'alpha-asc') {
                    return a.getAttribute('data-query').localeCompare(b.getAttribute('data-query'));
                } else if (sortBy === 'alpha-desc') {
                    return b.getAttribute('data-query').localeCompare(a.getAttribute('data-query'));
                } else if (sortBy === 'score-asc') {
                    return parseFloat(a.getAttribute('data-score')) - parseFloat(b.getAttribute('data-score'));
                } else if (sortBy === 'score-desc') {
                    return parseFloat(b.getAttribute('data-score')) - parseFloat(a.getAttribute('data-score'));
                }
                // original order
                return parseInt(a.getAttribute('data-index')) - parseInt(b.getAttribute('data-index'));
            });

            queries.forEach(function(q) { container.appendChild(q); });
            filterQueries();
        }

        // Filter queries by FQI band and search text
        function filterQueries() {
            const scoreFilter = document.getElementById('scoreFilter').value;
            const searchText = document.getElementById('querySearch').value.toLowerCase();
            const queries = document.querySelectorAll('.query-details');

            queries.forEach(function(query) {
                const score = parseFloat(query.getAttribute('data-score'));
                const queryText = query.getAttribute('data-query');

                let showByScore = true;
                if (scoreFilter !== 'all') {
                    const [min, max] = scoreFilter.split('-').map(Number);
                    showByScore = score >= min && score < max;
                    // Include score == 5 in the top band
                    if (max === 5 && score === 5) showByScore = true;
                }

                let showBySearch = true;
                if (searchText) {
                    showBySearch = queryText.includes(searchText);
                }

                query.style.display = (showByScore && showBySearch) ? '' : 'none';
            });
        }

        // Sortable tables
        document.querySelectorAll('.results-table th').forEach(function(th) {
            th.addEventListener('click', function() {
                const table = th.closest('table');
                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));
                const index = Array.from(th.parentNode.children).indexOf(th);
                const isAsc = th.classList.contains('sort-asc');

                // Remove sort classes from all headers
                table.querySelectorAll('th').forEach(function(header) {
                    header.classList.remove('sort-asc', 'sort-desc');
                });

                // Sort rows
                rows.sort(function(a, b) {
                    const aVal = a.children[index].textContent;
                    const bVal = b.children[index].textContent;

                    // Try numeric sort first
                    const aNum = parseFloat(aVal);
                    const bNum = parseFloat(bVal);
                    if (!isNaN(aNum) && !isNaN(bNum)) {
                        return isAsc ? bNum - aNum : aNum - bNum;
                    }

                    // Fall back to string sort
                    return isAsc ? bVal.localeCompare(aVal) : aVal.localeCompare(bVal);
                });

                // Add sort class
                th.classList.add(isAsc ? 'sort-desc' : 'sort-asc');

                // Reappend sorted rows
                rows.forEach(function(row) {
                    tbody.appendChild(row);
                });
            });
        });
    </script>
"""

    def _generate_pdf(self) -> None:
        """Generate PDF version of the HTML report.

        Requires weasyprint to be installed (optional dependency).
        """
        if not HAS_WEASYPRINT:
            logger.warning(
                "PDF generation skipped: weasyprint not installed. "
                "Install with: pip install weasyprint"
            )
            return

        html_path = self.run_dir / "report.html"
        pdf_path = self.run_dir / "report.pdf"

        if not html_path.exists():
            logger.warning("Cannot generate PDF: HTML report not found")
            return

        try:
            import weasyprint  # type: ignore[import-not-found]

            logger.info(f"Generating PDF report: {pdf_path}")
            html_content = html_path.read_text(encoding="utf-8")

            # WeasyPrint needs base_url for relative paths (screenshots)
            html_doc = weasyprint.HTML(string=html_content, base_url=str(self.run_dir))
            html_doc.write_pdf(pdf_path)

            logger.info(f"PDF report saved to {pdf_path}")
        except Exception as e:
            logger.error(f"Failed to generate PDF: {e}")
