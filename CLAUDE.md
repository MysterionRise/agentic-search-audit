# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

Agentic Search Audit runs search queries against e-commerce sites in a real browser,
extracts the results, and scores them with an LLM judge (the Findability Quality Index).
Python 3.10+, `src/agentic_search_audit`, managed with uv.

## Commands

```bash
make bootstrap                       # one-time: uv sync (dev, saas, undetected), Chromium, hooks
uv run pytest tests/                 # all tests that run locally (browser tests need Chromium)
uv run pytest tests/ -m "not browser and not integration"   # what CI runs
uv run pytest tests/test_config.py   # one file
make lint && make typecheck          # ruff, black --check, mypy src/
make ci                              # lint, types, tests with coverage, pip-audit
uv lock                              # after changing dependencies in pyproject.toml

uv run search-audit --site nike --max-queries 3 --no-headless
uv run search-audit --url https://example.com --queries examples/custom_queries.json
uv run search-audit --site nike --browser chrome_devtools_mcp      # bridge into real Chrome
uv run python scripts/backend_spike.py --sites nike --backends playwright --queries 1
```

Run from the repository root: `--site NAME` and query paths resolve relative to the CWD.

## Architecture

```
cli/main.py ─► core/config.load_config ─► core/orchestrator.SearchAuditOrchestrator
   browser/   : BrowserClient protocol (core/types.py); playwright_client, undetected_client,
                cdp_client; bridge/ (BridgeBrowserClient over BridgeTransport:
                chrome_devtools_mcp, kimi_webbridge, playwright_mcp); session.BrowserSession
                (identity rotation and recovery gated by BrowserCapabilities); _js.py
                (the evaluate() envelope every backend uses)
   extractors/: modals, search_box (+ intelligent_finder, vision_provider), results
                (one EXTRACT_RESULTS_JS round trip), vision_results, pdp_analyzer
   judge/     : judge (FQI rubric), intent_classifier, experts, rate_limiter
   analysis/  : maturity, benchmarks, uplift_planner (findings)
   report/    : generator (md/html/json/csv/pdf), comparison_report
   api/ jobs/ db/ : experimental SaaS layer behind the `saas` extra (docs/SAAS.md)
```

Per query the orchestrator runs `_prepare_browser_for_query` (recover, rotate, load the
site only when needed), `_capture_query` under a time budget (modals, search or URL
template, challenge check, scroll, extraction, PDP, artifacts), then `_judge_query`.
Failures become `QueryFailure` rows in `failures.jsonl`.

## Contracts worth knowing

- `BrowserClient.evaluate(expr)` returns the JSON-decoded JS value (`JsValue`), never a
  stringified repr; script errors raise `BrowserScriptError`. Consumers narrow with
  `isinstance`. Embed selectors with `json.dumps`.
- Backends declare `BrowserCapabilities`; bridges on a real profile report no UA override,
  proxy or cookie clearing, and the orchestrator skips those steps.
- Batch page probes: one `evaluate` per decision (`first_match_js()` for selector lists,
  one script for a whole result list). A bridge tool call costs about 0.7 s, so a loop of
  `query_selector` calls is unusable there.
- Site config models (`SearchConfig`, `ResultsConfig`, `ModalsConfig`, `LocationConfig`,
  `SiteConfig`, `RunConfig`, `BridgeConfig`) reject unknown keys.
- `load_config()` loads `configs/default.yaml` only when `--config` is not given; `--config`
  replaces it. 14 site configs have no query file and need `--queries`.

## Tests

`asyncio_mode = "auto"`, `filterwarnings = error`. Markers: `unit`, `browser` (launches
Playwright Chromium, auto-skips without it), `integration` (opt-in,
`ASA_BRIDGE_INTEGRATION=1`). SaaS tests skip unless the `saas` extra is installed. CI runs
the matrix on 3.10 to 3.13 with `-m "not browser and not integration"`.

## Style

black (100 columns), ruff (E, F, I, N, W, UP), mypy with `disallow_untyped_defs`. Tool
versions are pinned once in `pyproject.toml` (`dev` extra); pre-commit, the Makefile and
CI run them through `uv run`.
