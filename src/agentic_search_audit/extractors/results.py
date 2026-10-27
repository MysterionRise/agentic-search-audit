"""Search results extraction.

The whole result list is read in ONE ``evaluate`` call (``EXTRACT_RESULTS_JS``): the
configured selectors are passed in as JSON, the script finds the first item selector
that matches, and returns the top-K items with their title, URL, snippet, price and
image. One round trip per query instead of one per field per item matters for the
bridge backends, where every ``evaluate`` is a tool call.
"""

import json
import logging
from typing import Final
from urllib.parse import urljoin, urlparse

from ..browser._js import coerce_int
from ..core.types import BrowserClient, JsValue, ResultItem, ResultsConfig

logger = logging.getLogger(__name__)

DEFAULT_MAX_TEXT_CHARS: Final = 500
"""Per-field cap on extracted text, so one noisy card cannot blow up the payload."""

EXTRACT_RESULTS_JS: Final = r"""(function(cfg) {
  function q(parent, sel) {
    try { return parent.querySelector(sel); } catch (e) { return null; }
  }
  function firstText(parent, sels) {
    for (var i = 0; i < sels.length; i++) {
      var el = q(parent, sels[i]);
      if (!el) continue;
      var t = (el.textContent || '').replace(/\s+/g, ' ').trim();
      if (t) return t.slice(0, cfg.maxTextChars);
    }
    return null;
  }
  function firstAttr(parent, sels, attrs) {
    for (var i = 0; i < sels.length; i++) {
      var el = q(parent, sels[i]);
      if (!el) continue;
      for (var j = 0; j < attrs.length; j++) {
        var v = el.getAttribute(attrs[j]);
        if (v) return v.slice(0, cfg.maxTextChars);
      }
    }
    return null;
  }
  var nodes = null, used = null, total = 0;
  for (var s = 0; s < cfg.itemSelectors.length; s++) {
    var found;
    try { found = document.querySelectorAll(cfg.itemSelectors[s]); } catch (e) { continue; }
    if (found.length) {
      nodes = Array.prototype.slice.call(found, 0, cfg.topK);
      used = cfg.itemSelectors[s];
      total = found.length;
      break;
    }
  }
  if (!nodes) return {selector: null, total: 0, items: []};
  return {selector: used, total: total, items: nodes.map(function(p, i) {
    var url = cfg.urlAttr ? p.getAttribute(cfg.urlAttr) : null;
    if (!url) {
      var a = (p.matches && p.matches('a[href]')) ? p : q(p, 'a[href]');
      url = a ? a.getAttribute('href') : null;
    }
    return {
      index: i,
      title: firstText(p, cfg.titleSelectors),
      url: url,
      snippet: firstText(p, cfg.snippetSelectors),
      price: firstText(p, cfg.priceSelectors),
      image: firstAttr(p, cfg.imageSelectors, ['src', 'data-src'])
    };
  })};
})(__CFG__)"""


def build_extract_results_js(
    config: ResultsConfig, top_k: int, max_text_chars: int = DEFAULT_MAX_TEXT_CHARS
) -> str:
    """Return ``EXTRACT_RESULTS_JS`` with the selector config embedded as JSON.

    ``json.dumps`` output is valid JavaScript literal syntax, so selectors containing
    quotes or backslashes are safe.
    """
    cfg = {
        "itemSelectors": list(config.item_selectors),
        "titleSelectors": list(config.title_selectors),
        "snippetSelectors": list(config.snippet_selectors),
        "priceSelectors": list(config.price_selectors),
        "imageSelectors": list(config.image_selectors),
        "urlAttr": config.url_attr,
        "topK": top_k,
        "maxTextChars": max_text_chars,
    }
    return EXTRACT_RESULTS_JS.replace("__CFG__", json.dumps(cfg))


def _text(value: JsValue) -> str | None:
    """A non-empty string from a JS field, else None."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


class ResultsExtractor:
    """Extracts search results from the page."""

    def __init__(self, client: BrowserClient, config: ResultsConfig, base_url: str):
        """Initialize results extractor.

        Args:
            client: Browser client
            config: Results configuration
            base_url: Base URL for resolving relative URLs
        """
        self.client = client
        self.config = config
        self.base_url = base_url

    async def count_visible_results(self) -> int:
        """Count visible result items on the page without full extraction.

        Returns:
            Number of matching result items currently in the DOM.
        """
        for selector in self.config.item_selectors:
            script = f"document.querySelectorAll({json.dumps(selector)}).length"
            try:
                count = coerce_int(await self.client.evaluate(script))
            except Exception as e:
                logger.debug(f"Counting '{selector}' failed: {e}")
                continue
            if count > 0:
                return count
        return 0

    async def extract_results(self, top_k: int = 10) -> list[ResultItem]:
        """Extract top-K search results from the page in one round trip.

        Args:
            top_k: Maximum number of results to extract

        Returns:
            List of result items
        """
        logger.info(f"Extracting top {top_k} search results...")

        try:
            raw = await self.client.evaluate(build_extract_results_js(self.config, top_k))
        except Exception as e:
            logger.warning(f"Result extraction script failed: {e}")
            return []

        entries = raw.get("items") if isinstance(raw, dict) else None
        if not isinstance(entries, list) or not entries:
            logger.warning("No result items found")
            return []

        selector = raw.get("selector") if isinstance(raw, dict) else None
        total = coerce_int(raw.get("total")) if isinstance(raw, dict) else len(entries)
        logger.info(f"Found {total} items with selector: {selector}")

        results: list[ResultItem] = []
        for rank, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                continue
            results.append(self._to_result_item(rank, entry))

        logger.info(f"Successfully extracted {len(results)} results")
        return results

    def _to_result_item(self, rank: int, entry: dict[str, JsValue]) -> ResultItem:
        """Build a ``ResultItem`` from one entry of the extraction script's output."""
        attributes: dict[str, str] = {}

        url = _text(entry.get("url"))
        if url:
            url = urljoin(self.base_url, url)
            parsed_url = urlparse(url)
            if parsed_url.scheme not in ("http", "https", ""):
                logger.warning(f"Result {rank}: invalid URL scheme '{parsed_url.scheme}': {url}")
                url = None
            elif parsed_url.netloc:
                # Flag off-domain URLs (ad network links etc.), allowing subdomains.
                base_netloc = urlparse(self.base_url).netloc
                if base_netloc and parsed_url.netloc != base_netloc:
                    base_domain = ".".join(base_netloc.split(".")[-2:])
                    url_domain = ".".join(parsed_url.netloc.split(".")[-2:])
                    if base_domain != url_domain:
                        attributes["url_off_domain"] = "true"
                        logger.debug(
                            f"Result {rank}: off-domain URL detected:"
                            f" {parsed_url.netloc}"
                            f" (expected: {base_netloc})"
                        )

        image = _text(entry.get("image"))
        if image:
            image = urljoin(self.base_url, image)

        return ResultItem(
            rank=rank,
            title=_text(entry.get("title")),
            url=url,
            snippet=_text(entry.get("snippet")),
            price=_text(entry.get("price")),
            image=image,
            attributes=attributes,
        )

    async def check_for_no_results(self) -> bool:
        """Check if page shows a 'no results' message.

        Uses site-specific ``no_results_selectors`` when configured.
        Otherwise falls back to a heuristic text search scoped to the
        main content area (``main``, ``[role=main]``, ``#content``,
        ``.content``) to avoid false positives from footer / FAQ text.
        If no content container is found, searches ``document.body`` but
        excludes ``<header>``, ``<footer>``, and ``<nav>`` elements.

        Returns:
            True if a no-results indicator is detected.
        """
        # --- Strategy 1: explicit selectors from config ---
        if self.config.no_results_selectors:
            for selector in self.config.no_results_selectors:
                script = f"""
                (function() {{
                    var el = document.querySelector({json.dumps(selector)});
                    if (!el) return false;
                    var style = window.getComputedStyle(el);
                    return style.display !== 'none' && style.visibility !== 'hidden';
                }})()
                """
                result = await self.client.evaluate(script)
                if result is True:
                    logger.info(f"Detected no-results element via selector: '{selector}'")
                    return True
            return False

        # --- Strategy 2: heuristic text search, scoped to content area ---
        no_results_patterns = [
            "no results",
            "no items found",
            "0 results",
            "nothing found",
            "try a different search",
        ]

        # Build a JS snippet that extracts text only from the main
        # content area, excluding header/footer/nav.
        scope_script = """
        (function() {
            var container = document.querySelector('main, [role="main"], #content, .content');
            if (container) return container.textContent.toLowerCase().slice(0, 50000);
            // Fallback: body text minus header/footer/nav
            var clone = document.body.cloneNode(true);
            var exclude = clone.querySelectorAll('header, footer, nav, [role="banner"], [role="contentinfo"], [role="navigation"]');
            for (var i = 0; i < exclude.length; i++) exclude[i].remove();
            return clone.textContent.toLowerCase().slice(0, 50000);
        })()
        """

        scoped_text = await self.client.evaluate(scope_script)
        if not isinstance(scoped_text, str) or not scoped_text:
            return False

        scoped_text_lower = scoped_text.lower()
        for pattern in no_results_patterns:
            if pattern in scoped_text_lower:
                logger.info(f"Detected no results message: '{pattern}'")
                return True

        return False
