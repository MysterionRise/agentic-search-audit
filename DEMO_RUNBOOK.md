# Demo Runbook — Agentic Search Audit

Quick guide for presenting a live demo of the search quality audit tool.

## Prerequisites

- **Python 3.11+** installed
- **Google Chrome** installed (latest stable)
- **pip install -e ".[dev]"** completed
- **OPENROUTER_API_KEY** exported in your shell

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
```

## Quick Start (single site)

```bash
search-audit --site amazon --max-queries 5 --no-headless
```

This runs 5 queries against Amazon with a visible browser. Takes ~3 minutes.

## Full Demo (3 sites)

```bash
./scripts/demo.sh
```

Runs Amazon, Target, and Best Buy sequentially (5 queries each). Takes ~10 minutes total.

## Recommended Demo Flow (~12 min)

| Time   | Action |
|--------|--------|
| 0:00   | Explain the tool's purpose: automated search quality auditing |
| 1:00   | Show a site config (e.g., `configs/sites/amazon.yaml`) |
| 2:00   | Start single-site audit: `search-audit --site amazon --max-queries 3 --no-headless` |
| 2:30   | While browser runs, explain the FQI scoring model (5 dimensions) |
| 5:00   | Audit completes — open the HTML report |
| 5:30   | Walk through: FQI hero score, radar chart, band distribution |
| 7:00   | Drill into individual query cards (verdict bar, dimension scores) |
| 8:00   | Show findings section and maturity assessment |
| 9:00   | Mention coverage: 35+ retailer configs ready to go |
| 10:00  | Show the config system: YAML + query JSON |
| 11:00  | Q&A |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot detection / CAPTCHA | Switch to a different site (`--site sephora` or `--site asos`) |
| API timeout | The tool auto-falls back to score=0 and continues. Mention this is by design. |
| Browser won't start | Ensure Chrome is installed. Try `--browser playwright` as fallback. |
| No results extracted | CSS selectors may have changed. Use pre-generated reports as backup. |
| `search-audit` not found | Run `pip install -e ".[dev]"` from project root. |
| `OPENROUTER_API_KEY` error | Export the key: `export OPENROUTER_API_KEY=sk-or-...` |

## Backup Plan

If live demo fails, use pre-generated reports from a previous run:
1. Keep a `runs/demo-backup/` directory with known-good reports
2. Open `runs/demo-backup/amazon/report.html` directly

## Demo-Safe Sites

**Best for demo** (use `search_url_template`, skip fragile search-box detection):
- Amazon, Target, Best Buy, Sephora, Walmart

**Avoid in live demo** (rely on search-box detection, more fragile):
- Nike, Zalando, Zara, H&M
