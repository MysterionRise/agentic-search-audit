# Agentic Search Audit

[![CI](https://github.com/MysterionRise/agentic-search-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/MysterionRise/agentic-search-audit/actions/workflows/ci.yml)
[![Python 3.10-3.13](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> AI-powered tool that audits e-commerce search quality using real browser automation and LLM evaluation

<!-- TODO: Add demo GIF here once recorded -->
<!-- ![Demo](docs/demo.gif) -->

## Why This Tool?

E-commerce search quality directly impacts conversion rates and user satisfaction. This tool provides:

- **Automated Quality Audits**: Run reproducible search quality assessments across your site
- **LLM-Powered Analysis**: Get structured, explainable scores with evidence-backed rationale
- **Real Browser Testing**: Test actual user experience with Playwright stealth mode
- **Multi-Site Support**: Configure once, audit multiple e-commerce platforms

## Tested Sites

| Site | Status | Products Found |
|------|--------|----------------|
| Nike | ✅ Working | 24 |
| Amazon | ✅ Working | 60 |
| eBay | ✅ Working | 163 |

## Features

- **Browser Automation**: Playwright with stealth mode for realistic browser interactions
- **LLM-as-a-Judge**: Structured evaluation with reproducible scores (OpenAI, Anthropic, OpenRouter, vLLM)
- **Vision-Based Detection**: Intelligent search box detection using vision models
- **Rich Reports**: Generates Markdown, HTML, and JSONL reports with screenshots
- **Configurable**: YAML-based configuration with site-specific overrides
- **Deterministic**: Seed-based reproducibility for LLM judgements
- **Smart Extraction**: Heuristics-based DOM parsing with fallbacks
- **Local or Cloud**: Use local vLLM models or cloud APIs

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Chrome/Chromium browser (Playwright will manage this)

### Installation

```bash
# Clone the repository
git clone https://github.com/MysterionRise/agentic-search-audit.git
cd agentic-search-audit

# Install Python dependencies
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium
```

### Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. **Choose your LLM provider:**

   **Option A: Use vLLM (local, free, private)**
   ```bash
   # Start vLLM server (see VLLM_SETUP.md for details)
   vllm serve llava-hf/llava-v1.6-mistral-7b-hf --port 8000
   ```

   **Option B: Use OpenRouter (cloud, cheap, easy)**
   ```bash
   # Add to .env:
   OPENROUTER_API_KEY=sk-or-v1-...
   ```

   **Option C: Use OpenAI (cloud)**
   ```bash
   # Add to .env:
   OPENAI_API_KEY=your-api-key-here
   ```

   **Option D: Use Anthropic (cloud)**
   ```bash
   # Add to .env:
   ANTHROPIC_API_KEY=your-api-key-here
   ```

   See [VLLM_SETUP.md](VLLM_SETUP.md) for detailed configuration of all providers.

### Run Your First Audit

```bash
# Run audit on Nike.com with predefined queries
search-audit --site nike --config configs/sites/nike.yaml

# Run with visible browser (non-headless)
search-audit --site nike --no-headless

# Run with custom queries
search-audit --site https://www.nike.com --queries data/queries/custom.json
```

## Project Structure

```
agentic-search-audit/
├── src/agentic_search_audit/    # Main package
│   ├── core/                     # Orchestrator, types, policies
│   ├── browser/                  # Playwright browser automation
│   ├── extractors/               # DOM parsers & heuristics
│   ├── judge/                    # LLM client & rubric
│   ├── report/                   # Report generators
│   └── cli/                      # CLI entrypoint
├── configs/                      # YAML configurations
│   ├── default.yaml             # Default settings
│   └── sites/                   # Site-specific configs
├── data/queries/                # Predefined query sets
├── runs/                        # Audit artifacts (gitignored)
└── tests/                       # Unit tests
```

## Configuration

See `configs/default.yaml` for all available options. Key settings:

- **site**: Target URL and locale
- **search**: Selectors and strategies for search box and results
- **modals**: Cookie/consent handling
- **run**: Top-K results, viewport, headless mode, rate limiting
- **llm**: Provider (vllm/openai/anthropic/openrouter), model, temperature, seed
- **report**: Output formats and directory

### Vision Provider Configuration

The intelligent search box detection supports multiple vision providers:

- **vLLM**: Local vision models (LLaVA, Qwen-VL, etc.) - Free, private, GPU required
- **OpenRouter**: Cloud API gateway (Qwen-VL, Claude, GPT-4V, etc.) - Cheap, easy, no GPU needed
- **OpenAI**: GPT-4o, GPT-4o-mini - Direct API, cloud-based
- **Anthropic**: Claude 3.5 Sonnet - Direct API, cloud-based

**Recommended for most users**: OpenRouter with Qwen-VL-Plus (best value, excellent quality)

See [VLLM_SETUP.md](VLLM_SETUP.md) for detailed setup instructions.

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

## LLM-as-a-Judge Rubric

The judge evaluates searches on:

- **Relevance**: Match to user intent (0-5)
- **Diversity**: Coverage of brands, categories, price points (0-5)
- **Result Quality**: Clarity, no duplicates, valid links (0-5)
- **Navigability**: Filters, sorting, UI usability (0-5)
- **Overall**: Aggregate user satisfaction score (0-5)

Each score includes rationale and evidence citing specific results.

## Output

Each audit run creates a timestamped directory in `runs/` containing:

- `audit.jsonl`: Structured results for each query
- `report.md`: Human-readable Markdown report
- `report.html`: HTML version of the report
- `screenshots/`: Full-page screenshots for each query
- `html_snapshots/`: Raw HTML for each results page
- `audit.log`: Detailed execution log

## Security & Compliance

- **Rate Limiting**: Configurable RPS to avoid overloading sites
- **Stealth Mode**: Playwright stealth to avoid bot detection
- **Data Privacy**: Use isolated browser profiles, avoid sensitive data

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
make test

# Run tests with coverage
make test-cov

# Format code
make format

# Lint
make lint

# Type check
make typecheck

# Run all CI checks locally
make ci
```

See [TESTING.md](TESTING.md) for detailed testing guide.

### Testing

The project has comprehensive test coverage (46%+):
- **32 unit tests** covering core types, config, judge, extractors, reports, and CLI
- **CI/CD** with GitHub Actions testing on Python 3.10, 3.11, 3.12, 3.13
- **Pre-commit hooks** for code quality

## Roadmap

- [x] P0: Nike.com support with predefined queries
- [x] P0: Multi-site support (Amazon, eBay)
- [x] P0: Playwright-based browser automation with stealth mode
- [ ] P1: LLM-generated queries from site content
- [ ] P2: Additional LLM providers (Gemini, local Ollama)
- [ ] P3: Multi-language support
- [ ] P4: Cross-model reliability experiments

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.
