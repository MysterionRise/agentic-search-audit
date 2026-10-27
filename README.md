# Agentic Search Audit

[![CI](https://github.com/MysterionRise/agentic-search-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/MysterionRise/agentic-search-audit/actions/workflows/ci.yml)
[![Python 3.10-3.13](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Runs a set of queries against an e-commerce site's search in a real browser, captures each
results page, and has an LLM score every query on a fixed rubric, citing the results behind
each score. The output is a Markdown and HTML report, a JSONL record per query, and the
screenshots and HTML that back them.

## What it does

- Drives a browser through one of six backends: Playwright, undetected-chromedriver, an
  external Chrome over CDP, or a *bridge* into the Chrome you already have open
  (chrome-devtools-mcp, Kimi WebBridge, Playwright MCP). See
  [docs/BROWSER_BACKENDS.md](docs/BROWSER_BACKENDS.md).
- Dismisses cookie, consent and location dialogs; finds the search box with CSS selectors,
  falling back to a vision model; or navigates straight to a site's search URL template.
- Extracts the top results from the DOM in one round trip, with a vision fallback, and can
  click into product pages (`--pdp`).
- Scores each query with an LLM judge (OpenAI, Anthropic, OpenRouter or a local vLLM
  server) on five dimensions combined into the Findability Quality Index (FQI), then adds
  site-level maturity, findings and expert commentary.
- Records queries that produced no result (bot challenge, timeout, submit failure) in
  `failures.jsonl` and in the report instead of dropping them silently.

43 site configs ship under `configs/sites/`, 29 of them with a query set under
`data/queries/`.

## Quick start

Requirements: Python 3.10 or newer and [uv](https://docs.astral.sh/uv/). `pip install -e
".[dev]"` works too, without the lock file.

```bash
git clone https://github.com/MysterionRise/agentic-search-audit.git
cd agentic-search-audit
make bootstrap                  # uv sync with the dev, saas and undetected extras,
                                # Playwright Chromium, git hooks
cp .env.example .env            # add OPENROUTER_API_KEY (or OPENAI_API_KEY / ANTHROPIC_API_KEY)

uv run search-audit --site nike --max-queries 3            # three queries, headless
uv run search-audit --site nike --no-headless              # watch the browser
uv run search-audit --url https://www.example.com --queries examples/custom_queries.json
uv run search-audit --site nike --browser chrome_devtools_mcp   # in your own Chrome
```

Run from the repository root: `--site nike` resolves `configs/sites/nike.yaml` and
`data/queries/nike.json` relative to the current directory. Sites without a query file need
`--queries`. The site configs use OpenRouter by default; `configs/default.yaml` uses a local
vLLM server. See [QUICKSTART.md](QUICKSTART.md) for the walkthrough and
[VLLM_SETUP.md](VLLM_SETUP.md) for every provider.

## How it works

```
cli/main.py ─► load_config (default.yaml ◄ site yaml ◄ CLI flags)
            ─► SearchAuditOrchestrator (core/orchestrator.py)
                 ├─ BrowserClient via create_browser_client (browser/, browser/bridge/)
                 ├─ BrowserSession: identity rotation and recovery, gated by capabilities
                 ├─ per query, under a time budget: modals ─► search ─► results ─► artifacts
                 ├─ judge/: SearchQualityJudge (FQI), IntentClassifier, ExpertPanel
                 ├─ analysis/: maturity, benchmarks, findings
                 └─ report/: Markdown, HTML, JSON, CSV, optional PDF
```

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) has the detail.

## Judge rubric

Each query is scored 0 to 5 on `query_understanding`, `results_relevance`,
`result_presentation`, `advanced_features` and `error_handling`. The weighted average
(0.25 / 0.25 / 0.20 / 0.20 / 0.10) is the FQI, capped at 3.5 when understanding or relevance
falls below 2, and mapped to the bands Excellent, Good, Weak, Critical and Broken. Every
score comes with a rationale that cites specific results.

The judge runs with a fixed temperature and seed where the provider supports it. LLM scores
still vary between runs and models, so compare runs made with the same model.

## Configuration

`configs/default.yaml` lists every option. `--config FILE` *replaces* the defaults with
that file; `--site NAME` deep-merges `configs/sites/NAME.yaml` on top; CLI flags win. The
sections:

- `site`: URL, locale, `search` (selectors, submit strategy, `search_url_template`,
  vision fallback), `results` (item and field selectors), `modals` (consent and location
  dialogs)
- `run`: `browser_backend` and `bridge` settings, top-K, viewport, waits, rate limit,
  retries, time budgets, scrolling, PDP analysis, proxies, identity rotation
- `llm`: provider, model, temperature, timeouts, concurrency
- `report`: formats and output directory
- `compliance`: robots.txt handling

Unknown keys are rejected. `examples/custom_site.yaml` is a complete template.

## Output

Each run writes `runs/<host>/<timestamp>/`:

- `audit.jsonl`: one record per scored query (also the resume checkpoint)
- `failures.jsonl`: queries that produced no record, with the reason
- `report.md`, `report.html`, and `audit.json` when `json` is in `report.formats`
- `findings.csv`: critical and high findings
- `screenshots/` and `html_snapshots/`: full-page screenshot and raw HTML per query
- `report.pdf` with `--pdf` (needs the `pdf` extra)

`--resume` continues the latest run for the site; failed queries are retried.

## Running it responsibly

- Requests are rate-limited (`run.throttle_rps`) and robots.txt is respected unless you
  pass `--ignore-robots`. Keep rates low on sites you do not own and check their terms.
- The launched backends rotate spoofed Chrome user agents and apply stealth patches to
  reduce bot-detection blocks. The bridge backends drive your real, logged-in Chrome and
  never rotate identity, clear cookies or close your tabs; review `runs/` before sharing
  screenshots of a logged-in session.
- The Kimi WebBridge daemon reports usage to its vendor; see docs/BROWSER_BACKENDS.md.

## Development

```bash
make test        # unit tests (uv run pytest tests/)
make test-cov    # with coverage
make lint        # ruff and black
make typecheck   # mypy
make ci          # lint, types, tests, pip-audit
uv lock          # after editing dependencies in pyproject.toml
```

Tests marked `browser` need Playwright's Chromium and skip without it; `integration`
tests are opt-in (`ASA_BRIDGE_INTEGRATION=1`). See [TESTING.md](TESTING.md) and
[CONTRIBUTING.md](CONTRIBUTING.md).

The `api/`, `jobs/` and `db/` packages are an experimental hosted layer behind the `saas`
extra; see [docs/SAAS.md](docs/SAAS.md).

## License

MIT, see [LICENSE](LICENSE).
