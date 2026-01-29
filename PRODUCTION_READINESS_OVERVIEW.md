# Production Readiness Audit - Agentic Search Audit

**Date:** 2026-01-29
**Version:** 0.1.0 (Alpha)
**Repository:** agentic-search-audit

---

## Executive Summary

This document provides a comprehensive production readiness assessment of the Agentic Search Audit tool. Use this overview for planning further development with other LLMs.

**Overall Status:** `BETA READY` - Production-ready for MVP deployments with known limitations.

| Metric | Value |
|--------|-------|
| Total LOC | ~3,262 |
| Test Coverage | 41% |
| Tests Passing | 32/32 (100%) |
| Lint Status | PASS (Ruff) |
| Format Status | PASS (Black) |
| Type Checking | 26 errors (non-blocking in CI) |
| Security Issues | 1 Medium (temp file path) |
| Python Versions | 3.10, 3.11, 3.12, 3.13 |

---

## 1. Project Purpose

**What it does:** Automated evaluation of on-site search quality through:
1. Real browser automation via MCP protocol (chrome-devtools-mcp)
2. Intelligent search box detection with CSS selectors + LLM vision fallback
3. Results extraction via configurable DOM parsing
4. LLM-as-a-judge scoring with structured rubric (5 dimensions, 0-5 scale)
5. Multi-format reporting (Markdown, HTML, JSONL)

**Target Users:** E-commerce teams, Search QA engineers, SEO professionals

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI (main.py)                           │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                    Orchestrator (core/)                          │
│  - Rate limiting (RateLimiter, retry_with_backoff)              │
│  - Flow control                                                  │
│  - Error handling                                                │
└──────┬──────────────┬──────────────┬──────────────┬─────────────┘
       │              │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌──────▼──────┐ ┌────▼─────┐
│ MCP Client  │ │ Extractors │ │   Judge    │ │ Reporter │
│ (mcp/)      │ │            │ │ (judge/)   │ │ (report/)│
│             │ │ - search   │ │            │ │          │
│ - navigate  │ │ - results  │ │ - rubric   │ │ - md     │
│ - click     │ │ - modals   │ │ - scoring  │ │ - html   │
│ - screenshot│ │ - vision   │ │            │ │ - json   │
└─────────────┘ └────────────┘ └────────────┘ └──────────┘
```

### Module Responsibilities

| Module | Files | LOC | Purpose |
|--------|-------|-----|---------|
| `core/` | 4 | ~574 | Orchestration, types (Pydantic), config loading, rate limiting |
| `mcp/` | 1 | 421 | MCP client wrapper for chrome-devtools-mcp |
| `extractors/` | 5 | 685 | Search box finder, results extraction, modal handling, vision providers |
| `judge/` | 2 | 390 | LLM evaluation with structured JSON output |
| `report/` | 1 | 479 | Multi-format report generation |
| `cli/` | 1 | 283 | CLI interface (argparse) |

---

## 3. Current Implementation Status

### ✅ Fully Implemented (Production Ready)

| Feature | Module | Notes |
|---------|--------|-------|
| CLI interface | `cli/main.py` | Full argparse with help, examples |
| Configuration system | `core/config.py` | YAML-based with env var support |
| Type system | `core/types.py` | Pydantic v2 models, 100% coverage |
| Rate limiting | `core/policies.py` | Configurable RPS, retry with backoff |
| MCP browser client | `mcp/client.py` | Navigate, click, type, screenshot, eval |
| Search box detection | `extractors/search_box.py` | CSS selectors + LLM vision fallback |
| Results extraction | `extractors/results.py` | Configurable selectors for title/price/etc |
| Modal handling | `extractors/modals.py` | Cookie consent auto-dismiss |
| LLM Judge | `judge/judge.py` | OpenAI, OpenRouter, vLLM support |
| Scoring rubric | `judge/rubric.py` | 5-dimension structured evaluation |
| Report generation | `report/generator.py` | MD, HTML, JSONL formats (97% coverage) |
| CI/CD pipeline | `.github/workflows/` | Multi-Python, lint, security checks |

### ⚠️ Partially Implemented

| Feature | Status | Gap |
|---------|--------|-----|
| Anthropic vision provider | Stub only | `TODO` in `vision_provider.py:261` |
| Integration tests | 0 tests | No `@pytest.mark.integration` tests |
| E2E tests | None | No real browser tests |
| Robots.txt compliance | Documented P1 | Not implemented |

### ❌ Not Yet Implemented (Roadmap)

| Feature | Priority | Notes |
|---------|----------|-------|
| LLM-generated queries | P1 | From site content |
| Multi-language support | P3 | i18n |
| Cross-model reliability | P4 | Compare LLM judges |
| API server mode | Future | REST endpoints |
| Continuous monitoring | Future | Trend analysis |

---

## 4. Test Results Summary

**Test Run:** 2026-01-29

```
Tests:        32 passed, 0 failed
Duration:     ~2.1s
Coverage:     41% overall
```

### Coverage by Module

| Module | Coverage | Notes |
|--------|----------|-------|
| `core/types.py` | 100% | Excellent |
| `judge/rubric.py` | 100% | Excellent |
| `report/generator.py` | 97% | Excellent |
| `cli/main.py` | 39% | Main entry untested |
| `core/config.py` | 38% | File loading untested |
| `extractors/vision_provider.py` | 24% | API calls mocked |
| `mcp/client.py` | 24% | Requires real browser |
| `core/orchestrator.py` | 20% | Integration-heavy |
| `extractors/modals.py` | 18% | Requires real DOM |
| `extractors/results.py` | 16% | Requires real DOM |
| `extractors/search_box.py` | 14% | Requires real DOM |
| `core/policies.py` | 0% | Untested (rate limiting) |

### Test Organization

```
tests/
├── conftest.py          # Shared fixtures
├── test_cli.py          # 5 tests - query loading, arg parsing
├── test_config.py       # 3 tests - config merging, validation
├── test_extractors.py   # 6 tests - config objects only
├── test_judge.py        # 8 tests - schema, prompts, validation
├── test_report.py       # 6 tests - all report formats
└── test_types.py        # 4 tests - Pydantic model validation
```

---

## 5. Code Quality Results

### Linting (Ruff)
```
Status: PASS
All checks passed!
```

### Formatting (Black)
```
Status: PASS (after fix)
1 file was reformatted: report/generator.py
```

### Type Checking (mypy)
```
Status: 26 errors (non-blocking in CI)

Error Categories:
- no-any-return: 12 errors (returning Any from typed functions)
- union-attr: 8 errors (optional None checks in orchestrator)
- arg-type: 3 errors (MCPBrowserClient | None passed)
- var-annotated: 1 error (missing dict annotation)
- no-untyped-def: 1 error (retry_with_backoff decorator)
```

### Security (Bandit)
```
Issues: 1 Medium
Location: extractors/intelligent_finder.py:71
Issue: B108 - hardcoded temp directory (/tmp/search_detection.png)
CWE: CWE-377
```

---

## 6. Dependencies

### Runtime Dependencies
```
pydantic>=2.0.0          # Type validation
pyyaml>=6.0              # Config parsing
openai>=1.0.0            # OpenAI/OpenRouter API
anthropic>=0.18.0        # Anthropic API (future)
jinja2>=3.1.0            # Templating
aiohttp>=3.9.0           # Async HTTP
python-dotenv>=1.0.0     # .env loading
pillow>=10.0.0           # Image handling
mcp>=0.9.0               # MCP protocol
```

### External Requirements
- Node.js (for chrome-devtools-mcp)
- Chrome/Chromium browser
- GPU (optional, for local vLLM)

---

## 7. Configuration System

### Configuration Priority (highest → lowest)
1. CLI flags (`--top-k`, `--seed`, etc.)
2. Environment variables (`.env`)
3. Site-specific config (`configs/sites/nike.yaml`)
4. Default config (`configs/default.yaml`)

### Key Configuration Sections
```yaml
site:
  url: "https://..."
  search: { input_selectors, submit_strategy }
  results: { item_selectors, title_selectors, price_selectors }
  modals: { close_text_matches, max_auto_clicks }

run:
  top_k: 10
  headless: true
  throttle_rps: 0.5
  seed: 42

llm:
  provider: "openrouter"  # vllm, openai, anthropic
  model: "qwen/qwen-vl-plus"
  temperature: 0.2

report:
  formats: ["md", "html"]
  out_dir: "./runs"
```

---

## 8. LLM Provider Support

| Provider | Judge | Vision | Status |
|----------|-------|--------|--------|
| OpenAI | ✅ | ✅ | Production |
| OpenRouter | ✅ | ✅ | Production |
| vLLM (local) | ✅ | ✅ | Production |
| Anthropic | ❌ | ❌ | Stub only (TODO) |

---

## 9. Output Artifacts

Each audit run produces:
```
runs/{site}/{timestamp}/
├── report.md           # Markdown summary
├── report.html         # Styled HTML report
├── audit.jsonl         # Raw structured data (1 JSON per query)
├── audit.log           # Execution log
├── screenshots/        # Full-page PNGs
└── html_snapshots/     # Raw HTML for traceability
```

---

## 10. Known Issues & Technical Debt

### Critical (Fix Before Production)
1. **No robots.txt compliance** - Could violate site TOS
2. **Hardcoded temp path** - `/tmp/search_detection.png` (security risk)

### High Priority
1. **mypy errors** - 26 type errors (non-blocking but should fix)
2. **No integration tests** - 0% coverage on browser interactions
3. **policies.py untested** - Rate limiting has 0% coverage

### Medium Priority
1. **Anthropic provider** - Only stub implemented
2. **Error recovery** - Limited graceful degradation
3. **Structured logging** - Basic logging only

### Low Priority
1. **Docker deployment** - No container setup
2. **Performance benchmarks** - Not documented
3. **API server mode** - CLI only

---

## 11. Development Commands

```bash
# Install
pip install -e ".[dev]"

# Test
make test              # Run all tests
make test-cov          # With coverage
make test-unit         # Unit tests only

# Code Quality
make lint              # Ruff + Black check
make format            # Auto-format
make typecheck         # mypy

# Run
search-audit --site nike
search-audit --url https://example.com --queries queries.json

# CI locally
make ci                # lint + typecheck + test-cov
```

---

## 12. Recommended Development Priorities

### Phase 1: Production Hardening (Immediate)
| Task | Effort | Impact |
|------|--------|--------|
| Fix mypy type errors (26 errors) | Medium | High |
| Add integration tests for MCP client | High | High |
| Implement robots.txt compliance | Medium | High |
| Fix hardcoded /tmp path | Low | Medium |
| Add tests for core/policies.py | Low | Medium |

### Phase 2: Feature Completion
| Task | Effort | Impact |
|------|--------|--------|
| Implement Anthropic vision provider | Medium | Medium |
| Add E2E tests with real browser | High | High |
| Structured logging (OpenTelemetry) | Medium | Medium |
| Docker containerization | Low | Medium |

### Phase 3: Production Features
| Task | Effort | Impact |
|------|--------|--------|
| LLM-generated queries (P1 roadmap) | High | High |
| API server mode | High | Medium |
| Performance monitoring dashboard | Medium | Medium |
| Multi-language support | High | Low |

---

## 13. Context for Other LLMs

### When Working on This Codebase

1. **Entry Point:** `src/agentic_search_audit/cli/main.py` → `core/orchestrator.py`
2. **Type Safety:** All domain objects in `core/types.py` (Pydantic v2)
3. **Async:** Entire codebase is async/await
4. **Config:** YAML-based with Pydantic validation
5. **Testing:** pytest with asyncio support, fixtures in `conftest.py`

### Important Files to Read First
- `src/agentic_search_audit/core/types.py` - Domain models
- `src/agentic_search_audit/core/orchestrator.py` - Main flow
- `configs/default.yaml` - Configuration schema
- `README.md` - User documentation

### Codebase Patterns
- **Error Handling:** Try/except with logging, graceful degradation
- **Logging:** Python logging module, configurable via CLI
- **Async:** All I/O operations are async
- **Type Hints:** Comprehensive (though mypy has 26 errors)
- **Config:** Pydantic models for validation

---

## 14. Summary Table

| Category | Status | Score |
|----------|--------|-------|
| Architecture | Excellent - modular, async, typed | 9/10 |
| Code Quality | Good - passing lint, some type errors | 7/10 |
| Documentation | Excellent - comprehensive README, guides | 9/10 |
| Testing | Fair - 41% coverage, no integration tests | 6/10 |
| Security | Good - 1 medium issue | 7/10 |
| Maintainability | Excellent - clear structure | 9/10 |
| **Overall** | **Beta Ready** | **7.5/10** |

---

**Conclusion:** This codebase is well-architected and documented, suitable for MVP deployments. Priority improvements: fix type errors, add integration tests, implement robots.txt compliance.
