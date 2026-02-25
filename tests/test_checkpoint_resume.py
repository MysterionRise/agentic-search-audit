"""Tests for checkpoint resume in orchestrator."""

import json

import pytest

from agentic_search_audit.core.orchestrator import SearchAuditOrchestrator, _find_latest_run_dir
from agentic_search_audit.core.types import (
    AuditConfig,
    AuditRecord,
    DimensionDiagnosis,
    JudgeScore,
    PageArtifacts,
    Query,
    ResultItem,
)


def _make_record(query_id: str, query_text: str) -> dict:
    """Build a minimal AuditRecord dict for JSONL."""
    record = AuditRecord(
        site="https://www.example.com/",
        query=Query(id=query_id, text=query_text),
        items=[ResultItem(rank=1, title="Test")],
        page=PageArtifacts(
            url="https://www.example.com/",
            final_url="https://www.example.com/search?q=test",
            html_path="/tmp/test.html",
            screenshot_path="/tmp/test.png",
        ),
        judge=JudgeScore(
            query_understanding=DimensionDiagnosis(score=4.0, diagnosis="Good"),
            results_relevance=DimensionDiagnosis(score=4.0, diagnosis="Good"),
            result_presentation=DimensionDiagnosis(score=3.5, diagnosis="OK"),
            advanced_features=DimensionDiagnosis(score=3.0, diagnosis="OK"),
            error_handling=DimensionDiagnosis(score=3.0, diagnosis="OK"),
            rationale="Good",
        ),
    )
    return record.model_dump(mode="json")


@pytest.fixture
def sample_config(sample_config_dict):
    return AuditConfig(**sample_config_dict)


@pytest.mark.unit
def test_load_checkpoint_no_file(sample_config, tmp_path):
    """Should return empty set when no JSONL exists."""
    orchestrator = SearchAuditOrchestrator(sample_config, [], tmp_path)
    ids = orchestrator._load_checkpoint()
    assert ids == set()
    assert len(orchestrator.records) == 0


@pytest.mark.unit
def test_load_checkpoint_with_records(sample_config, tmp_path):
    """Should load completed query IDs from existing JSONL."""
    # Write two records to JSONL
    jsonl_path = tmp_path / "audit.jsonl"
    with open(jsonl_path, "w") as f:
        f.write(json.dumps(_make_record("q001", "red shoes")) + "\n")
        f.write(json.dumps(_make_record("q002", "blue jacket")) + "\n")

    orchestrator = SearchAuditOrchestrator(sample_config, [], tmp_path)
    ids = orchestrator._load_checkpoint()
    assert ids == {"q001", "q002"}
    assert len(orchestrator.records) == 2


@pytest.mark.unit
def test_load_checkpoint_skips_malformed_lines(sample_config, tmp_path):
    """Should skip malformed JSON lines gracefully."""
    jsonl_path = tmp_path / "audit.jsonl"
    with open(jsonl_path, "w") as f:
        f.write(json.dumps(_make_record("q001", "red shoes")) + "\n")
        f.write("not valid json\n")
        f.write(json.dumps(_make_record("q003", "green hat")) + "\n")

    orchestrator = SearchAuditOrchestrator(sample_config, [], tmp_path)
    ids = orchestrator._load_checkpoint()
    assert ids == {"q001", "q003"}
    assert len(orchestrator.records) == 2


@pytest.mark.unit
def test_load_checkpoint_empty_file(sample_config, tmp_path):
    """Should handle empty JSONL file."""
    jsonl_path = tmp_path / "audit.jsonl"
    jsonl_path.write_text("")

    orchestrator = SearchAuditOrchestrator(sample_config, [], tmp_path)
    ids = orchestrator._load_checkpoint()
    assert ids == set()


@pytest.mark.unit
def test_find_latest_run_dir_no_dirs(tmp_path):
    """Should return None when no run dirs exist."""
    assert _find_latest_run_dir(tmp_path, "example.com") is None


@pytest.mark.unit
def test_find_latest_run_dir_no_site(tmp_path):
    """Should return None when site dir doesn't exist."""
    assert _find_latest_run_dir(tmp_path, "nonexistent.com") is None


@pytest.mark.unit
def test_find_latest_run_dir_finds_latest(tmp_path):
    """Should return the latest run dir with a JSONL file."""
    site_dir = tmp_path / "example.com"
    old_dir = site_dir / "20250101_120000"
    new_dir = site_dir / "20250225_150000"
    old_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)

    # Only the newer has a JSONL
    (new_dir / "audit.jsonl").write_text("")

    result = _find_latest_run_dir(tmp_path, "example.com")
    assert result == new_dir


@pytest.mark.unit
def test_find_latest_run_dir_ignores_no_jsonl(tmp_path):
    """Should skip dirs without audit.jsonl."""
    site_dir = tmp_path / "example.com"
    dir1 = site_dir / "20250101_120000"
    dir2 = site_dir / "20250102_120000"
    dir1.mkdir(parents=True)
    dir2.mkdir(parents=True)

    (dir1 / "audit.jsonl").write_text("")
    # dir2 has no jsonl

    result = _find_latest_run_dir(tmp_path, "example.com")
    assert result == dir1
