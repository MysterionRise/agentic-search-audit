"""Report generation for audit results."""

import json
import logging
from datetime import datetime
from pathlib import Path

from ..analysis.benchmarks import Industry
from ..analysis.maturity import MaturityEvaluator, MaturityReport
from ..analysis.uplift_planner import UpliftPlan, UpliftPlanner
from ..core.types import AuditConfig, AuditRecord

logger = logging.getLogger(__name__)


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
        self.uplift_planner = UpliftPlanner()

    def generate_reports(
        self,
        records: list[AuditRecord],
        include_maturity: bool = True,
        include_uplift: bool = True,
    ) -> None:
        """Generate all configured report formats.

        Args:
            records: List of audit records
            include_maturity: Include maturity assessment section
            include_uplift: Include uplift recommendations section
        """
        logger.info(f"Generating reports in {self.run_dir}")

        # Generate maturity and uplift analysis
        maturity_report = None
        uplift_plan = None

        if include_maturity and records:
            maturity_report = self.maturity_evaluator.evaluate(records)
            logger.info(
                f"Maturity assessment: Level {maturity_report.overall_level.name} "
                f"(score: {maturity_report.overall_score:.2f})"
            )

        if include_uplift and records:
            uplift_plan = self.uplift_planner.generate_plan(records, maturity_report)
            logger.info(
                f"Uplift plan: {len(uplift_plan.recommendations)} recommendations, "
                f"{uplift_plan.total_potential_uplift:.1f}% potential uplift"
            )

        if "md" in self.config.report.formats:
            self._generate_markdown(records, maturity_report, uplift_plan)

        if "html" in self.config.report.formats:
            self._generate_html(records, maturity_report, uplift_plan)

        if "json" in self.config.report.formats:
            self._generate_json(records, maturity_report, uplift_plan)

        # Export uplift plan to CSV if available
        if uplift_plan and uplift_plan.recommendations:
            csv_path = self.run_dir / "uplift_recommendations.csv"
            csv_content = self.uplift_planner.export_to_csv(uplift_plan)
            csv_path.write_text(csv_content, encoding="utf-8")
            logger.info(f"Exported uplift recommendations to {csv_path}")

        logger.info("Reports generated successfully")

    def _generate_markdown(
        self,
        records: list[AuditRecord],
        maturity_report: MaturityReport | None = None,
        uplift_plan: UpliftPlan | None = None,
    ) -> None:
        """Generate Markdown report.

        Args:
            records: Audit records
            maturity_report: Maturity assessment report
            uplift_plan: Uplift recommendations plan
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
                avg_overall = sum(r.judge.overall for r in records) / len(records)
                avg_relevance = sum(r.judge.relevance for r in records) / len(records)
                avg_diversity = sum(r.judge.diversity for r in records) / len(records)
                avg_quality = sum(r.judge.result_quality for r in records) / len(records)
                avg_nav = sum(r.judge.navigability for r in records) / len(records)

                f.write("## Summary\n\n")
                f.write("| Metric | Average Score |\n")
                f.write("|--------|---------------|\n")
                f.write(f"| Overall | {avg_overall:.2f} |\n")
                f.write(f"| Relevance | {avg_relevance:.2f} |\n")
                f.write(f"| Diversity | {avg_diversity:.2f} |\n")
                f.write(f"| Result Quality | {avg_quality:.2f} |\n")
                f.write(f"| Navigability | {avg_nav:.2f} |\n\n")

            # Maturity Assessment Section
            if maturity_report:
                self._write_markdown_maturity_section(f, maturity_report)

            # Uplift Recommendations Section
            if uplift_plan:
                self._write_markdown_uplift_section(f, uplift_plan)

            # Score distribution
            f.write("## Score Distribution\n\n")
            score_ranges = {"0-1": 0, "1-2": 0, "2-3": 0, "3-4": 0, "4-5": 0}
            for record in records:
                score = record.judge.overall
                if score < 1:
                    score_ranges["0-1"] += 1
                elif score < 2:
                    score_ranges["1-2"] += 1
                elif score < 3:
                    score_ranges["2-3"] += 1
                elif score < 4:
                    score_ranges["3-4"] += 1
                else:
                    score_ranges["4-5"] += 1

            for range_label, count in score_ranges.items():
                f.write(f"- {range_label}: {count} queries\n")
            f.write("\n")

            # Per-query details
            f.write("## Query Details\n\n")

            for i, record in enumerate(records, 1):
                f.write(f"### {i}. {record.query.text}\n\n")

                # Scores
                f.write("**Scores:**\n")
                f.write(f"- Overall: {record.judge.overall:.2f}\n")
                f.write(f"- Relevance: {record.judge.relevance:.2f}\n")
                f.write(f"- Diversity: {record.judge.diversity:.2f}\n")
                f.write(f"- Result Quality: {record.judge.result_quality:.2f}\n")
                f.write(f"- Navigability: {record.judge.navigability:.2f}\n\n")

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
                f.write(f"**Top {len(record.items)} Results:**\n\n")
                f.write("| Rank | Title | Price | URL |\n")
                f.write("|------|-------|-------|-----|\n")
                for item in record.items[:10]:
                    title = (item.title or "N/A")[:50]
                    price = item.price or "N/A"
                    url = (item.url or "N/A")[:60]
                    f.write(f"| {item.rank} | {title} | {price} | {url} |\n")
                f.write("\n")

                # Screenshot
                screenshot_rel = Path(record.page.screenshot_path).relative_to(self.run_dir)
                f.write(f"**Screenshot:** [{screenshot_rel}]({screenshot_rel})\n\n")

                f.write("---\n\n")

        logger.info(f"Markdown report saved to {report_path}")

    def _write_markdown_maturity_section(self, f, maturity_report: MaturityReport) -> None:
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

    def _write_markdown_uplift_section(self, f, uplift_plan: UpliftPlan) -> None:
        """Write uplift recommendations section to markdown file."""
        f.write("## Conversion Uplift Opportunities\n\n")
        f.write(f"{uplift_plan.summary}\n\n")
        f.write(f"**Total Potential Uplift:** {uplift_plan.total_potential_uplift:.1f}%\n\n")

        # Quick Wins
        if uplift_plan.quick_wins:
            f.write("### Quick Wins (0-4 weeks)\n\n")
            for rec in uplift_plan.quick_wins:
                f.write(f"**{rec.title}** (Expected uplift: {rec.expected_uplift_pct:.1f}%)\n")
                f.write(f"> {rec.description}\n\n")

        # Top Recommendations Table
        f.write("### All Recommendations\n\n")
        f.write("| Priority | Title | Effort | Expected Uplift |\n")
        f.write("|----------|-------|--------|----------------|\n")
        for rec in uplift_plan.recommendations[:10]:
            f.write(
                f"| {rec.priority.value.upper()} | {rec.title} | "
                f"{rec.effort.value} | {rec.expected_uplift_pct:.1f}% |\n"
            )
        f.write("\n")

        # Implementation Phases
        if uplift_plan.phases:
            f.write("### Implementation Phases\n\n")
            for phase in uplift_plan.phases:
                f.write(f"**{phase['name']}** ({phase['duration']})\n")
                f.write(f"- Expected uplift: {phase['expected_uplift']:.1f}%\n")
                f.write(f"- Recommendations: {len(phase['recommendations'])} items\n\n")

    def _generate_html(
        self,
        records: list[AuditRecord],
        maturity_report: MaturityReport | None = None,
        uplift_plan: UpliftPlan | None = None,
    ) -> None:
        """Generate HTML report.

        Args:
            records: Audit records
            maturity_report: Maturity assessment report
            uplift_plan: Uplift recommendations plan
        """
        report_path = self.run_dir / "report.html"
        logger.info(f"Generating HTML report: {report_path}")

        # Calculate summary stats
        avg_overall = sum(r.judge.overall for r in records) / len(records) if records else 0
        avg_relevance = sum(r.judge.relevance for r in records) / len(records) if records else 0
        avg_diversity = sum(r.judge.diversity for r in records) / len(records) if records else 0
        avg_quality = sum(r.judge.result_quality for r in records) / len(records) if records else 0
        avg_nav = sum(r.judge.navigability for r in records) / len(records) if records else 0

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Search Quality Audit Report</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .header {
            background: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .summary {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .summary table {
            width: 100%;
            border-collapse: collapse;
        }
        .summary th, .summary td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        .query-card {
            background: white;
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .query-title {
            font-size: 1.5em;
            margin-bottom: 15px;
            color: #333;
        }
        .scores {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .score-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid #007bff;
        }
        .score-label {
            font-size: 0.9em;
            color: #666;
            margin-bottom: 5px;
        }
        .score-value {
            font-size: 1.8em;
            font-weight: bold;
            color: #333;
        }
        .score-excellent { border-left-color: #28a745; }
        .score-good { border-left-color: #17a2b8; }
        .score-fair { border-left-color: #ffc107; }
        .score-poor { border-left-color: #dc3545; }
        .results-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        .results-table th, .results-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        .results-table th {
            background: #f8f9fa;
            font-weight: 600;
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
            background: white;
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
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
            background: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            text-align: center;
        }
        .dimension-name {
            font-size: 0.9em;
            color: #666;
            margin-bottom: 5px;
        }
        .dimension-score {
            font-size: 1.5em;
            font-weight: bold;
        }
        /* Uplift Section Styles */
        .uplift-section {
            background: white;
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .uplift-summary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .uplift-number {
            font-size: 2.5em;
            font-weight: bold;
        }
        .recommendation-card {
            border: 1px solid #e9ecef;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 10px;
        }
        .recommendation-card.priority-critical {
            border-left: 4px solid #dc3545;
        }
        .recommendation-card.priority-high {
            border-left: 4px solid #fd7e14;
        }
        .recommendation-card.priority-medium {
            border-left: 4px solid #ffc107;
        }
        .recommendation-card.priority-low {
            border-left: 4px solid #28a745;
        }
        .priority-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75em;
            font-weight: bold;
            text-transform: uppercase;
        }
        .priority-critical { background: #dc3545; color: white; }
        .priority-high { background: #fd7e14; color: white; }
        .priority-medium { background: #ffc107; color: #333; }
        .priority-low { background: #28a745; color: white; }
        .phase-timeline {
            margin: 20px 0;
        }
        .phase-item {
            padding: 15px;
            border-left: 3px solid #007bff;
            margin-left: 20px;
            margin-bottom: 15px;
            background: #f8f9fa;
            border-radius: 0 6px 6px 0;
        }
    </style>
</head>
<body>
""")

            # Header
            f.write(f"""
    <div class="header">
        <h1>Search Quality Audit Report</h1>
        <p><strong>Site:</strong> {self.config.site.url}</p>
        <p><strong>Date:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        <p><strong>Total Queries:</strong> {len(records)}</p>
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
                <td>Overall</td>
                <td>{avg_overall:.2f}</td>
            </tr>
            <tr>
                <td>Relevance</td>
                <td>{avg_relevance:.2f}</td>
            </tr>
            <tr>
                <td>Diversity</td>
                <td>{avg_diversity:.2f}</td>
            </tr>
            <tr>
                <td>Result Quality</td>
                <td>{avg_quality:.2f}</td>
            </tr>
            <tr>
                <td>Navigability</td>
                <td>{avg_nav:.2f}</td>
            </tr>
        </table>
    </div>
""")

            # Maturity Assessment Section
            if maturity_report:
                self._write_html_maturity_section(f, maturity_report)

            # Uplift Recommendations Section
            if uplift_plan:
                self._write_html_uplift_section(f, uplift_plan)

            # Query details
            for i, record in enumerate(records, 1):
                score_class = self._get_score_class(record.judge.overall)
                screenshot_rel = Path(record.page.screenshot_path).relative_to(self.run_dir)

                f.write(f"""
    <div class="query-card">
        <h2 class="query-title">{i}. {record.query.text}</h2>

        <div class="scores">
            <div class="score-item {score_class}">
                <div class="score-label">Overall</div>
                <div class="score-value">{record.judge.overall:.2f}</div>
            </div>
            <div class="score-item">
                <div class="score-label">Relevance</div>
                <div class="score-value">{record.judge.relevance:.2f}</div>
            </div>
            <div class="score-item">
                <div class="score-label">Diversity</div>
                <div class="score-value">{record.judge.diversity:.2f}</div>
            </div>
            <div class="score-item">
                <div class="score-label">Result Quality</div>
                <div class="score-value">{record.judge.result_quality:.2f}</div>
            </div>
            <div class="score-item">
                <div class="score-label">Navigability</div>
                <div class="score-value">{record.judge.navigability:.2f}</div>
            </div>
        </div>

        <p><strong>Rationale:</strong> {record.judge.rationale}</p>
""")

                if record.judge.issues:
                    f.write('        <div class="issues">\n')
                    f.write("            <strong>Issues:</strong>\n")
                    f.write("            <ul>\n")
                    for issue in record.judge.issues:
                        f.write(f"                <li>{issue}</li>\n")
                    f.write("            </ul>\n")
                    f.write("        </div>\n")

                if record.judge.improvements:
                    f.write('        <div class="improvements">\n')
                    f.write("            <strong>Suggested Improvements:</strong>\n")
                    f.write("            <ul>\n")
                    for improvement in record.judge.improvements:
                        f.write(f"                <li>{improvement}</li>\n")
                    f.write("            </ul>\n")
                    f.write("        </div>\n")

                # Results table
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
                    title = (item.title or "N/A")[:80]
                    price = item.price or "N/A"
                    url = (item.url or "N/A")[:80]
                    f.write(f"""
                <tr>
                    <td>{item.rank}</td>
                    <td>{title}</td>
                    <td>{price}</td>
                    <td><a href="{url}" target="_blank">{url[:50]}...</a></td>
                </tr>
""")

                f.write("""
            </tbody>
        </table>
""")

                # Screenshot
                f.write(f"""
        <h3>Screenshot</h3>
        <img src="{screenshot_rel}" alt="Screenshot" class="screenshot">
    </div>
""")

            f.write("""
</body>
</html>
""")

        logger.info(f"HTML report saved to {report_path}")

    def _write_html_maturity_section(self, f, maturity_report: MaturityReport) -> None:
        """Write maturity assessment section to HTML file."""
        level_class = f"maturity-l{maturity_report.overall_level.value}"

        f.write(f"""
    <div class="maturity-section">
        <h2>Maturity Assessment</h2>
        <p><span class="maturity-badge {level_class}">
            Level {maturity_report.overall_level.value}: {maturity_report.overall_level.name}
        </span></p>
        <p><strong>Overall Score:</strong> {maturity_report.overall_score:.2f}/5.00</p>
        <p>{maturity_report.executive_summary}</p>

        <h3>Dimension Scores</h3>
        <div class="dimension-grid">
""")

        for dim_name, dim_score in maturity_report.dimensions.items():
            score_class = self._get_score_class(dim_score.score)
            f.write(f"""
            <div class="dimension-item {score_class}">
                <div class="dimension-name">{dim_score.name}</div>
                <div class="dimension-score">{dim_score.score:.1f}</div>
                <div style="font-size: 0.8em; color: #666;">{dim_score.level.name}</div>
            </div>
""")

        f.write("        </div>\n")

        # Strengths and Weaknesses
        if maturity_report.strengths:
            f.write("        <h3>Strengths</h3>\n        <ul>\n")
            for strength in maturity_report.strengths:
                f.write(f"            <li style='color: #28a745;'>{strength}</li>\n")
            f.write("        </ul>\n")

        if maturity_report.weaknesses:
            f.write("        <h3>Areas for Improvement</h3>\n        <ul>\n")
            for weakness in maturity_report.weaknesses:
                f.write(f"            <li style='color: #dc3545;'>{weakness}</li>\n")
            f.write("        </ul>\n")

        f.write("    </div>\n")

    def _write_html_uplift_section(self, f, uplift_plan: UpliftPlan) -> None:
        """Write uplift recommendations section to HTML file."""
        f.write(f"""
    <div class="uplift-section">
        <h2>Conversion Uplift Opportunities</h2>

        <div class="uplift-summary">
            <div class="uplift-number">{uplift_plan.total_potential_uplift:.1f}%</div>
            <div>Total Potential Conversion Uplift</div>
            <p style="margin-top: 15px; font-size: 0.9em;">{uplift_plan.summary}</p>
        </div>
""")

        # Quick Wins
        if uplift_plan.quick_wins:
            f.write("        <h3>Quick Wins (0-4 weeks)</h3>\n")
            for rec in uplift_plan.quick_wins:
                f.write(f"""
        <div class="recommendation-card priority-{rec.priority.value}">
            <span class="priority-badge priority-{rec.priority.value}">{rec.priority.value}</span>
            <strong>{rec.title}</strong>
            <span style="float: right; color: #28a745;">+{rec.expected_uplift_pct:.1f}%</span>
            <p style="margin: 10px 0 0 0; color: #666;">{rec.description}</p>
        </div>
""")

        # Top Recommendations
        f.write("        <h3>All Recommendations</h3>\n")
        for rec in uplift_plan.recommendations[:10]:
            f.write(f"""
        <div class="recommendation-card priority-{rec.priority.value}">
            <span class="priority-badge priority-{rec.priority.value}">{rec.priority.value}</span>
            <strong>{rec.title}</strong>
            <span style="float: right;">
                <span style="color: #28a745;">+{rec.expected_uplift_pct:.1f}%</span>
                | Effort: {rec.effort.value}
            </span>
            <p style="margin: 10px 0 0 0; color: #666;">{rec.description}</p>
        </div>
""")

        # Implementation Phases
        if uplift_plan.phases:
            f.write(
                "        <h3>Implementation Roadmap</h3>\n        <div class='phase-timeline'>\n"
            )
            for phase in uplift_plan.phases:
                f.write(f"""
            <div class="phase-item">
                <strong>{phase['name']}</strong> ({phase['duration']})
                <br>
                <span style="color: #28a745;">Expected uplift: +{phase['expected_uplift']:.1f}%</span>
                | {len(phase['recommendations'])} recommendations
            </div>
""")
            f.write("        </div>\n")

        f.write("    </div>\n")

    def _generate_json(
        self,
        records: list[AuditRecord],
        maturity_report: MaturityReport | None = None,
        uplift_plan: UpliftPlan | None = None,
    ) -> None:
        """Generate JSON report.

        Args:
            records: Audit records
            maturity_report: Maturity assessment report
            uplift_plan: Uplift recommendations plan
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

        # Add uplift recommendations
        if uplift_plan:
            data["uplift"] = {
                "total_potential_uplift": uplift_plan.total_potential_uplift,
                "summary": uplift_plan.summary,
                "recommendations": [
                    {
                        "id": rec.id,
                        "title": rec.title,
                        "description": rec.description,
                        "category": rec.category.value,
                        "priority": rec.priority.value,
                        "effort": rec.effort.value,
                        "expected_uplift_pct": rec.expected_uplift_pct,
                        "confidence": rec.confidence,
                        "roi_score": rec.roi_score,
                        "metrics_to_track": rec.metrics_to_track,
                    }
                    for rec in uplift_plan.recommendations
                ],
                "phases": uplift_plan.phases,
            }

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
        if score >= 4:
            return "score-excellent"
        elif score >= 3:
            return "score-good"
        elif score >= 2:
            return "score-fair"
        else:
            return "score-poor"
