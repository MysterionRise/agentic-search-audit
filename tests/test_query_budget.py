"""Per-query time budget derivation."""

import pytest

from agentic_search_audit.core.types import (
    AuditConfig,
    LLMConfig,
    RunConfig,
    SiteConfig,
    query_time_budget_s,
)

pytestmark = pytest.mark.unit


def _config(**run: object) -> AuditConfig:
    return AuditConfig(
        site=SiteConfig(url="https://example.com"),  # type: ignore[arg-type]
        run=RunConfig(**run),  # type: ignore[arg-type]
        llm=LLMConfig(),
    )


def test_default_budget_is_browser_plus_two_vision_calls() -> None:
    assert query_time_budget_s(_config()) == 90 + 2 * 90


def test_pdp_adds_its_visits() -> None:
    assert query_time_budget_s(_config(enable_pdp_analysis=True)) == 270 + 3 * 15


def test_explicit_timeout_wins() -> None:
    assert query_time_budget_s(_config(query_timeout_s=42, enable_pdp_analysis=True)) == 42


def test_budget_follows_the_configured_parts() -> None:
    config = _config(
        browser_budget_s=30, enable_pdp_analysis=True, pdp_top_k=2, pdp_timeout_ms=5000
    )
    config.llm.vision_timeout = 10
    assert query_time_budget_s(config) == 30 + 20 + 10


def test_llm_config_has_timeouts_and_rate_limits() -> None:
    llm = LLMConfig()
    assert (llm.timeout, llm.vision_timeout, llm.max_concurrent, llm.min_request_interval_s) == (
        30.0,
        90.0,
        3,
        0.5,
    )
