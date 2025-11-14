# Quick Start Guide

Get up and running with Agentic Search Audit in 5 minutes.

## Prerequisites

- **Python 3.10+** installed
- **Node.js** installed (for chrome-devtools-mcp)
- **OpenAI API key** (sign up at [platform.openai.com](https://platform.openai.com))

## Installation

### 1. Clone and Install

```bash
# Clone the repository
git clone https://github.com/yourusername/agentic-search-audit.git
cd agentic-search-audit

# Install the package
pip install -e .
```

### 2. Set Up Environment Variables

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your OpenAI API key
echo "OPENAI_API_KEY=your-api-key-here" > .env
```

### 3. Verify Installation

```bash
# Check that the CLI is available
search-audit --help

# Verify MCP server is accessible
npx chrome-devtools-mcp@latest --help
```

## Run Your First Audit

### Nike.com Example (Predefined Queries)

The easiest way to get started is with the Nike.com example:

```bash
# Run audit on Nike.com with 10 predefined queries
search-audit --site nike

# Or run with just 3 queries for a quick test
search-audit --site nike --queries examples/quick-test.json
```

This will:
1. Launch Chrome in headless mode
2. Navigate to nike.com
3. Run searches for each query
4. Extract and evaluate results
5. Generate reports in `./runs/nike.com/{timestamp}/`

### View Results

After the audit completes, check:

```bash
# Open the HTML report
open runs/nike.com/*/report.html

# Or view the Markdown report
cat runs/nike.com/*/report.md

# Raw data in JSONL format
cat runs/nike.com/*/audit.jsonl
```

## Customize Your Audit

### Use a Different Site

1. Create a config file:

```bash
cp examples/custom_site.yaml configs/sites/mysite.yaml
```

2. Edit `configs/sites/mysite.yaml`:
   - Update `site.url`
   - Customize CSS selectors for your site
   - Adjust search and results extraction settings

3. Create queries:

```bash
cp examples/custom_queries.json data/queries/mysite.json
```

4. Run:

```bash
search-audit --site mysite
```

### Run in Headed Mode (Visible Browser)

Watch the browser in action:

```bash
search-audit --site nike --no-headless
```

### Adjust Number of Results

```bash
# Extract top 20 results instead of default 10
search-audit --site nike --top-k 20
```

### Change Output Directory

```bash
search-audit --site nike --output ./my-audit-results
```

## Understanding the Output

Each audit run creates:

```
runs/nike.com/20241114_153045/
├── report.md              # Markdown report
├── report.html            # HTML report (open in browser)
├── audit.jsonl            # Raw data (one record per line)
├── screenshots/           # Full-page screenshots
│   ├── q001_running_shoes.png
│   ├── q002_air_jordan.png
│   └── ...
└── html_snapshots/        # Raw HTML snapshots
    ├── q001_running_shoes.html
    ├── q002_air_jordan.html
    └── ...
```

### Report Contents

- **Summary**: Average scores across all queries
- **Score Distribution**: How many queries in each score range
- **Per-Query Details**:
  - Scores (Overall, Relevance, Diversity, Quality, Navigability)
  - Rationale and evidence
  - Issues identified
  - Suggested improvements
  - Top results table
  - Screenshot

## Advanced Usage

### Custom LLM Settings

```bash
# Use GPT-4 for higher quality evaluations
search-audit --site nike \
  --config-override '{"llm": {"model": "gpt-4"}}'

# Adjust temperature for more/less variance
search-audit --site nike \
  --config-override '{"llm": {"temperature": 0.0}}'
```

### Reproducible Runs

```bash
# Use a seed for deterministic LLM outputs
search-audit --site nike --seed 12345
```

### Rate Limiting

Edit `configs/sites/mysite.yaml`:

```yaml
run:
  throttle_rps: 0.5  # 0.5 requests per second (2s between requests)
```

### Debugging

```bash
# Enable debug logging
search-audit --site nike --log-level DEBUG
```

## Common Issues

### "OPENAI_API_KEY environment variable not set"

Solution: Make sure your `.env` file exists and contains:
```
OPENAI_API_KEY=sk-...
```

### "npx: command not found"

Solution: Install Node.js from [nodejs.org](https://nodejs.org)

### "No search box found"

Solution: The site's search box selectors may be different. Update `configs/sites/yoursite.yaml`:

```yaml
site:
  search:
    input_selectors:
      - 'input#your-search-id'
      - 'input.your-search-class'
```

Use browser DevTools to inspect the search input element.

### Browser crashes or timeouts

Solution: Increase timeouts in your config:

```yaml
run:
  network_idle_ms: 3000
  post_submit_ms: 2000
```

## Next Steps

- Read [CONTRIBUTING.md](CONTRIBUTING.md) to learn how to extend the tool
- Check [README.md](README.md) for full documentation
- Explore `configs/sites/nike.yaml` to see a complete configuration
- Run `scripts/smoke.sh` for a quick validation test

## Getting Help

- Check existing [issues](https://github.com/yourusername/agentic-search-audit/issues)
- Open a new issue for bugs or feature requests
- Read the full docs in [README.md](README.md)

Happy auditing! 🎯
