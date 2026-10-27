# Quick start

## 1. Install

Python 3.10 or newer. With [uv](https://docs.astral.sh/uv/) (recommended):

```bash
git clone https://github.com/MysterionRise/agentic-search-audit.git
cd agentic-search-audit
make bootstrap
```

`make bootstrap` runs `uv sync` with the `dev`, `saas` and `undetected` extras, installs
Playwright's Chromium and the git hooks. Without uv:

```bash
pip install -e ".[dev,undetected]"
playwright install chromium
```

Prefix commands with `uv run` when using uv (or activate `.venv`).

## 2. Choose an LLM provider

```bash
cp .env.example .env
```

The shipped site configs use OpenRouter, so add `OPENROUTER_API_KEY`. `OPENAI_API_KEY`
and `ANTHROPIC_API_KEY` work for configs that select those providers, and
`configs/default.yaml` points at a local vLLM server. [VLLM_SETUP.md](VLLM_SETUP.md)
covers every provider and the vision models used for search-box detection.

## 3. Run an audit

```bash
uv run search-audit --site nike --max-queries 3          # quick check, headless
uv run search-audit --site nike --no-headless            # watch the browser
uv run search-audit --site amazon --browser undetected   # a backend that gets past Akamai
uv run search-audit --site nike --top-k 20 --pdp         # more results, visit product pages
uv run search-audit --site nike --output runs/nike-today # choose the output directory
uv run search-audit --site nike --resume                 # continue the latest run
```

Run from the repository root: `--site NAME` resolves `configs/sites/NAME.yaml` and
`data/queries/NAME.json` relative to the current directory. Sites without a query file
(asos, carrefour, decathlon, douglas, fnac, hm, ikea, laredoute, marksandspencer,
mediamarkt, otto, primark, sephora-uk, zara) need `--queries`, for example
`--queries data/queries/queries_de.json`.

Other flags: `--url` for an ad-hoc site with the default config, `--config` to replace
`configs/default.yaml`, `--seed`, `--vision` (vision-first extraction), `--pdf`,
`--log-level DEBUG`, `--ignore-robots`, `--auto-generate [--dry-run]` to generate queries
from the homepage, `--compare SITE_A SITE_B` for a side-by-side run.

## 4. Read the results

```bash
ls runs/www.nike.com/<timestamp>/
open runs/www.nike.com/<timestamp>/report.html
```

`report.md` and `report.html` carry the FQI per query, the site's maturity level, findings
and expert commentary; `audit.jsonl` has every record; `failures.jsonl` lists queries that
produced no record and why; `screenshots/` and `html_snapshots/` back each score.

## 5. Run in your own Chrome (bridge backends)

The launched backends start a fresh browser. On sites that block them, or when a logged-in
session is needed, drive the Chrome you already have open:

**chrome-devtools-mcp** (Google's MCP server; needs Node 20.19+, `nvm use 24`):

1. Chrome 144 or newer: open `chrome://inspect/#remote-debugging` and enable remote
   debugging for the profile (once).
2. `uv run search-audit --site nike --browser chrome_devtools_mcp`, then click "Allow" in
   the Chrome dialog within 60 seconds.

Alternatives: `--bridge-mode launch` lets the server start its own Chrome (no user action);
`--browser-url http://127.0.0.1:9222` attaches to a Chrome you started with
`--remote-debugging-port=9222 --user-data-dir=<non-default dir>`.

**Kimi WebBridge** (Moonshot's local daemon plus extension):

1. Install from <https://www.kimi.com/features/webbridge> and add its Chrome extension.
2. `~/.kimi-webbridge/bin/kimi-webbridge start`
3. `uv run search-audit --site nike --browser kimi_webbridge`

On a real profile the audit opens one tab, works only there, and never rotates identity or
clears cookies. [docs/BROWSER_BACKENDS.md](docs/BROWSER_BACKENDS.md) compares the backends.

## 6. Add a site

Copy `examples/custom_site.yaml` to `configs/sites/<name>.yaml`, set the URL, selectors
and, if the site has one, `search_url_template` (skips search-box detection entirely). Add
`data/queries/<name>.json` (a list of strings, or `{"queries": [...]}`). Unknown keys are
rejected, so typos surface at load time.

## Common issues

- **`OPENROUTER_API_KEY environment variable not set`**: put the key in `.env` or export it.
- **No search box found**: add selectors under `site.search.input_selectors`, set a
  `search_url_template`, or run with `--no-headless` to see what the page shows.
- **Challenge persists / blocked**: try `--browser undetected`, then a bridge backend.
- **`node ... is older than 20.19.0`**: `nvm use 24` (the repo has an `.nvmrc`).
- **Kimi WebBridge daemon is not running**: start it as above; make sure the extension is
  installed in the Chrome that is open.
