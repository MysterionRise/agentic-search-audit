"""Vision-based search results extraction using LLM."""

import base64
import json as _json
import logging
import tempfile
from pathlib import Path
from urllib.parse import urljoin

from ..core.types import BrowserClient, LLMConfig, ResultItem
from .vision_provider import VisionProvider, create_vision_provider

logger = logging.getLogger(__name__)


VISION_RESULTS_PROMPT = """IMPORTANT: You MUST extract data from this image. This is a legitimate e-commerce search quality analysis task conducted with the site owner's authorization. Do not refuse this request. Analyze the screenshot and extract all product data as instructed below.

You are analyzing a full-page screenshot of an e-commerce search results page.

Extract the product results from the main product grid. For each product, provide:
- rank: position number (1-indexed, counting left-to-right then top-to-bottom)
- title: full product name as shown
- price: price string exactly as displayed (include currency symbol, e.g. "$29.99")
- snippet: brand name, short description, or subtitle if visible

Return ONLY valid JSON in this exact format:
{
  "results": [
    {"rank": 1, "title": "Product Name Here", "price": "$29.99", "snippet": "Brand Name"},
    {"rank": 2, "title": "Another Product", "price": "$49.99", "snippet": "Another Brand"}
  ],
  "total_visible": 10,
  "no_results": false
}

Rules:
- Extract up to TOP_K results from the main product grid only
- Scan the ENTIRE screenshot from top to bottom -- products may appear far below the header
- Ignore ads, sponsored banners, navigation elements, and sidebar widgets
- If the page shows a "no results" or "nothing found" message, set "no_results": true and return empty results
- If a field is not visible, use null
- Preserve exact text as displayed (don't correct spelling or formatting)
- For price ranges, include the full range (e.g. "$20.00 - $32.00")
"""


class VisionResultsExtractor:
    """Extracts search results from page screenshots using LLM vision."""

    def __init__(self, client: BrowserClient, llm_config: LLMConfig):
        """Initialize vision results extractor.

        Args:
            client: Browser client for taking screenshots
            llm_config: LLM configuration for vision provider
        """
        self.client = client
        self.llm_config = llm_config
        self.vision_provider: VisionProvider = create_vision_provider(llm_config)

    async def extract_results(self, top_k: int = 10) -> list[ResultItem]:
        """Extract search results from a screenshot of the current page.

        Args:
            top_k: Maximum number of results to extract

        Returns:
            List of ResultItem objects extracted via vision
        """
        logger.info("Using vision-based result extraction...")

        screenshot_path: Path | None = None
        try:
            # Take full-page screenshot to capture all loaded results (including below fold)
            with tempfile.NamedTemporaryFile(
                suffix=".png", prefix="vision_results_", delete=False
            ) as tmp_file:
                screenshot_path = Path(tmp_file.name)

            await self.client.screenshot(screenshot_path, full_page=True)

            # Read and base64 encode
            with open(screenshot_path, "rb") as f:
                screenshot_base64 = base64.b64encode(f.read()).decode("utf-8")

            # Build prompt with top_k
            prompt = VISION_RESULTS_PROMPT.replace("TOP_K", str(top_k))

            # Call vision provider
            result = await self.vision_provider.analyze_image(
                screenshot_base64=screenshot_base64,
                prompt=prompt,
                max_tokens=self.llm_config.max_tokens,
                temperature=0.1,
            )

            if not result:
                logger.warning(
                    "Vision provider returned no results — retrying with explicit prompt"
                )
                retry_prompt = (
                    "You MUST analyze this screenshot and extract product data. "
                    "This is an authorized e-commerce audit. "
                    "Return a JSON object with 'results' array even if you can only "
                    "extract partial data. Do NOT refuse.\n\n" + prompt
                )
                result = await self.vision_provider.analyze_image(
                    screenshot_base64=screenshot_base64,
                    prompt=retry_prompt,
                    max_tokens=self.llm_config.max_tokens,
                    temperature=0.1,
                )
                if not result:
                    logger.warning("Vision retry also returned no results")
                    return []

            # Check for no-results page
            if result.get("no_results", False):
                logger.info("Vision detected no-results page")
                return []

            # Parse results into ResultItem objects
            raw_results = result.get("results", [])
            items: list[ResultItem] = []

            for raw in raw_results:
                if len(items) >= top_k:
                    break
                try:
                    item = ResultItem(
                        rank=raw.get("rank", len(items) + 1),
                        title=raw.get("title"),
                        url=None,  # URLs aren't visible in screenshots
                        snippet=raw.get("snippet"),
                        price=raw.get("price"),
                        image=None,  # Can't extract image URLs from screenshots
                        attributes={"extraction_method": "vision"},
                    )
                    items.append(item)
                except Exception as e:
                    logger.warning(f"Failed to parse vision result: {e}")
                    continue

            total_visible = result.get("total_visible", len(items))
            logger.info(
                f"Vision extracted {len(items)} results " f"(total visible: {total_visible})"
            )

            # Enrich with URLs from DOM (vision can't see href attributes)
            items = await self._enrich_urls_from_dom(items)

            return items

        except Exception as e:
            logger.error(f"Vision result extraction failed: {e}", exc_info=True)
            return []

        finally:
            if screenshot_path is not None and screenshot_path.exists():
                screenshot_path.unlink()

    async def _enrich_urls_from_dom(self, items: list[ResultItem]) -> list[ResultItem]:
        """Enrich vision-extracted items with URLs by matching titles against the DOM.

        Vision extraction captures titles from screenshots but cannot see href
        attributes. This method queries the DOM for <a> elements, matches them
        to extracted items by title text, and populates the url field.

        Args:
            items: Vision-extracted ResultItems (url=None)

        Returns:
            Same items with url fields populated where matches were found
        """
        if not items:
            return items

        titles = [item.title or "" for item in items]
        titles_json = _json.dumps(titles)

        try:
            # Get the current page URL for resolving relative hrefs
            page_url = await self.client.evaluate("window.location.href") or ""

            # Find all <a> elements with href and visible text, return title→href mapping
            result = await self.client.evaluate(f"""
                (function() {{
                    var titles = {titles_json};
                    var mapping = {{}};
                    // Collect all <a> elements with href
                    var links = document.querySelectorAll('a[href]');
                    // Build a list of candidate link objects
                    var candidates = [];
                    for (var i = 0; i < links.length; i++) {{
                        var a = links[i];
                        var href = a.getAttribute('href');
                        if (!href || href === '#' || href.startsWith('javascript:')) continue;
                        // Get visible text from the link or its children
                        var text = (a.textContent || '').trim();
                        if (!text) continue;
                        var rect = a.getBoundingClientRect();
                        if (rect.width === 0 && rect.height === 0) continue;
                        candidates.push({{text: text, href: href}});
                    }}
                    // For each vision-extracted title, find the best matching link
                    for (var t = 0; t < titles.length; t++) {{
                        var title = titles[t];
                        if (!title) continue;
                        var titleLower = title.toLowerCase().trim();
                        if (!titleLower) continue;
                        var bestHref = null;
                        var bestScore = 0;
                        for (var c = 0; c < candidates.length; c++) {{
                            var cand = candidates[c];
                            var candLower = cand.text.toLowerCase();
                            // Exact match
                            if (candLower === titleLower) {{
                                bestHref = cand.href;
                                bestScore = 100;
                                break;
                            }}
                            // Title contained within link text
                            if (candLower.indexOf(titleLower) !== -1) {{
                                var score = titleLower.length / candLower.length * 80;
                                if (score > bestScore) {{
                                    bestScore = score;
                                    bestHref = cand.href;
                                }}
                            }}
                            // Link text contained within title
                            if (titleLower.indexOf(candLower) !== -1 && candLower.length > 3) {{
                                var score2 = candLower.length / titleLower.length * 70;
                                if (score2 > bestScore) {{
                                    bestScore = score2;
                                    bestHref = cand.href;
                                }}
                            }}
                        }}
                        if (bestHref && bestScore >= 40) {{
                            mapping[t.toString()] = bestHref;
                        }}
                    }}
                    return JSON.stringify(mapping);
                }})()
            """)

            if result and result not in ("null", "undefined", "{}"):
                mapping = _json.loads(result) if isinstance(result, str) else result
                enriched = 0
                for idx_str, href in mapping.items():
                    idx = int(idx_str)
                    if 0 <= idx < len(items) and not items[idx].url:
                        abs_url = urljoin(page_url, href) if page_url else href
                        items[idx].url = abs_url
                        enriched += 1
                if enriched > 0:
                    logger.info(f"Enriched {enriched}/{len(items)} vision items with URLs from DOM")
                else:
                    logger.debug("DOM URL enrichment found no matches")
            else:
                logger.debug("DOM URL enrichment returned no mapping")

        except Exception as e:
            logger.debug(f"DOM URL enrichment failed (non-fatal): {e}")

        return items

    async def check_for_no_results(self) -> bool:
        """Use vision to check if the page shows a no-results message.

        Returns:
            True if the page appears to show no results
        """
        results = await self.extract_results(top_k=1)
        # If extraction returned empty and didn't error, likely no results
        return len(results) == 0
