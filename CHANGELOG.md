# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Bridge backends that drive a real, already-running Chrome: `chrome_devtools_mcp`
  (Google's chrome-devtools-mcp; modes autoconnect, browser_url, launch), `kimi_webbridge`
  (Moonshot's local daemon) and an experimental `playwright_mcp`, behind one
  `BridgeBrowserClient` (`browser/bridge/`). `run.bridge` settings and the CLI flags
  `--bridge-mode`, `--browser-url`, `--bridge-session`, `--allow-profile-mutations`.
- `BrowserCapabilities` on every backend and `BrowserSession`, which skips user-agent
  rotation, proxy switching and cookie clearing where a backend cannot or should not do them.
- `failures.jsonl` and a Failed Queries table in every report for queries that produced no
  record (challenge, timeout, submit failure, judge error).
- Explicit time budgets: `run.query_timeout_s`, `run.browser_budget_s`, `llm.timeout`,
  `llm.vision_timeout`, `llm.max_concurrent`, `llm.min_request_interval_s`;
  `run.ua_rotation_strategy` (default per-site).
- `scripts/backend_spike.py` and docs/BROWSER_BACKENDS.md to measure the backends on the
  configured sites; docs/ARCHITECTURE.md; docs/SAAS.md.
- `saas` optional extra for the experimental API/worker/database layer; `uv.lock`,
  `.python-version` (3.12), `.nvmrc` (24), `make bootstrap`, `make audit-deps`, Dependabot
  configuration; `browser` and `integration` test markers; Alembic merge revision
  7d2e4f1a9c3b (single head).

### Changed
- `BrowserClient.evaluate` returns the JSON-decoded JavaScript value on every backend
  (`JsValue`) and raises `BrowserScriptError` for script failures. The extractors compared
  stringified results before, which silently disabled the consent fallbacks, the close-button
  finder and PDP dropdown probing on every real backend.
- Results are extracted in one `evaluate` round trip instead of one per field per item;
  selectors are embedded with `json.dumps`.
- Modal fallbacks are scoped to consent and overlay containers and return objects, so a
  second `dismiss_modals()` on a clean page clicks nothing.
- The orchestrator accepts an injected client, builds its extractors once, runs the first
  navigation inside the retry loop (a challenge there is retried instead of aborting the run),
  and runs the judge outside the browser time budget. Timeouts and submit failures are retried.
- Site config models reject unknown keys; `search.intelligent_detection_model` is a real key.
- Tool versions are pinned once in `pyproject.toml`; CI runs through uv with `pip-audit`
  instead of the deprecated `safety check`; playwright-stealth 2.x; `mcp` pinned below 2.
- One multi-stage Dockerfile (targets `cli` and `saas`) with Playwright Chromium replaces
  three Dockerfiles that installed a non-existent `setup.py`, Node and a wrongly named npm
  package.
- README, QUICKSTART, CLAUDE.md, TESTING, CONTRIBUTING, SECURITY, DEMO_RUNBOOK, VLLM_SETUP
  and docs/INTELLIGENT_DETECTION.md describe the code as it is (FQI rubric, six backends,
  43 site configs, uv workflow).

### Removed
- The dead `mcp/` package (replaced by `browser/bridge/mcp_base.py`), `requirements.txt`,
  `requirements-dev.txt`, `Dockerfile.api`, `Dockerfile.worker`, and the stale documents
  CI_TESTING_SUMMARY.md, PROJECT_SUMMARY.md, CODE_REFERENCES.md, LLM_DETECTION_ANALYSIS.md
  and docs/GAP_ANALYSIS.md. Unused dependencies `jinja2` and `pillow`.

### Fixed
- mypy errors in `jobs/worker.py` and the old MCP client; `tests/api` collection (`httpx`,
  `aiosqlite` declared); the dead `getattr(config, "timeout")` in the judge, experts and
  vision providers; `run.seed` now seeds `random` and reaches the judge; SECURITY.md no longer
  claims crawl-delay is honoured or that the user agent is transparent.

## [0.1.0] - 2024-11-14

### Added

- Initial MVP release
- MCP-based browser automation via chrome-devtools-mcp
- Search box detection and interaction
- Results extraction with heuristics-based DOM parsing
- Modal/popup handling
- LLM-as-a-judge evaluation system
- Structured scoring rubric (0-5 scale)
- Markdown and HTML report generation
- JSONL audit logs
- CLI interface with argparse
- Nike.com example configuration and queries
- Rate limiting and retry logic
- Deterministic mode with seed support
- Full-page screenshots
- HTML snapshots for traceability
- Configuration system with YAML
- Site-specific config overrides
- Unit tests for core types and config
- Comprehensive documentation

### Features

- **P0 Requirements Met**:
  - ✅ Works with Nike.com and 10 English queries
  - ✅ Opens Chrome via chrome-devtools-mcp (headless by default)
  - ✅ Locates search box, submits queries, waits for results
  - ✅ Extracts top-K results with metadata
  - ✅ Screenshots and HTML snapshots
  - ✅ LLM judge with structured rubric
  - ✅ JSONL audit and Markdown/HTML reports
  - ✅ Deterministic mode with --seed
  - ✅ End-to-end execution without manual intervention

### Known Limitations

- OpenAI only (multi-LLM support planned)
- English only (i18n planned)
- No robots.txt checking yet
- No LLM-generated queries yet (P1 feature)
