"""Shared test helpers."""

from typing import Any

from agentic_search_audit.core.types import DimensionDiagnosis, JudgeScore


def make_fqi_judge_score(**overrides: Any) -> JudgeScore:
    """Create a JudgeScore with FQI dimensions for testing.

    All dimension scores default to 3.5 unless overridden.
    Override individual dimension scores with e.g. query_understanding_score=4.0,
    or pass full DimensionDiagnosis objects with e.g. query_understanding=DimensionDiagnosis(...).

    Args:
        **overrides: Field overrides. Supports shorthand like
            query_understanding_score=4.0 (creates DimensionDiagnosis with that score)
            or full field overrides like rationale="custom".

    Returns:
        JudgeScore instance with computed FQI.
    """
    defaults: dict[str, Any] = {
        "query_understanding": DimensionDiagnosis(score=3.5, diagnosis="Adequate understanding"),
        "results_relevance": DimensionDiagnosis(score=3.5, diagnosis="Mostly relevant results"),
        "result_presentation": DimensionDiagnosis(score=3.5, diagnosis="Good presentation"),
        "advanced_features": DimensionDiagnosis(score=3.5, diagnosis="Basic features present"),
        "error_handling": DimensionDiagnosis(score=3.5, diagnosis="Adequate error handling"),
        "rationale": "Good search quality overall",
        "executive_summary": "Search performs adequately across dimensions.",
        "issues": [],
        "improvements": [],
        "evidence": [],
        "schema_version": "2.1",
    }

    # Handle shorthand score overrides like query_understanding_score=4.0
    dim_keys = [
        "query_understanding",
        "results_relevance",
        "result_presentation",
        "advanced_features",
        "error_handling",
    ]
    for dim_key in dim_keys:
        score_key = f"{dim_key}_score"
        diag_key = f"{dim_key}_diagnosis"
        if score_key in overrides or diag_key in overrides:
            score = overrides.pop(score_key, defaults[dim_key].score)
            diagnosis = overrides.pop(diag_key, defaults[dim_key].diagnosis)
            defaults[dim_key] = DimensionDiagnosis(score=score, diagnosis=diagnosis)

    defaults.update(overrides)
    return JudgeScore(**defaults)
