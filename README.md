# Agentic Search Audit

[![CI](https://github.com/MysterionRise/agentic-search-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/MysterionRise/agentic-search-audit/actions/workflows/ci.yml)
[![Python 3.10-3.13](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Runs a set of queries against an e-commerce site's search in a real browser, captures the results
pages, and has an LLM score each query on relevance, diversity, result quality and navigability,
citing the results behind each score. The output is a Markdown and HTML report plus JSONL.

## What it does

- Finds the search box with CSS selectors, falling back to a vision model when selectors fail
- Dismisses cookie and consent dialogs
- Extracts results from the DOM, with site-specific overrides in YAML
- Scores each query with an LLM judge (OpenAI, Anthropic, OpenRouter or a local vLLM server)
  against a fixed rubric
- Saves screenshots and raw HTML for every results page, so each score can be checked

Site configs are included for Nike, Amazon and eBay. In a sample run they extracted 24, 60 and
163 products respectively.

## Quick start

### Prerequisites

- Python 3.10 or higher
- Chromium (installed by Playwright)

### Installation

```bash
git clone https://github.com/MysterionRise/agentic-search-audit.git
cd agentic-search-audit

pip install -e .            # or: pip install -e ".[dev]"
playwright install chromium
```

### Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Choose an LLM provider:

   **vLLM (local, needs a GPU)**
   ```bash
   # see VLLM_SETUP.md for details
   vllm serve llava-hf/llava-v1.6-mistral-7b-hf --port 8000
   ```

   **OpenRouter (cloud, one key for many models)**
   ```bash
   # add to .env:
   OPENROUTER_API_KEY=sk-or-v1-...
   ```

   **OpenAI**
   ```bash
   # add to .env:
   OPENAI_API_KEY=your-api-key-here
   ```

   **Anthropic**
   ```bash
   # add to .env:
   ANTHROPIC_API_KEY=your-api-key-here
   ```

   See [VLLM_SETUP.md](VLLM_SETUP.md) for all providers.

### Run an audit

```bash
# Nike.com with the predefined queries
search-audit --site nike --config configs/sites/nike.yaml

# with a visible browser
search-audit --site nike --no-headless

# with your own queries
search-audit --site https://www.nike.com --queries data/queries/custom.json
```

## Project structure

```
agentic-search-audit/
├── src/agentic_search_audit/    # main package
│   ├── core/                     # orchestrator, types, policies
│   ├── browser/                  # Playwright browser automation
│   ├── extractors/               # DOM parsers and heuristics
│   ├── judge/                    # LLM client and rubric
│   ├── report/                   # report generators
│   └── cli/                      # CLI entrypoint
├── configs/                      # YAML configurations
│   ├── default.yaml             # default settings
│   └── sites/                   # site-specific configs
├── data/queries/                # predefined query sets
├── runs/                        # audit artifacts (gitignored)
└── tests/                       # unit tests
```

## Configuration

See `configs/default.yaml` for all options. The main sections:

- `site`: target URL and locale
- `search`: selectors and strategies for the search box and results
- `modals`: cookie and consent handling
- `run`: top-K results, viewport, headless mode, rate limiting
- `llm`: provider (vllm, openai, anthropic, openrouter), model, temperature, seed
- `report`: output formats and directory

### Vision providers

Search-box detection can use:

- vLLM: local vision models (LLaVA, Qwen-VL and others); needs a GPU
- OpenRouter: hosted Qwen-VL, Claude, GPT-4V and others
- OpenAI: GPT-4o, GPT-4o-mini
- Anthropic: Claude 3.5 Sonnet

Without a GPU, OpenRouter with Qwen-VL-Plus is a reasonable default. See [VLLM_SETUP.md](VLLM_SETUP.md).

## Architecture

```
CLI (cli/main.py)
    ↓
Orchestrator (core/orchestrator.py) - manages audit flow, rate limiting
    ↓
Browser Automation (browser/) - Playwright with stealth mode
    ↓
Extractors (extractors/):
  - search_box.py: finds search input via CSS selectors + vision fallback
  - results.py: parses search results from DOM
  - modals.py: dismisses cookie/consent dialogs
    ↓
Judge (judge/) - LLM evaluation with structured JSON schema
    ↓
Reporter (report/) - Markdown, HTML, JSONL output
```

## Judge rubric

Each query is scored 0 to 5 on:

- **Relevance**: match to user intent
- **Diversity**: coverage of brands, categories and price points
- **Result quality**: clarity, no duplicates, valid links
- **Navigability**: filters, sorting, UI usability
- **Overall**: aggregate user satisfaction

Each score comes with a rationale that cites specific results.

The judge runs with a fixed temperature and seed where the provider supports it. LLM scores can
still vary between runs and between models, so compare runs made with the same model.

## Output

Each run creates a timestamped directory in `runs/`:

- `audit.jsonl`: structured results per query
- `report.md`: Markdown report
- `report.html`: HTML version of the report
- `screenshots/`: full-page screenshot per query
- `html_snapshots/`: raw HTML per results page
- `audit.log`: execution log

## Running it responsibly

- Requests are rate-limited (configurable RPS); keep it low on sites you don't own.
- The browser uses Playwright stealth settings, which reduce bot-detection blocks. Check a site's
  terms of use before auditing it.
- Use an isolated browser profile and don't audit while logged in to real accounts.

## Development

```bash
pip install -e ".[dev]"
make test        # tests
make test-cov    # tests with coverage
make format
make lint
make typecheck
make ci          # all CI checks locally
```

There are 32 unit tests (about 46% line coverage) and CI runs on Python 3.10 to 3.13. See
[TESTING.md](TESTING.md) for details.

## Roadmap

- [x] P0: Nike.com support with predefined queries
- [x] P0: Multi-site support (Amazon, eBay)
- [x] P0: Playwright-based browser automation with stealth mode
- [ ] P1: LLM-generated queries from site content
- [ ] P2: Additional LLM providers (Gemini, local Ollama)
- [ ] P3: Multi-language support
- [ ] P4: Cross-model reliability experiments

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT, see [LICENSE](LICENSE).
