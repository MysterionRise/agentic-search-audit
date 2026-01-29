"""Report generation for audit results."""

import json
import logging
from datetime import datetime
from pathlib import Path

from ..core.types import AuditConfig, AuditRecord

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates human-readable reports from audit results."""

    def __init__(self, config: AuditConfig, run_dir: Path):
        """Initialize report generator.

        Args:
            config: Audit configuration
            run_dir: Run output directory
        """
        self.config = config
        self.run_dir = run_dir

    def generate_reports(self, records: list[AuditRecord]) -> None:
        """Generate all configured report formats.

        Args:
            records: List of audit records
        """
        logger.info(f"Generating reports in {self.run_dir}")

        if "md" in self.config.report.formats:
            self._generate_markdown(records)

        if "html" in self.config.report.formats:
            self._generate_html(records)

        if "json" in self.config.report.formats:
            self._generate_json(records)

        logger.info("Reports generated successfully")

    def _generate_markdown(self, records: list[AuditRecord]) -> None:
        """Generate Markdown report.

        Args:
            records: Audit records
        """
        report_path = self.run_dir / "report.md"
        logger.info(f"Generating Markdown report: {report_path}")

        with open(report_path, "w", encoding="utf-8") as f:
            # Header
            f.write("# Search Quality Audit Report\n\n")
            f.write(f"**Site:** {self.config.site.url}\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Total Queries:** {len(records)}\n\n")

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

    def _generate_html(self, records: list[AuditRecord]) -> None:
        """Generate HTML report.

        Args:
            records: Audit records
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

    def _generate_json(self, records: list[AuditRecord]) -> None:
        """Generate JSON report.

        Args:
            records: Audit records
        """
        report_path = self.run_dir / "audit.json"
        logger.info(f"Generating JSON report: {report_path}")

        data = {
            "site": str(self.config.site.url),
            "timestamp": datetime.now().isoformat(),
            "total_queries": len(records),
            "records": [r.model_dump(mode="json") for r in records],
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
