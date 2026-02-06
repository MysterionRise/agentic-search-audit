"""Pytest configuration and shared fixtures."""

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def project_root():
    """Get project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def configs_dir(project_root):
    """Get configs directory."""
    return project_root / "configs"


@pytest.fixture(scope="session")
def data_dir(project_root):
    """Get data directory."""
    return project_root / "data"


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for tests."""
    # Set a dummy OpenAI API key for tests that don't actually call the API
    if "OPENAI_API_KEY" not in os.environ:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-for-testing-only")


@pytest.fixture
def sample_config_dict():
    """Sample configuration dictionary."""
    return {
        "site": {
            "url": "https://www.example.com",
            "locale": "en-US",
        },
        "run": {
            "top_k": 10,
            "headless": True,
            "viewport_width": 1366,
            "viewport_height": 900,
        },
        "llm": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "max_tokens": 2000,
            "temperature": 0.2,
        },
        "report": {
            "formats": ["md", "html"],
            "out_dir": "./runs",
        },
    }
