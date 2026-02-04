# LLM Selector Detection Implementation Analysis

## Overview
The codebase currently implements LLM-based selector detection using **OpenAI's GPT-4O Mini** with vision capabilities for intelligent fallback when CSS selectors fail to find elements.

---

## 1. Core Architecture

### Main Components:

#### A. **IntelligentSearchBoxFinder** (`intelligent_finder.py`)
- Uses OpenAI's vision API to analyze screenshots and HTML
- Falls back to LLM-based detection when traditional CSS selectors fail
- Returns suggested CSS selectors with confidence levels

#### B. **SearchBoxFinder** (`search_box.py`)
- First tries traditional CSS selectors
- Falls back to intelligent LLM-based detection if enabled
- Validates suggested selectors before use
- Configurable submit strategies

#### C. **SearchQualityJudge** (`judge.py`)
- Evaluates search quality using LLM
- Scores: relevance, diversity, result_quality, navigability, overall
- Currently supports only OpenAI provider

---

## 2. LLM Detection Logic

### File: `/home/user/agentic-search-audit/src/agentic_search_audit/extractors/intelligent_finder.py`

**Key Features:**
- Takes screenshot (base64 encoded) + HTML snippet as input
- Sends both to OpenAI's chat completion with vision
- Returns JSON with selectors, submit strategy, and confidence level

**Vision API Usage:**
```python
response = await self.openai_client.chat.completions.create(
    model=self.llm_model,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{screenshot_base64}",
                        "detail": "high",
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }
    ],
    response_format={"type": "json_object"},
)
```

**Prompt Template:**
Located in `SEARCH_BOX_FINDER_PROMPT` - instructs LLM to:
1. Identify main search input field
2. Provide multiple CSS selectors (most reliable first)
3. Suggest submit method (Enter or button click)
4. Return confidence level

---

## 3. Current Configuration

### Model Configuration:

**Files:**
- `/home/user/agentic-search-audit/src/agentic_search_audit/core/types.py` (lines 160-168)
- `/home/user/agentic-search-audit/src/agentic_search_audit/core/types.py` (lines 100-103)
- `/home/user/agentic-search-audit/configs/default.yaml` (lines 62-67)

**Current Settings:**
```yaml
llm:
  provider: "openai"  # Only option currently working
  model: "gpt-4o-mini"
  max_tokens: 800
  temperature: 0.2

search:
  intelligent_detection_model: "gpt-4o-mini"
  use_intelligent_fallback: true
```

**Environment Variables:**
- `OPENAI_API_KEY` (required)
- `ANTHROPIC_API_KEY` (defined but not implemented)

---

## 4. Current Implementation Issues

### A. **OpenAI-Only Support**
- Judge only supports OpenAI provider (line 32-38 in judge.py)
- Anthropic provider defined in types but raises "not supported" error
- No vision capability for other LLMs

### B. **Hardcoded Vision Implementation**
- Screenshot taken with `await self.client.screenshot()`
- Saved to `/tmp/search_detection.png`
- Base64 encoded and sent to OpenAI
- HTML snippet truncated to 5000 characters

### C. **Screenshot Dependencies**
- Full page screenshot captured for detection
- Only viewport screenshot available (full_page=False not used in detection)
- Relies on file I/O (read from `/tmp/` directory)

### D. **Query Selector Implementation Issue** (RECENTLY FIXED)
- Fixed in commit 5ba5284: Query selector was returning JavaScript objects
- Changed to return boolean "true"/"false" string for reliability
- Python check: `if result and len(result) > 0 and result[0].text == "true"`

---

## 5. Browser Integration (MCP Client)

### File: `/home/user/agentic-search-audit/src/agentic_search_audit/mcp/client.py`

**Key Methods:**
- `query_selector(selector)` - Returns element existence check
- `query_selector_all(selector)` - Returns array of matching elements
- `screenshot(path, full_page)` - Takes browser screenshot
- `get_html()` - Extracts full HTML content

**Current Implementation of query_selector (lines 154-179):**
```python
async def query_selector(self, selector: str) -> dict[str, Any] | None:
    result = await self._call_tool(
        "evaluate_script",
        {
            "function": """(selector) => {
                return document.querySelector(selector) !== null;
            }""",
            "args": [selector],
        },
    )
    if result and len(result) > 0 and result[0].text == "true":
        return {"exists": True}
    return None
```

---

## 6. Vision LLM Detection Flow

```
SearchBoxFinder.find_search_box()
  ├─ Try traditional CSS selectors
  │   └─ client.query_selector(selector)
  │       └─ MCP: evaluate_script → returns boolean
  │
  └─ Fallback: _intelligent_find()
      └─ IntelligentSearchBoxFinder.find_search_box()
          ├─ Take screenshot
          │   └─ client.screenshot() → /tmp/search_detection.png
          │
          ├─ Extract HTML
          │   └─ client.get_html() → first 5000 chars
          │
          ├─ Encode screenshot to base64
          │
          ├─ Call OpenAI Chat Completion with Vision
          │   └─ Send: [image_url (base64) + text prompt]
          │   └─ Return: JSON (selectors, strategy, confidence)
          │
          └─ Validate returned selectors
              └─ query_selector() for each suggestion
```

---

## 7. Missing vLLM Integration

### What's NOT Implemented:
1. **No vLLM Support** - vLLM is not referenced anywhere in codebase
2. **No Claude Vision Models** - Anthropic support is stubbed out
3. **No Local Vision Models** - All vision processing is via OpenAI API

### Type Definition (types.py, line 163):
```python
provider: Literal["openai", "anthropic"] = Field(default="openai")
```

But only OpenAI is actually implemented in judge.py

---

## 8. File Structure

```
/home/user/agentic-search-audit/
├── src/agentic_search_audit/
│   ├── extractors/
│   │   ├── search_box.py              [CSS selector + fallback to LLM]
│   │   ├── intelligent_finder.py      [Vision-based detection using OpenAI]
│   │   ├── results.py                 [Results extraction]
│   │   └── modals.py                  [Modal handling]
│   │
│   ├── judge/
│   │   ├── judge.py                   [LLM-based quality evaluation]
│   │   └── rubric.py                  [Evaluation criteria]
│   │
│   ├── mcp/
│   │   └── client.py                  [Browser automation via MCP]
│   │
│   └── core/
│       ├── types.py                   [Configuration types + LLMConfig]
│       ├── config.py                  [Config loading]
│       └── orchestrator.py            [Main audit orchestration]
│
├── configs/
│   └── default.yaml                   [Default configuration]
│
└── .env.example                        [Environment variables]
```

---

## 9. Configuration Override Points

### 1. Per-Site Configuration
File: `/home/user/agentic-search-audit/configs/sites/nike.yaml`
- Can override intelligent_detection_model

### 2. Runtime Configuration
SearchBoxFinder.__init__():
```python
def __init__(
    self,
    client: MCPBrowserClient,
    config: SearchConfig,
    use_intelligent_fallback: bool = True,
    llm_model: str = "gpt-4o-mini",  # <-- Can override here
):
```

### 3. Global LLM Config
Via `llm` section in YAML or AuditConfig

---

## 10. Recent Fixes

### Commit 5ba5284: "Fix search box detection in query_selector"
**Problem:** JavaScript object serialization was unreliable through MCP protocol

**Solution:**
- Changed JS to return boolean instead of object
- `document.querySelector(selector) !== null` → boolean
- Python parser compares: `result[0].text == "true"`

**Impact:** Fixes "Could not find search box" errors in search audit

---

## 11. Key Dependencies

```
openai==1.x          [For Vision API calls]
mcp                   [For browser automation protocol]
pydantic              [Configuration validation]
httpx / AsyncOpenAI   [HTTP client for LLM]
```

---

## Summary: Vision LLM Detection Status

✅ **Implemented:**
- OpenAI GPT-4O Mini vision detection
- Screenshot + HTML to LLM pipeline
- Fallback logic when CSS selectors fail
- Multi-selector suggestion with confidence
- Selector validation before use

❌ **Not Implemented:**
- vLLM integration
- Claude/Anthropic vision models
- Local vision LLM support
- Alternative vision providers

⚠️ **Known Issues:**
- Hard dependency on OpenAI API key
- Screenshot file I/O to /tmp directory
- HTML truncation (5000 chars) may miss important structure
- No caching of vision analysis results
- Temperature=0.2 may be too strict for some detection scenarios
