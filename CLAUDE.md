# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Agentic Search Audit evaluates on-site search quality using browser automation and LLM-as-a-judge. It uses chrome-devtools-mcp to control a real browser, runs searches on target websites, extracts results, and scores search quality with an LLM.

## Common Commands

```bash
# Install
pip install -e ".[dev]"

# Run tests
make test                    # All tests
make test-cov                # With coverage
pytest tests/test_config.py  # Single file
pytest tests/ -m unit        # Unit tests only

# Code quality
make lint                    # Ruff + Black check
make lint-fix                # Fix issues
make format                  # Black format
make typecheck               # mypy

# Run all CI checks
make ci

# Run audit
search-audit --site nike --config configs/sites/nike.yaml
search-audit --site nike --no-headless  # Visible browser
```

## Architecture

```
CLI (cli/main.py)
    ↓
Orchestrator (core/orchestrator.py) - manages audit flow, rate limiting
    ↓
┌───────────────────────────────────────────────────────────┐
│ MCP Client (mcp/client.py) - chrome-devtools-mcp wrapper  │
└───────────────────────────────────────────────────────────┘
    ↓
Extractors (extractors/):
  - search_box.py: finds search input via CSS selectors + vision fallback
  - results.py: parses search results from DOM
  - modals.py: dismisses cookie/consent dialogs
  - intelligent_finder.py + vision_provider.py: LLM vision for search box detection
    ↓
Judge (judge/judge.py + rubric.py) - LLM evaluation with structured JSON schema
    ↓
Reporter (report/generator.py) - Markdown, HTML, JSONL output
```

**Key types** are in `core/types.py`: `Query`, `ResultItem`, `JudgeScore`, `AuditConfig` (all Pydantic models).

## Configuration System

- `configs/default.yaml` - global defaults
- `configs/sites/*.yaml` - site-specific overrides (e.g., nike.yaml)
- `data/queries/*.json` - predefined query sets
- CLI args override config values

Vision providers (for intelligent search box detection): vLLM (local), OpenRouter, OpenAI. Configure in YAML under `llm.provider`.

## Code Style

- Black with 100 char line length
- Ruff for linting (rules: E, F, I, N, W, UP)
- mypy with `disallow_untyped_defs = true`
- Pre-commit hooks configured

## Testing Notes

- Tests use `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow` markers
- `asyncio_mode = "auto"` in pytest config
- Coverage ~46%, lower in browser automation code (mcp/, extractors/)
- `conftest.py` has shared fixtures with mocked env vars
