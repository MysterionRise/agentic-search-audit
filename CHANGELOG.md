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
  selectors are embedded with `json.dumps`. Consent, location-modal and search-box selector
  lists and the challenge checks are probed in one call each (`first_match_js`), which took
  chrome_devtools_mcp from 138 s to 35 s per query on Nike.
- Modal fallbacks are scoped to consent and overlay containers and return objects, so a
  second `dismiss_modals()` on a clean page clicks nothing.
- The bridge transports use the mcp 2.x Python SDK (`mcp>=2.3,<3`): `MCPError`, float
  `read_timeout_seconds`, `CallToolResult.is_error`.
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
- Results scrolling failed every query on current Chrome: `window.scrollBy` and
  `scrollTo` return a Promise since Chrome 155, which `evaluate()` rejects. The scroll
  calls now discard it (`void`). Spike runs never scroll, so only a full audit showed it.
- On macOS the undetected backend reads Chrome's version from its `Info.plist` instead of
  launching Chrome with `--version`. When detection failed, undetected-chromedriver
  fetched the newest stable driver (157), which refuses an older Chrome (156); that
  failure is now logged as a warning.
- Kimi WebBridge opens the run's tab with its first navigation. Opening it on `about:blank`
  timed out with extension 2.0.32, which waits for a load event that page never sends. A
  failed connect now closes its HTTP session.
- Bridge waits (page load, network idle, selector) run again when the page navigates
  underneath them; Boots redirects category searches mid-load. A full-page screenshot that
  Chrome refuses falls back to the viewport.
- eBay and Boots result selectors match their current markup: eBay's `.s-card` listings
  (without the two hidden "Shop on eBay" placeholders) and Boots' `oct-teaser` tiles,
  checked by running the extraction script on the live pages.
- The backend spike reports the chrome-devtools-mcp version `@latest` resolved to, not
  whichever npx cache directory sorted last.
- A bridge tool call that gets no answer now counts as a broken connection, so recovery
  restarts the MCP server. chrome-devtools-mcp runs one call at a time, and reusing the
  server left every later call of the run waiting behind the stuck one.
- The challenge detector recognises edge block pages by their Akamai-style reference ID
  (eBay's "Something went wrong on our end", `edge_block`) and Imperva's
  `/_Incapsula_Resource` iframe (Boots). Both were reported as "no results" before.
- The modal overlay check and close-button finder count only visible overlays that are
  dialogs or float above the page; a class name containing "overlay" is no longer enough
  (Amazon's product images matched). The finder also reads `<input>` buttons and
  `aria-labelledby` text, which dismisses Amazon's delivery-location toaster.
- mypy errors in `jobs/worker.py` and the old MCP client; `tests/api` collection (`httpx`,
  `aiosqlite` declared); the dead `getattr(config, "timeout")` in the judge, experts and
  vision providers; `run.seed` now seeds `random` and reaches the judge; SECURITY.md no longer
  claims crawl-delay is honoured or that the user agent is transparent.
- The challenge detector counts challenge selectors and CAPTCHA iframes only when they are
  rendered. Akamai keeps a hidden `#sec-overlay` on ordinary pages (Gap, Old Navy, Kohl's,
  Lowe's, adidas) and Sephora loads an invisible reCAPTCHA, so audits of those sites
  stopped at a false challenge. Short pages that turn a country away (JCPenney, Gap's
  franchise redirect, Best Buy's country selector) are reported as `geo_block`.

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
