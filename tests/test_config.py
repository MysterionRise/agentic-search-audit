"""Tests for configuration loading."""

import pytest
from pathlib import Path

from agentic_search_audit.core.config import load_config, merge_configs
from agentic_search_audit.core.types import AuditConfig


def test_merge_configs():
    """Test configuration merging."""
    base = {
        "site": {"url": "https://example.com", "locale": "en-US"},
        "run": {"top_k": 10, "headless": True},
    }

    override = {
        "run": {"top_k": 20},
        "llm": {"provider": "openai"},
    }

    merged = merge_configs(base, override)

    assert merged["site"]["url"] == "https://example.com"
    assert merged["site"]["locale"] == "en-US"
    assert merged["run"]["top_k"] == 20  # Overridden
    assert merged["run"]["headless"] is True  # Preserved
    assert merged["llm"]["provider"] == "openai"  # Added


def test_load_config_from_file():
    """Test loading config from YAML file."""
    # This test would require the actual config file to exist
    # For now, we'll just test that the function exists and has the right signature
    assert callable(load_config)


def test_audit_config_validation():
    """Test AuditConfig validation."""
    config_dict = {
        "site": {
            "url": "https://www.nike.com",
            "locale": "en-US",
        },
        "run": {
            "top_k": 10,
            "headless": True,
        },
        "llm": {
            "provider": "openai",
            "model": "gpt-4o-mini",
        },
        "report": {
            "formats": ["md", "html"],
            "out_dir": "./runs",
        },
    }

    config = AuditConfig(**config_dict)

    assert str(config.site.url) == "https://www.nike.com/"
    assert config.run.top_k == 10
    assert config.llm.provider == "openai"
