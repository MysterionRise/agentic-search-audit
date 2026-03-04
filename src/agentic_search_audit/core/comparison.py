"""Competitor comparison for search quality audits."""

import logging

from ..core.types import AuditRecord, Query, get_maturity_label

logger = logging.getLogger(__name__)


class QueryComparison:
    """Comparison of a single query across two sites."""

    def __init__(
        self,
        query_text: str,
        site_a_fqi: float,
        site_b_fqi: float,
        delta: float,
        site_a_dimensions: dict[str, float],
        site_b_dimensions: dict[str, float],
        winner: str,
    ) -> None:
        self.query_text = query_text
        self.site_a_fqi = site_a_fqi
        self.site_b_fqi = site_b_fqi
        self.delta = delta
        self.site_a_dimensions = site_a_dimensions
        self.site_b_dimensions = site_b_dimensions
        self.winner = winner


class ComparisonResult:
    """Complete comparison between two sites."""

    def __init__(
        self,
        site_a_name: str,
        site_b_name: str,
        site_a_avg_fqi: float,
        site_b_avg_fqi: float,
        site_a_maturity: str,
        site_b_maturity: str,
        query_comparisons: list[QueryComparison],
        dimension_comparison: dict[str, tuple[float, float]],
        overall_winner: str,
    ) -> None:
        self.site_a_name = site_a_name
        self.site_b_name = site_b_name
        self.site_a_avg_fqi = site_a_avg_fqi
        self.site_b_avg_fqi = site_b_avg_fqi
        self.site_a_maturity = site_a_maturity
        self.site_b_maturity = site_b_maturity
        self.query_comparisons = query_comparisons
        self.dimension_comparison = dimension_comparison
        self.overall_winner = overall_winner


def build_comparison(
    site_a_name: str,
    site_b_name: str,
    site_a_records: list[AuditRecord],
    site_b_records: list[AuditRecord],
    shared_queries: list[str],
) -> ComparisonResult:
    """Build comparison from two sets of audit records.

    Args:
        site_a_name: Name of site A.
        site_b_name: Name of site B.
        site_a_records: Audit records from site A.
        site_b_records: Audit records from site B.
        shared_queries: List of shared query texts.

    Returns:
        ComparisonResult with per-query and aggregate comparisons.
    """
    # Index records by normalized query text
    a_by_query = {r.query.text.strip().lower(): r for r in site_a_records}
    b_by_query = {r.query.text.strip().lower(): r for r in site_b_records}

    query_comparisons: list[QueryComparison] = []
    a_fqis: list[float] = []
    b_fqis: list[float] = []

    dim_keys = [
        "query_understanding",
        "results_relevance",
        "result_presentation",
        "advanced_features",
        "error_handling",
    ]
    dim_a_totals: dict[str, list[float]] = {k: [] for k in dim_keys}
    dim_b_totals: dict[str, list[float]] = {k: [] for k in dim_keys}

    for query_text in shared_queries:
        key = query_text.strip().lower()
        a_rec = a_by_query.get(key)
        b_rec = b_by_query.get(key)
        if not a_rec or not b_rec:
            continue

        a_fqi = a_rec.judge.fqi
        b_fqi = b_rec.judge.fqi
        delta = a_fqi - b_fqi

        a_dims = {k: getattr(a_rec.judge, k).score for k in dim_keys}
        b_dims = {k: getattr(b_rec.judge, k).score for k in dim_keys}

        winner = site_a_name if delta > 0 else site_b_name if delta < 0 else "tie"

        query_comparisons.append(
            QueryComparison(
                query_text=query_text,
                site_a_fqi=a_fqi,
                site_b_fqi=b_fqi,
                delta=delta,
                site_a_dimensions=a_dims,
                site_b_dimensions=b_dims,
                winner=winner,
            )
        )

        a_fqis.append(a_fqi)
        b_fqis.append(b_fqi)
        for k in dim_keys:
            dim_a_totals[k].append(a_dims[k])
            dim_b_totals[k].append(b_dims[k])

    a_avg = sum(a_fqis) / len(a_fqis) if a_fqis else 0.0
    b_avg = sum(b_fqis) / len(b_fqis) if b_fqis else 0.0

    dimension_comparison: dict[str, tuple[float, float]] = {}
    for k in dim_keys:
        a_dim_avg = sum(dim_a_totals[k]) / len(dim_a_totals[k]) if dim_a_totals[k] else 0.0
        b_dim_avg = sum(dim_b_totals[k]) / len(dim_b_totals[k]) if dim_b_totals[k] else 0.0
        dimension_comparison[k] = (a_dim_avg, b_dim_avg)

    overall_winner = site_a_name if a_avg > b_avg else site_b_name if b_avg > a_avg else "tie"

    return ComparisonResult(
        site_a_name=site_a_name,
        site_b_name=site_b_name,
        site_a_avg_fqi=a_avg,
        site_b_avg_fqi=b_avg,
        site_a_maturity=get_maturity_label(a_avg),
        site_b_maturity=get_maturity_label(b_avg),
        query_comparisons=query_comparisons,
        dimension_comparison=dimension_comparison,
        overall_winner=overall_winner,
    )


def find_shared_queries(queries_a: list[Query], queries_b: list[Query]) -> list[str]:
    """Find shared queries between two sets by normalized text.

    Args:
        queries_a: Queries from site A.
        queries_b: Queries from site B.

    Returns:
        List of shared query texts.
    """
    set_a = {q.text.strip().lower() for q in queries_a}
    set_b = {q.text.strip().lower() for q in queries_b}
    shared = set_a & set_b
    # Return in original casing from queries_a
    return [q.text for q in queries_a if q.text.strip().lower() in shared]
