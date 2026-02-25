"""Tests for adaptive throttle in orchestrator."""

import pytest

from agentic_search_audit.core.orchestrator import SearchAuditOrchestrator
from agentic_search_audit.core.types import AuditConfig


@pytest.fixture
def orchestrator(sample_config_dict, tmp_path):
    """Create an orchestrator with sample config."""
    config = AuditConfig(**sample_config_dict)
    return SearchAuditOrchestrator(config, [], tmp_path)


@pytest.mark.unit
def test_signal_resistance_increases_multiplier(orchestrator):
    """_signal_resistance() should increase throttle multiplier by 1.5x."""
    assert orchestrator._throttle_multiplier == 1.0
    orchestrator._signal_resistance()
    assert orchestrator._throttle_multiplier == 1.5
    orchestrator._signal_resistance()
    assert abs(orchestrator._throttle_multiplier - 2.25) < 0.01


@pytest.mark.unit
def test_signal_resistance_capped_at_5(orchestrator):
    """Throttle multiplier should not exceed 5.0."""
    for _ in range(20):
        orchestrator._signal_resistance()
    assert orchestrator._throttle_multiplier <= 5.0


@pytest.mark.unit
def test_signal_success_decays_multiplier(orchestrator):
    """_signal_success() should decay throttle multiplier toward 1.0."""
    orchestrator._throttle_multiplier = 3.0
    orchestrator._signal_success()
    assert abs(orchestrator._throttle_multiplier - 2.7) < 0.01
    orchestrator._signal_success()
    assert abs(orchestrator._throttle_multiplier - 2.43) < 0.01


@pytest.mark.unit
def test_signal_success_floors_at_1(orchestrator):
    """Throttle multiplier should not go below 1.0."""
    orchestrator._throttle_multiplier = 1.05
    orchestrator._signal_success()
    assert orchestrator._throttle_multiplier == 1.0


@pytest.mark.unit
def test_resistance_then_success_recovery(orchestrator):
    """Multiple resistances followed by successes should recover."""
    # Simulate resistance
    for _ in range(5):
        orchestrator._signal_resistance()
    high_multiplier = orchestrator._throttle_multiplier
    assert high_multiplier > 1.0

    # Simulate recovery
    for _ in range(50):
        orchestrator._signal_success()
    assert orchestrator._throttle_multiplier == 1.0
