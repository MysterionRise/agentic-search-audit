"""Tests for CLI interface."""

import json
import tempfile
from pathlib import Path

import pytest

from agentic_search_audit.cli.main import load_queries, parse_args


@pytest.mark.unit
def test_load_queries_from_list():
    """Test loading queries from a simple list."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(["query 1", "query 2", "query 3"], f)
        queries_path = Path(f.name)

    try:
        queries = load_queries(queries_path)

        assert len(queries) == 3
        assert queries[0].text == "query 1"
        assert queries[1].text == "query 2"
        assert queries[2].text == "query 3"
        assert queries[0].id == "q001"
        assert queries[1].id == "q002"
    finally:
        queries_path.unlink()


@pytest.mark.unit
def test_load_queries_from_objects():
    """Test loading queries from object format."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {
                "queries": [
                    {
                        "id": "custom-1",
                        "text": "search query",
                        "lang": "en",
                        "origin": "predefined",
                    }
                ]
            },
            f,
        )
        queries_path = Path(f.name)

    try:
        queries = load_queries(queries_path)

        assert len(queries) == 1
        assert queries[0].id == "custom-1"
        assert queries[0].text == "search query"
        assert queries[0].lang == "en"
    finally:
        queries_path.unlink()


@pytest.mark.unit
def test_load_queries_mixed_format():
    """Test loading queries from mixed format."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {
                "queries": [
                    "simple query",
                    {"id": "q2", "text": "complex query", "lang": "es"},
                ]
            },
            f,
        )
        queries_path = Path(f.name)

    try:
        queries = load_queries(queries_path)

        assert len(queries) == 2
        assert queries[0].text == "simple query"
        assert queries[0].id == "q001"
        assert queries[1].id == "q2"
        assert queries[1].text == "complex query"
        assert queries[1].lang == "es"
    finally:
        queries_path.unlink()


@pytest.mark.unit
def test_parse_args_defaults(monkeypatch):
    """Test CLI argument parsing with defaults."""
    monkeypatch.setattr(
        "sys.argv",
        ["search-audit", "--site", "nike"],
    )

    args = parse_args()

    assert args.site == "nike"
    assert args.url is None
    assert args.log_level == "INFO"


@pytest.mark.unit
def test_parse_args_custom(monkeypatch):
    """Test CLI argument parsing with custom values."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "search-audit",
            "--url",
            "https://example.com",
            "--queries",
            "queries.json",
            "--output",
            "./output",
            "--top-k",
            "20",
            "--seed",
            "42",
            "--log-level",
            "DEBUG",
            "--no-headless",
        ],
    )

    args = parse_args()

    assert args.url == "https://example.com"
    assert args.queries == Path("queries.json")
    assert args.output == Path("./output")
    assert args.top_k == 20
    assert args.seed == 42
    assert args.log_level == "DEBUG"
    assert args.no_headless is True
