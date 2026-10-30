# Architecture

## Pipeline

```
cli/main.py
  └─ load_config(config_path, site_config_path, overrides)      core/config.py
       default.yaml (unless --config) ◄ configs/sites/<site>.yaml ◄ CLI overrides
  └─ run_audit() ─► SearchAuditOrchestrator(config, queries, run_dir, client=|client_factory=)
       _init_components(): judge, reporter, compliance, rate limiter, extractors (once)
       _check_compliance(): robots.txt for the site URL
       for each query:
         _run_query_with_retries(query, index)
           _prepare_browser_for_query: BrowserSession.ensure_alive / rotate_for_query,
                                       _navigate_to_site only when needed
           _capture_query (under query_time_budget_s):
               modals ─► search_url_template or SearchBoxFinder.submit_search
               ─► detect_challenge ─► check_for_no_results ─► _scroll_for_results
               ─► ResultsExtractor.extract_results (vision fallback) ─► PdpAnalyzer
               ─► _capture_artifacts (screenshot, HTML)
           _judge_query: SearchQualityJudge.evaluate ─► AuditRecord ─► audit.jsonl
           on failure: _recover_after_failure, backoff; QueryFailure ─► failures.jsonl
       ExpertPanel ─► ReportGenerator (maturity, findings, md/html/json/csv/pdf)
```

## Browser layer

`BrowserClient` (`core/types.py`) is a `Protocol`; the orchestrator and extractors only
use it. Implementations:

| Client | Launches | Notes |
|---|---|---|
| `PlaywrightBrowserClient` | Playwright Chromium | stealth JS plus playwright-stealth, random UA and timezone |
| `UndetectedBrowserClient` | Chrome via undetected-chromedriver (Selenium) | for Akamai / PerimeterX / DataDome sites |
| `CDPBrowserClient` | attaches over CDP | external Chrome or Browserbase |
| `BridgeBrowserClient` | attaches through a bridge | one class over `BridgeTransport`: `ChromeDevtoolsMcpTransport`, `KimiWebBridgeTransport`, `PlaywrightMcpTransport` |

`browser/_js.py` gives every backend the same `evaluate()` contract: the expression runs
inside an IIFE that returns a JSON envelope, decoded to a `JsValue`; script errors raise
`BrowserScriptError`. `browser/errors.py` classifies exceptions into `BrowserErrorKind`
for the retry loop.

`browser/bridge/`: a transport provides `open`, `close`, `navigate`, `evaluate`,
`press_key`, `screenshot`, `set_viewport`, `new_tab`, `snapshot` and the identity mutations;
`BridgeBrowserClient` builds the rest from JavaScript (`bridge/js.py`), with waits running
inside the page as one call each. `mcp_base.py` holds the stdio MCP plumbing. See
docs/BROWSER_BACKENDS.md.

`BrowserCapabilities` (declared on each client) tells `BrowserSession` (`browser/session.py`)
what it may do: user-agent rotation (`run.ua_rotation_strategy`), proxy rotation, periodic
cookie clearing. Bridges on a real profile report all three as off.

## Extractors

- `modals.py`: known consent selectors, consent-platform APIs (OneTrust, Didomi, Usercentrics,
  Axeptio, Iubenda), text and shadow-DOM fallbacks scoped to consent containers, iframe
  consent, location dialogs, close buttons inside visible overlays, Escape as last resort.
- `search_box.py`: CSS selectors, optional trigger click for overlay search UIs, overlay
  removal, vision fallback (`intelligent_finder.py` + `vision_provider.py`), submit by Enter
  or button.
- `results.py`: `EXTRACT_RESULTS_JS` returns the top-K items with title, URL, snippet, price
  and image in one `evaluate`; `vision_results.py` reads a full-page screenshot instead and
  enriches URLs from the DOM; `pdp_analyzer.py` visits product pages.

## Judge and analysis

`judge/judge.py` scores five dimensions (query understanding, results relevance, result
presentation, advanced features, error handling) into the FQI (`core/types.py`), with
intent-aware guidance (`intent_classifier.py`) and provider clients for OpenAI, OpenRouter,
vLLM and Anthropic. `experts.py` adds two site-level personas. `analysis/` derives the
maturity level, benchmark position and findings; `report/` renders them.

## Configuration

Pydantic models in `core/types.py`. `RunConfig`, `BridgeConfig` and the site models reject
unknown keys. Time budgets: `run.browser_budget_s` plus two vision calls plus PDP visits,
or `run.query_timeout_s` when set (`query_time_budget_s()`).

## Experimental SaaS layer

`api/` (FastAPI), `jobs/` (Redis queue worker) and `db/` (SQLAlchemy, Alembic) run the same
orchestrator as a hosted service. They are behind the `saas` extra and documented, with
their known gaps, in docs/SAAS.md.
