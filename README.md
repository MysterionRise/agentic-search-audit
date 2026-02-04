# Agentic Search Audit

[![CI](https://github.com/MysterionRise/agentic-search-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/MysterionRise/agentic-search-audit/actions/workflows/ci.yml)
[![Python 3.10-3.13](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Open-source tool for evaluating on-site search quality using browser automation and LLM-as-a-judge.

## Overview

Agentic Search Audit opens a real browser via `chrome-devtools-mcp`, runs on-site searches (e.g., nike.com), extracts the top results, and uses an LLM judge to score search quality. It supports both predefined query sets and LLM-generated queries from site content.

## Features

- 🌐 **Browser Automation**: Uses chrome-devtools-mcp for real Chrome interactions
- 🤖 **LLM-as-a-Judge**: Structured evaluation with reproducible scores
- 👁️ **Vision-Based Detection**: Intelligent search box detection using vLLM, OpenRouter, or OpenAI vision models
- 📊 **Rich Reports**: Generates Markdown and HTML reports with screenshots
- 🔧 **Configurable**: YAML-based configuration with site-specific overrides
- 🎯 **Deterministic**: Seed-based reproducibility for LLM judgements
- 🔍 **Smart Extraction**: Heuristics-based DOM parsing with fallbacks
- 🏠 **Local or Cloud**: Use local vLLM models or cloud APIs (OpenAI, Anthropic)

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Node.js (for chrome-devtools-mcp)
- Chrome/Chromium browser

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/agentic-search-audit.git
cd agentic-search-audit

# Install Python dependencies
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

### Setup MCP Server

```bash
# Install chrome-devtools-mcp globally
npx chrome-devtools-mcp@latest

# Or configure it in Claude Code
claude mcp add chrome-devtools npx chrome-devtools-mcp@latest
```

### Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. **Choose your vision provider:**

   **Option A: Use vLLM (local, free, private)**
   ```bash
   # Start vLLM server (see VLLM_SETUP.md for details)
   vllm serve llava-hf/llava-v1.6-mistral-7b-hf --port 8000

   # No API key needed for local vLLM!
   # Config already set to use vLLM in configs/default.yaml
   ```

   **Option B: Use OpenRouter (cloud, cheap, easy)**
   ```bash
   # Add to .env:
   OPENROUTER_API_KEY=sk-or-v1-...

   # Update configs/default.yaml or use configs/openrouter-example.yaml:
   # provider: "openrouter"
   # model: "qwen/qwen-vl-plus"
   ```

   **Option C: Use OpenAI (cloud, paid)**
   ```bash
   # Add to .env:
   OPENAI_API_KEY=your-api-key-here

   # Update configs/default.yaml:
   # provider: "openai"
   # model: "gpt-4o-mini"
   ```

   See [VLLM_SETUP.md](VLLM_SETUP.md) for detailed configuration of all providers.

### Run Your First Audit

```bash
# Run audit on Nike.com with predefined queries
search-audit --site nike --config configs/sites/nike.yaml

# Run with custom queries
search-audit --site https://www.nike.com --queries data/queries/custom.json

# Enable headless mode (default) or headed
search-audit --site nike --headless false
```

## Project Structure

```
agentic-search-audit/
├── src/agentic_search_audit/    # Main package
│   ├── core/                     # Orchestrator, types, policies
│   ├── mcp/                      # MCP client wrapper
│   ├── extractors/               # DOM parsers & heuristics
│   ├── judge/                    # LLM client & rubric
│   ├── report/                   # Report generators
│   └── cli/                      # CLI entrypoint
├── configs/                      # YAML configurations
│   ├── default.yaml             # Default settings
│   └── sites/                   # Site-specific configs
├── data/queries/                # Predefined query sets
├── examples/                    # Example configs
├── runs/                        # Audit artifacts (gitignored)
├── scripts/                     # Helper scripts
└── tests/                       # Unit tests
```

## Configuration

See `configs/default.yaml` for all available options. Key settings:

- **site**: Target URL and locale
- **search**: Selectors and strategies for search box and results
- **modals**: Cookie/consent handling
- **run**: Top-K results, viewport, headless mode, rate limiting
- **llm**: Provider (vllm/openai/anthropic), model, temperature, seed, base_url
- **report**: Output formats and directory

### Vision Provider Configuration

The intelligent search box detection supports multiple vision providers:

- **vLLM**: Local vision models (LLaVA, Qwen-VL, etc.) - Free, private, GPU required
- **OpenRouter**: Cloud API gateway (Qwen-VL, Claude, GPT-4V, etc.) - Cheap, easy, no GPU needed
- **OpenAI**: GPT-4o, GPT-4o-mini - Direct API, cloud-based, no GPU needed
- **Anthropic**: Claude 3.5 Sonnet (coming soon)

**Recommended for most users**: OpenRouter with Qwen-VL-Plus (best value, excellent quality)

See [VLLM_SETUP.md](VLLM_SETUP.md) for detailed setup instructions for all providers.

## Architecture

1. **Orchestrator** (`core/`): Manages audit flow, state, and rate limiting
2. **MCP Client** (`mcp/`): Wraps chrome-devtools-mcp for browser control
3. **Extractors** (`extractors/`): Finds search boxes, parses results, handles modals
4. **Judge** (`judge/`): LLM-based quality scoring with structured rubric
5. **Reporter** (`report/`): Generates human-readable reports

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
- **Robots.txt**: Respect crawling policies (P1)
- **Data Privacy**: Use isolated browser profiles, avoid sensitive data
- **MCP Security**: Be aware that MCP exposes browser contents to the LLM

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
- **Coverage reports** generated with pytest-cov

```bash
# Quick test run
make test

# With coverage report
make test-cov

# Run only unit tests
make test-unit
```

## Roadmap

- [x] P0: Nike.com support with predefined queries
- [ ] P1: LLM-generated queries from site content
- [ ] P2: Multi-LLM support (Anthropic, Gemini, etc.)
- [ ] P3: Multi-language support
- [ ] P4: Cross-model reliability experiments

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [chrome-devtools-mcp](https://github.com/modelcontextprotocol/servers/tree/main/src/puppeteer) for browser automation via MCP
- OpenAI for LLM capabilities
- The MCP community for the protocol specification
