# Intelligent Search Box Detection

## Overview

The agentic search audit tool now includes **intelligent search box detection** using LLM vision capabilities. This feature automatically finds search input boxes on websites, even when traditional CSS selectors fail.

## How It Works

### Traditional Approach (CSS Selectors)
The system first attempts to find search boxes using predefined CSS selectors:
```yaml
search:
  input_selectors:
    - 'input[type="search"]'
    - 'input[data-testid="search-input"]'
    - 'input[aria-label*="Search" i]'
```

**Problems with this approach:**
- Brittle: breaks when websites change their HTML structure
- Not scalable: requires manual configuration for each site
- Maintenance overhead: need to update selectors regularly

### Intelligent Approach (LLM + Vision)
When CSS selectors fail, the system automatically:
1. **Takes a screenshot** of the webpage
2. **Extracts HTML structure** of the page header/navigation area
3. **Sends both to an LLM** (GPT-4o-mini with vision)
4. **Receives intelligent suggestions** for CSS selectors
5. **Validates selectors** and uses the first working one
6. **Auto-detects submit strategy** (Enter key vs. button click)

## Configuration

Enable intelligent detection in your site config:

```yaml
site:
  search:
    # Traditional selectors (tried first)
    input_selectors:
      - 'input[type="search"]'
      - 'input[aria-label*="Search" i]'

    # Intelligent fallback settings
    use_intelligent_fallback: true  # Enable LLM-based detection
    intelligent_detection_model: "gpt-4o-mini"  # OpenAI model to use

    submit_strategy: "enter"
    submit_selector: null
```

## Requirements

- **OpenAI API Key**: Set `OPENAI_API_KEY` environment variable
- **Vision-capable model**: Use `gpt-4o-mini` or `gpt-4o` (recommended: `gpt-4o-mini` for cost)

## Benefits

### 🎯 Robustness
Works across different websites without manual configuration

### 🔄 Self-Healing
Automatically adapts when websites update their HTML

### 📊 Scalability
No need to manually configure selectors for each new site

### 💡 Smart
Understands visual context and page structure, not just CSS

### 💰 Cost-Effective
Only runs when traditional selectors fail (fallback only)

## Example Output

```
2025-11-18 13:00:00 - INFO - Searching for search input box...
2025-11-18 13:00:01 - WARNING - No search box found with configured selectors
2025-11-18 13:00:01 - INFO - Falling back to intelligent LLM-based detection...
2025-11-18 13:00:05 - INFO - Found search box with high confidence: input[aria-label="Search"]
2025-11-18 13:00:05 - INFO - Reasoning: Found main search input in header with aria-label
2025-11-18 13:00:05 - INFO - LLM found valid search box: input[aria-label="Search"]
```

## How the LLM Analyzes Pages

The LLM receives:
1. **Screenshot** (visual context of the page)
2. **HTML snippet** (first 5000 chars - typically header/nav area)

And returns:
```json
{
  "selectors": [
    "input[aria-label='Search']",
    "input[placeholder='Search']",
    "#search-input"
  ],
  "submit_strategy": "enter",
  "submit_selector": null,
  "confidence": "high",
  "reasoning": "Found main search input in header navigation with clear aria-label"
}
```

## Disabling Intelligent Detection

To disable and use only CSS selectors:

```yaml
search:
  use_intelligent_fallback: false
```

## Best Practices

1. **Keep CSS selectors**: Still define good CSS selectors - they're faster and cheaper
2. **Use as fallback**: Intelligent detection works best as a safety net
3. **Monitor costs**: Track OpenAI API usage if processing many sites
4. **Review suggestions**: Check logs to see what selectors the LLM found
5. **Update configs**: If LLM consistently finds better selectors, update your config

## Performance

- **Traditional selectors**: ~100ms (instant)
- **Intelligent detection**: ~3-5 seconds (LLM API call + vision processing)
- **Cost**: ~$0.001-0.003 per detection (using gpt-4o-mini)

## Troubleshooting

### "OPENAI_API_KEY environment variable not set"
```bash
export OPENAI_API_KEY="sk-..."
```

### Intelligent detection fails
Check logs for:
- Screenshot capture issues
- HTML extraction problems
- LLM API errors
- Selector validation failures

### High API costs
- Ensure `use_intelligent_fallback: true` (only runs on fallback)
- Use `gpt-4o-mini` instead of `gpt-4o`
- Add more accurate CSS selectors to reduce fallback usage

## Future Enhancements

- Cache discovered selectors for future runs
- Support for other LLM providers (Anthropic Claude, etc.)
- Visual bounding box detection
- Selector persistence and learning
