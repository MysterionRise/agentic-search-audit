# Agentic Search Audit

AI-powered on-site search quality evaluation using Chrome DevTools MCP and LLM-as-a-judge.

## Overview

This tool automates the evaluation of on-site search quality for e-commerce and other websites. It:

1. Opens a real browser via `chrome-devtools-mcp`
2. Runs searches with predefined or LLM-generated queries
3. Extracts the top-K search results
4. Uses an LLM judge to score search quality on multiple dimensions
5. Generates comprehensive reports with screenshots and evidence

## Features

- **Browser Automation**: Uses MCP (Model Context Protocol) to control Chrome via DevTools
- **Smart Extraction**: Heuristics-based DOM parsing with site-specific overrides
- **LLM Judge**: Structured evaluation with reproducible scoring (OpenAI GPT-4o-mini by default)
- **Multi-format Reports**: Markdown and HTML reports with detailed evidence
- **Configurable**: YAML configuration for site-specific selectors and behavior
- **Artifacts**: Screenshots, HTML snapshots, and JSONL data for each query

## Quick Start

### Prerequisites

- Node.js >= 18
- pnpm >= 8
- OpenAI API key
- Claude Code (for MCP integration)

### 1. Install Dependencies

```bash
pnpm install
```

### 2. Set up MCP Server (Chrome DevTools)

If using Claude Code, add the chrome-devtools-mcp server:

```bash
claude mcp add chrome-devtools npx chrome-devtools-mcp@latest
```

For headless mode (recommended):

```bash
claude mcp add chrome-devtools npx chrome-devtools-mcp@latest -- --headless=true --isolated=true
```

**Important**: The chrome-devtools-mcp server exposes browser content to the MCP client. Use isolated profiles and avoid loading sensitive data.

### 3. Configure API Key

Create a `.env` file:

```bash
cp .env.example .env
# Edit .env and add your OpenAI API key
```

Or export it:

```bash
export OPENAI_API_KEY=sk-...
```

### 4. Build the Project

```bash
pnpm run build
```

### 5. Run the Nike.com Example

```bash
pnpm search-audit run \
  --site https://www.nike.com \
  --config ./configs/sites/nike.yaml \
  --queries ./data/queries/nike-en.json \
  --topk 10 \
  --seed 42
```

Or use the smoke test script:

```bash
pnpm run smoke
```

### 6. View Results

Reports are saved to `./runs/<timestamp>/`:

- `report.md` - Markdown report
- `report.html` - HTML report (open in browser)
- `audit.jsonl` - Raw audit records
- `*-screenshot.png` - Screenshots for each query
- `*-page.html` - HTML snapshots for each query

## Architecture

```
apps/cli/           - CLI application
packages/
  core/             - Orchestrator and configuration
  mcp/              - MCP client wrapper
  extractors/       - DOM parsing and heuristics
  judge/            - LLM judge implementation
  report/           - Report generators
configs/            - Configuration files
data/queries/       - Query sets
runs/               - Output artifacts
```

## Configuration

### Site Configuration (YAML)

```yaml
site:
  url: "https://www.nike.com"
  locale: "en-US"
  search:
    inputSelectors:
      - 'input[type="search"]'
      - 'input[aria-label*="Search" i]'
    submitStrategy: "enter"
  results:
    itemSelectors:
      - '[data-testid="product-card"]'
    titleSelectors:
      - 'h2'
      - '.title'
    urlAttr: 'href'
    snippetSelectors:
      - '.description'
  modals:
    closeTextMatches:
      - "accept"
      - "close"
    maxAutoClicks: 3

run:
  topK: 10
  viewport: { width: 1366, height: 900 }
  waitFor: { networkIdleMs: 1200, postSubmitMs: 800 }
  headless: true
  throttleRPS: 0.5
  seed: 42

llm:
  provider: "openai"
  model: "gpt-4o-mini"
  maxTokens: 800
  temperature: 0.2

report:
  format: ["md", "html"]
  outDir: "./runs"
```

### Query Format (JSON)

```json
[
  {
    "id": "q1",
    "text": "air force 1 white",
    "origin": "predefined"
  },
  {
    "id": "q2",
    "text": "men's running shoes",
    "origin": "predefined"
  }
]
```

## LLM Judge Rubric

The judge evaluates search results on five dimensions (0-5 scale):

1. **Relevance**: How well results match the search intent
2. **Diversity**: Variety in products, brands, categories, price points
3. **Result Quality**: Clarity, no duplication, valid links
4. **Navigability**: Presence of filters, sorting, navigation aids
5. **Overall**: User satisfaction (not an average of other scores)

The judge outputs structured JSON with:
- Scores for each dimension
- Rationale
- Issues found
- Improvement suggestions
- Evidence from specific results

## CLI Usage

### Run an Audit

```bash
pnpm search-audit run \
  --site <url> \
  --config <path> \
  --queries <path> \
  --topk <number> \
  --seed <number> \
  --out <dir>
```

### Validate Configuration

```bash
pnpm search-audit validate --config ./configs/sites/nike.yaml
```

## MCP Setup Details

The chrome-devtools-mcp server provides tools for:
- Navigation (`navigate`)
- DOM querying (`query_selector_all`)
- Element interaction (`click`, `type`)
- Screenshots (`screenshot`)
- JavaScript execution (`execute_javascript`)
- Network monitoring
- Performance tracing

### Connection Options

**Default (launches new Chrome):**
```bash
npx chrome-devtools-mcp@latest
```

**Headless + Isolated:**
```bash
npx chrome-devtools-mcp@latest -- --headless=true --isolated=true
```

**Connect to existing Chrome:**
```bash
# Start Chrome with remote debugging
chrome --remote-debugging-port=9222

# Connect MCP
npx chrome-devtools-mcp@latest -- --browserUrl=http://127.0.0.1:9222
```

**WebSocket endpoint:**
```bash
npx chrome-devtools-mcp@latest -- --wsEndpoint=ws://...
```

See the [chrome-devtools-mcp repository](https://github.com/modelcontextprotocol/servers/tree/main/src/chrome-devtools) for full documentation.

## Safety & Compliance

- **Rate Limiting**: Configurable RPS throttling (default: 0.5 RPS)
- **Robots.txt**: Manually check `robots.txt` before auditing
- **PII**: Do not run on sites with sensitive personal data
- **MCP Security**: The MCP server exposes all browser content to the AI. Use isolated profiles and avoid sensitive sites.
- **Cookies**: Artifacts may contain cookies/tokens; redact before sharing

## Troubleshooting

### MCP Connection Issues

If you get connection errors:

1. Verify MCP server is configured:
   ```bash
   claude mcp list
   ```

2. Test MCP server manually:
   ```bash
   npx chrome-devtools-mcp@latest
   ```

3. Check Chrome is available:
   ```bash
   which google-chrome || which chromium
   ```

### Search Box Not Found

If the tool can't find the search box:

1. Add site-specific selectors to your config:
   ```yaml
   site:
     search:
       inputSelectors:
         - 'input#search-field'
         - '[data-qa="search-input"]'
   ```

2. Use the default config as a starting point:
   ```bash
   cp configs/default.yaml configs/sites/mysite.yaml
   ```

### No Results Extracted

If results aren't being extracted:

1. Check the HTML snapshots in the run directory
2. Update `results.itemSelectors` in your config
3. Reduce `topK` if the site shows fewer results

### LLM Judge Errors

If the judge fails:

1. Verify your OpenAI API key is set
2. Check your API quota/limits
3. Review the error message for JSON schema issues

## Roadmap

### P1 (Next)
- Query generation from site content
- Multi-language support
- Additional LLM providers (Anthropic, OpenRouter)
- Advanced heuristics (infinite scroll, filters)

### P2 (Future)
- NDCG-based metrics
- Pairwise comparison of runs
- Web UI for browsing results
- Crawl etiquette (robots.txt parser, sitemap support)
- Performance insights via DevTools traces

## Contributing

This is an open-source project. Contributions welcome!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## References

- [Chrome DevTools MCP Documentation](https://github.com/modelcontextprotocol/servers/tree/main/src/chrome-devtools)
- [MCP Protocol Specification](https://modelcontextprotocol.io)
- [Chrome for Developers Blog](https://developer.chrome.com/blog/chrome-devtools-mcp)

## Disclaimer

This tool is for authorized search quality evaluation only. Always respect:
- Website terms of service
- Rate limits and robots.txt
- User privacy and data protection laws

Do not use this tool to scrape data, overload servers, or violate any policies.
