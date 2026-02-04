# LLM Selector Detection - Code Reference

## 1. IntelligentSearchBoxFinder Class
**File:** `/home/user/agentic-search-audit/src/agentic_search_audit/extractors/intelligent_finder.py`

### Initialization with OpenAI Vision
```python
class IntelligentSearchBoxFinder:
    """Uses LLM with vision to intelligently find search boxes."""

    def __init__(self, client: MCPBrowserClient, llm_model: str = "gpt-4o-mini"):
        """Initialize intelligent finder.

        Args:
            client: MCP browser client
            llm_model: OpenAI model with vision capability
        """
        self.client = client
        self.llm_model = llm_model

        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        self.openai_client = AsyncOpenAI(api_key=api_key)
```

### Vision-based Detection Method
```python
async def find_search_box(self) -> dict[str, Any] | None:
    """Use LLM to find the search box on the current page.

    Returns:
        Dictionary with selectors and strategy, or None if not found
    """
    logger.info("Using intelligent search box detection...")

    try:
        # Get screenshot
        screenshot_path = Path("/tmp/search_detection.png")
        await self.client.screenshot(screenshot_path, full_page=False)

        # Get HTML
        html_content = await self.client.get_html()

        # Prepare HTML snippet (first 5000 chars to include header/nav area)
        html_snippet = html_content[:5000]

        # Read screenshot as base64
        with open(screenshot_path, "rb") as f:
            screenshot_base64 = base64.b64encode(f.read()).decode("utf-8")

        # Call LLM with vision
        result = await self._analyze_page(screenshot_base64, html_snippet)

        if result and result.get("confidence") in ["high", "medium"]:
            logger.info(
                f"Found search box with {result['confidence']} confidence: "
                f"{result['selectors'][0] if result['selectors'] else 'none'}"
            )
            logger.info(f"Reasoning: {result.get('reasoning', 'N/A')}")
            return result
        else:
            logger.warning("LLM could not find search box with sufficient confidence")
            return None

    except Exception as e:
        logger.error(f"Intelligent search box detection failed: {e}", exc_info=True)
        return None
```

### LLM Vision Analysis Call
```python
async def _analyze_page(
    self, screenshot_base64: str, html_snippet: str
) -> dict[str, Any] | None:
    """Analyze page with LLM vision.

    Args:
        screenshot_base64: Base64-encoded screenshot
        html_snippet: HTML snippet of the page

    Returns:
        Analysis result or None
    """
    try:
        # Build prompt
        prompt = SEARCH_BOX_FINDER_PROMPT.format(html_snippet=html_snippet)

        # Call OpenAI with vision
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
            max_tokens=1000,
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        # Parse response
        content = response.choices[0].message.content
        if not content:
            return None

        result = json.loads(content)
        return result

    except Exception as e:
        logger.error(f"Failed to analyze page with LLM: {e}")
        return None
```

### Selector Validation
```python
async def validate_selector(self, selector: str) -> bool:
    """Validate that a selector exists on the page.

    Args:
        selector: CSS selector to validate

    Returns:
        True if selector is valid and element exists
    """
    try:
        element = await self.client.query_selector(selector)
        return element is not None
    except Exception as e:
        logger.debug(f"Selector validation failed for {selector}: {e}")
        return False
```

---

## 2. SearchBoxFinder Class (Orchestrates detection)
**File:** `/home/user/agentic-search-audit/src/agentic_search_audit/extractors/search_box.py`

### Fallback Logic
```python
async def find_search_box(self) -> str | None:
    """Find the search input box using configured selectors.

    First tries traditional CSS selectors, then falls back to LLM-based
    intelligent detection if enabled.

    Returns:
        CSS selector of found search box, or None if not found
    """
    logger.info("Searching for search input box...")

    # Try traditional CSS selectors first
    for selector in self.config.input_selectors:
        logger.debug(f"Trying selector: {selector}")

        # Try to find element
        element = await self.client.query_selector(selector)
        if element:
            logger.info(f"Found search box with selector: {selector}")
            return selector

    logger.warning("No search box found with configured selectors")

    # Fall back to intelligent detection
    if self.use_intelligent_fallback:
        logger.info("Falling back to intelligent LLM-based detection...")
        return await self._intelligent_find()

    return None
```

### LLM Fallback Implementation
```python
async def _intelligent_find(self) -> str | None:
    """Use LLM to intelligently find the search box.

    Returns:
        CSS selector of found search box, or None if not found
    """
    try:
        # Initialize intelligent finder if needed
        if not self._intelligent_finder:
            self._intelligent_finder = IntelligentSearchBoxFinder(
                self.client, llm_model=self.llm_model
            )

        # Find search box using LLM
        result = await self._intelligent_finder.find_search_box()

        if not result or not result.get("selectors"):
            return None

        # Validate and use the suggested selectors
        for selector in result["selectors"]:
            if await self._intelligent_finder.validate_selector(selector):
                logger.info(f"LLM found valid search box: {selector}")

                # Update config with discovered strategy
                if result.get("submit_strategy"):
                    self.config.submit_strategy = result["submit_strategy"]
                if result.get("submit_selector"):
                    self.config.submit_selector = result["submit_selector"]

                return selector

        logger.warning("LLM suggested selectors but none were valid")
        return None

    except Exception as e:
        logger.error(f"Intelligent search box detection failed: {e}")
        return None
```

---

## 3. LLM Configuration
**File:** `/home/user/agentic-search-audit/src/agentic_search_audit/core/types.py` (lines 160-168)

```python
class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: Literal["openai", "anthropic"] = Field(default="openai", description="LLM provider")
    model: str = Field(default="gpt-4o-mini", description="Model identifier")
    max_tokens: int = Field(default=800, description="Max tokens in response")
    temperature: float = Field(default=0.2, description="Sampling temperature")
    system_prompt: str | None = Field(default=None, description="Custom system prompt override")
```

**SearchConfig for Intelligent Detection (lines 100-103):**
```python
intelligent_detection_model: str = Field(
    default="gpt-4o-mini",
    description="OpenAI model to use for intelligent search box detection",
)
```

---

## 4. Search Quality Judge
**File:** `/home/user/agentic-search-audit/src/agentic_search_audit/judge/judge.py`

### Judge Initialization (OpenAI-only)
```python
class SearchQualityJudge:
    """LLM-based judge for search quality evaluation."""

    def __init__(self, config: LLMConfig):
        """Initialize judge.

        Args:
            config: LLM configuration
        """
        self.config = config

        # Initialize LLM client
        if config.provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            self.client = AsyncOpenAI(api_key=api_key)
        else:
            raise ValueError(f"Unsupported LLM provider: {config.provider}")

        self.schema = get_judge_schema()
```

### Judge Evaluation
```python
async def _call_llm(self, user_prompt: str) -> str:
    """Call LLM for evaluation.

    Args:
        user_prompt: User prompt

    Returns:
        LLM response text
    """
    logger.debug("Calling LLM for evaluation...")

    if self.config.provider == "openai":
        response = await self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": self.config.system_prompt or JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            response_format={"type": "json_object"},
            seed=self.config.seed if hasattr(self.config, "seed") else None,
        )

        return response.choices[0].message.content or ""

    raise ValueError(f"Unsupported provider: {self.config.provider}")
```

---

## 5. MCP Browser Client - Query Selector
**File:** `/home/user/agentic-search-audit/src/agentic_search_audit/mcp/client.py` (lines 154-179)

### Recently Fixed: Boolean Return
```python
async def query_selector(self, selector: str) -> dict[str, Any] | None:
    """Query DOM for a single element.

    Args:
        selector: CSS selector

    Returns:
        Element info or None if not found
    """
    try:
        result = await self._call_tool(
            "evaluate_script",
            {
                "function": """(selector) => {
                    return document.querySelector(selector) !== null;
                }""",
                "args": [selector],
            },
        )
        # Check if the result indicates the element exists
        if result and len(result) > 0 and result[0].text == "true":
            return {"exists": True}
        return None
    except Exception as e:
        logger.debug(f"Selector {selector} not found: {e}")
        return None
```

### Query Selector All
```python
async def query_selector_all(self, selector: str) -> list[dict[str, Any]]:
    """Query DOM for all matching elements.

    Args:
        selector: CSS selector

    Returns:
        List of element info
    """
    try:
        result = await self._call_tool(
            "evaluate_script",
            {
                "function": """(selector) => {
                    const elements = document.querySelectorAll(selector);
                    return Array.from(elements).map((el, i) => ({index: i}));
                }""",
                "args": [selector],
            },
        )
        if result and result[0].text:
            elements = json.loads(result[0].text)
            return elements if isinstance(elements, list) else []
        return []
    except Exception as e:
        logger.debug(f"Selector {selector} returned no results: {e}")
        return []
```

---

## 6. Search Box Detection Prompt
**File:** `/home/user/agentic-search-audit/src/agentic_search_audit/extractors/intelligent_finder.py` (lines 17-44)

```python
SEARCH_BOX_FINDER_PROMPT = """You are a web automation expert. Analyze this webpage screenshot and HTML to find the search input box.

Your task:
1. Identify the main search input field on the page
2. Provide CSS selectors that can uniquely identify this element
3. Suggest the best way to submit the search (pressing Enter or clicking a button)

Return your response as JSON with this structure:
{
  "selectors": ["selector1", "selector2", "selector3"],
  "submit_strategy": "enter" or "clickSelector",
  "submit_selector": "button selector if applicable, else null",
  "confidence": "high", "medium", or "low",
  "reasoning": "Brief explanation of your selection"
}

Provide multiple selector options ordered by reliability (most reliable first).
Consider:
- input[type="search"]
- input elements with search-related aria-labels
- input elements with search-related names, IDs, or classes
- input elements with search-related placeholders

Be specific and use attributes that are unlikely to change (data-testid, aria-label, etc. are better than generic classes).

HTML snippet:
{html_snippet}
"""
```

---

## 7. Default Configuration
**File:** `/home/user/agentic-search-audit/configs/default.yaml` (lines 62-67)

```yaml
llm:
  provider: "openai"  # "openai" or "anthropic"
  model: "gpt-4o-mini"
  max_tokens: 800
  temperature: 0.2
  system_prompt: null  # uses default if null
```

---

## 8. Environment Configuration
**File:** `/home/user/agentic-search-audit/.env.example`

```
# OpenAI API Key (required for LLM judge)
OPENAI_API_KEY=your-openai-api-key-here

# Anthropic API Key (optional, for future multi-LLM support)
ANTHROPIC_API_KEY=your-anthropic-api-key-here

# Default configuration file
CONFIG_PATH=configs/default.yaml

# Log level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO

# MCP server settings (optional, defaults are usually fine)
# MCP_CHROME_HEADLESS=true
# MCP_CHROME_ISOLATED=true
```

---

## 9. Integration in Orchestrator
**File:** `/home/user/agentic-search-audit/src/agentic_search_audit/core/orchestrator.py` (lines 113-118)

```python
# Find and submit search
search_finder = SearchBoxFinder(
    self.client,
    self.config.site.search,
    use_intelligent_fallback=self.config.site.search.use_intelligent_fallback,
    llm_model=self.config.site.search.intelligent_detection_model,
)
success = await search_finder.submit_search(query.text)
```

---

## Key Insight: Vision LLM Flow

```
1. SearchBoxFinder tries CSS selectors
   └─ Uses MCP client.query_selector()

2. If fails, calls _intelligent_find()
   └─ Creates IntelligentSearchBoxFinder
      ├─ Takes screenshot via client.screenshot()
      ├─ Gets HTML via client.get_html()
      ├─ Base64 encodes screenshot
      └─ Calls OpenAI Chat Completion with:
         ├─ image_url (base64 PNG)
         ├─ text prompt with HTML snippet
         └─ response_format=json_object

3. Receives JSON with:
   - selectors[] (ordered by reliability)
   - submit_strategy (enter|clickSelector)
   - submit_selector (button selector)
   - confidence (high|medium|low)
   - reasoning

4. Validates each selector via query_selector()
5. Returns first valid selector
```
