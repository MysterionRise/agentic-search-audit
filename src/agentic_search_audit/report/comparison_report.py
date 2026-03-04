"""Generate comparison reports between two site audits."""

import logging
from datetime import datetime
from pathlib import Path

from ..core.comparison import ComparisonResult

logger = logging.getLogger(__name__)


class ComparisonReportGenerator:
    """Generates comparison reports in Markdown and HTML."""

    def __init__(self, result: ComparisonResult, run_dir: Path) -> None:
        self.result = result
        self.run_dir = run_dir

    def generate(self) -> None:
        """Generate all comparison report formats."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._generate_markdown()
        self._generate_html()
        logger.info(f"Comparison reports generated in {self.run_dir}")

    def _generate_markdown(self) -> None:
        """Generate Markdown comparison report."""
        path = self.run_dir / "comparison_report.md"
        r = self.result

        with open(path, "w", encoding="utf-8") as f:
            f.write("# Search Quality Comparison Report\n\n")
            f.write(f"**{r.site_a_name}** vs **{r.site_b_name}**\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Queries Compared:** {len(r.query_comparisons)}\n\n")

            # Overall winner
            f.write("## Overall Results\n\n")
            f.write(f"| Metric | {r.site_a_name} | {r.site_b_name} |\n")
            f.write(
                "|--------|{a_sep}|{b_sep}|\n".format(
                    a_sep="-" * (len(r.site_a_name) + 2),
                    b_sep="-" * (len(r.site_b_name) + 2),
                )
            )
            f.write(f"| FQI Score | {r.site_a_avg_fqi:.2f} | {r.site_b_avg_fqi:.2f} |\n")
            f.write(f"| Maturity | {r.site_a_maturity} | {r.site_b_maturity} |\n")
            if r.overall_winner == "tie":
                f.write("| **Overall** | Tie | Tie |\n\n")
            else:
                winner_marker_a = "-- Winner --" if r.overall_winner == r.site_a_name else ""
                winner_marker_b = "-- Winner --" if r.overall_winner == r.site_b_name else ""
                f.write(f"| **Overall** | {winner_marker_a} | {winner_marker_b} |\n\n")

            # Dimension comparison
            f.write("## Dimension Comparison\n\n")
            f.write(f"| Dimension | {r.site_a_name} | {r.site_b_name} | Delta |\n")
            f.write(
                "|-----------|{a_sep}|{b_sep}|-------|\n".format(
                    a_sep="-" * (len(r.site_a_name) + 2),
                    b_sep="-" * (len(r.site_b_name) + 2),
                )
            )
            dim_labels = {
                "query_understanding": "Query Understanding",
                "results_relevance": "Results Relevance",
                "result_presentation": "Result Presentation",
                "advanced_features": "Advanced Features",
                "error_handling": "Error Handling",
            }
            for dim_key, label in dim_labels.items():
                a_val, b_val = r.dimension_comparison.get(dim_key, (0.0, 0.0))
                delta = a_val - b_val
                delta_str = f"+{delta:.2f}" if delta >= 0 else f"{delta:.2f}"
                f.write(f"| {label} | {a_val:.2f} | {b_val:.2f} | {delta_str} |\n")
            f.write("\n")

            # Head-to-head query table
            f.write("## Head-to-Head Query Results\n\n")
            f.write(f"| Query | {r.site_a_name} FQI | {r.site_b_name} FQI | Delta | Winner |\n")
            f.write(
                "|-------|{a_sep}|{b_sep}|-------|--------|\n".format(
                    a_sep="-" * (len(r.site_a_name) + 6),
                    b_sep="-" * (len(r.site_b_name) + 6),
                )
            )
            for qc in r.query_comparisons:
                delta_str = f"+{qc.delta:.2f}" if qc.delta >= 0 else f"{qc.delta:.2f}"
                f.write(
                    f"| {qc.query_text} | {qc.site_a_fqi:.2f} | {qc.site_b_fqi:.2f}"
                    f" | {delta_str} | {qc.winner} |\n"
                )
            f.write("\n")

            # Summary
            a_wins = sum(1 for qc in r.query_comparisons if qc.winner == r.site_a_name)
            b_wins = sum(1 for qc in r.query_comparisons if qc.winner == r.site_b_name)
            ties = sum(1 for qc in r.query_comparisons if qc.winner == "tie")
            f.write("## Summary\n\n")
            f.write(f"- **{r.site_a_name}** wins {a_wins} queries\n")
            f.write(f"- **{r.site_b_name}** wins {b_wins} queries\n")
            f.write(f"- Ties: {ties}\n")
            f.write(f"- **Overall Winner: {r.overall_winner}**\n")

        logger.info(f"Markdown comparison report: {path}")

    def _generate_html(self) -> None:
        """Generate HTML comparison report."""
        path = self.run_dir / "comparison_report.html"
        r = self.result

        dim_labels = {
            "query_understanding": "Query Understanding",
            "results_relevance": "Results Relevance",
            "result_presentation": "Result Presentation",
            "advanced_features": "Advanced Features",
            "error_handling": "Error Handling",
        }

        # Build dimension rows
        dim_rows = ""
        for dk, label in dim_labels.items():
            a_val, b_val = r.dimension_comparison.get(dk, (0.0, 0.0))
            delta = a_val - b_val
            cls = "positive" if delta > 0 else "negative" if delta < 0 else ""
            delta_str = f"+{delta:.2f}" if delta >= 0 else f"{delta:.2f}"
            dim_rows += (
                f"<tr><td>{label}</td><td>{a_val:.2f}</td><td>{b_val:.2f}</td>"
                f"<td class='{cls}'>{delta_str}</td></tr>\n"
            )

        # Build query rows
        query_rows = ""
        for qc in r.query_comparisons:
            delta_str = f"+{qc.delta:.2f}" if qc.delta >= 0 else f"{qc.delta:.2f}"
            cls = "positive" if qc.delta > 0 else "negative" if qc.delta < 0 else ""
            query_rows += (
                f"<tr><td>{qc.query_text}</td><td>{qc.site_a_fqi:.2f}</td>"
                f"<td>{qc.site_b_fqi:.2f}</td><td class='{cls}'>{delta_str}</td>"
                f"<td>{qc.winner}</td></tr>\n"
            )

        a_wins = sum(1 for qc in r.query_comparisons if qc.winner == r.site_a_name)
        b_wins = sum(1 for qc in r.query_comparisons if qc.winner == r.site_b_name)

        winner_a_cls = "winner" if r.overall_winner == r.site_a_name else ""
        winner_b_cls = "winner" if r.overall_winner == r.site_b_name else ""

        html_content = (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f"<title>Comparison: {r.site_a_name} vs {r.site_b_name}</title>\n"
            "<style>\n"
            "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,"
            " sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px;"
            " background: #f5f5f5; }\n"
            "h1 { color: #1a1a2e; }\n"
            ".card { background: white; border-radius: 8px; padding: 24px; margin: 16px 0;"
            " box-shadow: 0 2px 4px rgba(0,0,0,0.1); }\n"
            ".scorecard { display: flex; gap: 24px; justify-content: center; }\n"
            ".site-score { text-align: center; padding: 20px; flex: 1; }\n"
            ".site-score h2 { margin: 0 0 8px; }\n"
            ".fqi { font-size: 2em; font-weight: bold; }\n"
            ".winner { color: #27ae60; }\n"
            "table { width: 100%; border-collapse: collapse; margin: 16px 0; }\n"
            "th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; }\n"
            "th { background: #f8f9fa; font-weight: 600; }\n"
            ".positive { color: #27ae60; }\n"
            ".negative { color: #e74c3c; }\n"
            "@media print {\n"
            "    body { background: white; }\n"
            "    .card { box-shadow: none; border: 1px solid #ddd; break-inside: avoid; }\n"
            "}\n"
            "</style>\n"
            "</head>\n"
            "<body>\n"
            "<h1>Search Quality Comparison</h1>\n"
            f"<p><strong>{r.site_a_name}</strong> vs <strong>{r.site_b_name}</strong>"
            f" &mdash; {datetime.now().strftime('%Y-%m-%d')}</p>\n"
            f"<p>{len(r.query_comparisons)} shared queries compared</p>\n"
            "\n"
            '<div class="card">\n'
            '<div class="scorecard">\n'
            '<div class="site-score">\n'
            f"<h2>{r.site_a_name}</h2>\n"
            f'<div class="fqi {winner_a_cls}">{r.site_a_avg_fqi:.2f}</div>\n'
            f"<div>{r.site_a_maturity}</div>\n"
            "</div>\n"
            '<div class="site-score" style="display:flex;align-items:center;'
            'font-size:2em;flex:0;">vs</div>\n'
            '<div class="site-score">\n'
            f"<h2>{r.site_b_name}</h2>\n"
            f'<div class="fqi {winner_b_cls}">{r.site_b_avg_fqi:.2f}</div>\n'
            f"<div>{r.site_b_maturity}</div>\n"
            "</div>\n"
            "</div>\n"
            f'<p style="text-align:center;font-weight:bold;">'
            f"Overall Winner: {r.overall_winner}</p>\n"
            "</div>\n"
            "\n"
            '<div class="card">\n'
            "<h2>Dimension Comparison</h2>\n"
            "<table>\n"
            f"<tr><th>Dimension</th><th>{r.site_a_name}</th>"
            f"<th>{r.site_b_name}</th><th>Delta</th></tr>\n"
            f"{dim_rows}"
            "</table>\n"
            "</div>\n"
            "\n"
            '<div class="card">\n'
            "<h2>Head-to-Head Results</h2>\n"
            "<table>\n"
            f"<tr><th>Query</th><th>{r.site_a_name}</th>"
            f"<th>{r.site_b_name}</th><th>Delta</th><th>Winner</th></tr>\n"
            f"{query_rows}"
            "</table>\n"
            "</div>\n"
            "\n"
            '<div class="card">\n'
            "<h2>Summary</h2>\n"
            f"<p><strong>{r.site_a_name}</strong> wins {a_wins} queries | "
            f"<strong>{r.site_b_name}</strong> wins {b_wins} queries</p>\n"
            "</div>\n"
            "</body>\n"
            "</html>"
        )

        path.write_text(html_content, encoding="utf-8")
        logger.info(f"HTML comparison report: {path}")
