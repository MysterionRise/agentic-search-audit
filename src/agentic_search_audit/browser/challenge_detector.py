"""CAPTCHA and challenge page detection.

Detects bot-detection challenge pages (Cloudflare, PerimeterX, DataDome, Akamai)
so the orchestrator can avoid extracting garbage results and instead retry with
increased backoff.
"""

import json
import logging
import re
from dataclasses import dataclass

from ..core.types import BrowserClient
from ._js import coerce_int

logger = logging.getLogger(__name__)

# Page title strings that indicate a challenge/block page
CHALLENGE_TITLE_PATTERNS: list[str] = [
    "just a moment",
    "verify you are human",
    "access denied",
    "attention required",
    "please verify",
    "security check",
    "pardon our interruption",
    "before you continue",
    "blocked",
    "you have been blocked",
    "error 403",
    "error 1015",
    "error 1020",
]

# CSS selectors for known challenge page elements
CHALLENGE_SELECTORS: list[str] = [
    "#challenge-running",
    "#challenge-stage",
    ".cf-browser-verification",
    "#cf-challenge-running",
    "#px-captcha",
    "[data-testid='challenge']",
    "#distil_identify_cookie_block",
    "#sec-overlay",
    "#datadome",
    ".g-recaptcha",
    "#captcha-form",
    ".h-captcha",
]

# CAPTCHA iframe src patterns
CAPTCHA_IFRAME_PATTERNS: list[str] = [
    "captcha",
    "challenge",
    "recaptcha",
    "hcaptcha",
    "turnstile",
    "_incapsula_resource",  # Imperva's block interstitial (boots.com)
]

# Keywords in page body that suggest a block page (used when body is short)
BLOCK_KEYWORDS: list[str] = [
    "ray id",
    "cloudflare",
    "captcha",
    "bot detection",
    "automated access",
    "unusual traffic",
    "access to this page has been denied",
    "perimeterx",
    "datadome",
    "please enable cookies",
    "enable javascript",
    "incapsula",
]

# Short pages that turn visitors from another country away. Seen from a UK IP on
# 2026-11-04: jcpenney.com, gap.com's franchise redirect, bestbuy.com's country splash.
GEO_BLOCK_KEYWORDS: list[str] = [
    "unable to provide a shopping experience for this country",
    "not available in your country",
    "not available in your region",
    "does not support shipping outside",
    "choose a country",
]

# Akamai edge error pages carry a reference ID instead of a vendor name: eBay's
# "SORRY / Something went wrong on our end" shows "0.afe41602.1793671333.12568738",
# Akamai's "Access Denied" shows "Reference #18.2f7d1402.1793671333.1a2b3c4".
EDGE_REFERENCE_RE = re.compile(r"\b\d{1,3}\.[0-9a-f]{8}\.\d{10}\.[0-9a-f]{6,10}\b")


@dataclass
class ChallengeDetection:
    """Result of challenge page detection."""

    detected: bool
    challenge_type: str
    message: str


class ChallengeDetectedError(Exception):
    """Raised when a bot-detection challenge page is detected."""

    def __init__(self, detection: ChallengeDetection):
        self.detection = detection
        super().__init__(detection.message)


def _probe_js() -> str:
    """One in-page probe for every heuristic: title, known selectors, CAPTCHA iframes, body."""
    return f"""(function() {{
  var selectors = {json.dumps(CHALLENGE_SELECTORS)};
  var patterns = {json.dumps(CAPTCHA_IFRAME_PATTERNS)};
  // Only what is rendered counts: Akamai keeps a hidden #sec-overlay on ordinary pages
  // (gap, kohls, lowes, adidas) and invisible reCAPTCHA leaves 0x0 iframes (sephora).
  function shown(el) {{
    var r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width >= 20 && r.height >= 20 && s.visibility !== 'hidden' &&
      parseFloat(s.opacity || '1') > 0.05;
  }}
  var selectorHit = null;
  for (var i = 0; i < selectors.length && !selectorHit; i++) {{
    var found;
    try {{ found = document.querySelectorAll(selectors[i]); }} catch (e) {{ continue; }}
    for (var m = 0; m < found.length; m++) {{
      if (shown(found[m])) {{ selectorHit = selectors[i]; break; }}
    }}
  }}
  var iframeHit = null;
  var iframes = document.querySelectorAll('iframe');
  for (var k = 0; k < iframes.length && !iframeHit; k++) {{
    if (!shown(iframes[k])) continue;
    // The raw attribute too: a relative src may not resolve (Imperva serves "/_Incapsula_Resource")
    var src = ((iframes[k].getAttribute('src') || '') + ' ' + (iframes[k].src || '')).toLowerCase();
    for (var j = 0; j < patterns.length; j++) {{
      if (src.indexOf(patterns[j]) !== -1) {{ iframeHit = patterns[j]; break; }}
    }}
  }}
  var text = document.body ? (document.body.innerText || '') : '';
  return {{title: document.title || '', selector: selectorHit, iframe: iframeHit,
          bodyLen: text.length, bodyText: text.substring(0, 1000)}};
}})()"""


async def detect_challenge(client: BrowserClient) -> ChallengeDetection:
    """Check whether the current page is a bot-detection challenge.

    One ``evaluate`` call collects the signals, then four heuristics run on them:
    1. Page title matches known challenge strings
    2. Known challenge-page CSS selectors exist
    3. CAPTCHA iframes present
    4. Short body with block keywords or an edge (Akamai) reference ID
    5. Short body that turns visitors from another country away (``geo_block``)

    Selectors and iframes count only when rendered, since several vendors keep hidden
    challenge elements on ordinary pages.

    Args:
        client: Active browser client with a loaded page.

    Returns:
        ChallengeDetection with detection result.
    """
    try:
        probe = await client.evaluate(_probe_js())
    except Exception as e:
        logger.debug(f"Challenge probe failed: {e}")
        probe = None
    if not isinstance(probe, dict):
        return ChallengeDetection(
            detected=False, challenge_type="none", message="No challenge detected"
        )

    title = probe.get("title")
    if isinstance(title, str) and title:
        title_lower = title.lower()
        for pattern in CHALLENGE_TITLE_PATTERNS:
            if pattern in title_lower:
                msg = f"Challenge page detected via title: '{title}'"
                logger.warning(msg)
                return ChallengeDetection(detected=True, challenge_type="title_match", message=msg)

    selector = probe.get("selector")
    if isinstance(selector, str) and selector:
        msg = f"Challenge page detected via selector: {selector}"
        logger.warning(msg)
        return ChallengeDetection(detected=True, challenge_type="selector_match", message=msg)

    iframe = probe.get("iframe")
    if isinstance(iframe, str) and iframe:
        msg = f"CAPTCHA iframe detected: {iframe}"
        logger.warning(msg)
        return ChallengeDetection(detected=True, challenge_type="captcha_iframe", message=msg)

    body_len = coerce_int(probe.get("bodyLen"))
    text_value = probe.get("bodyText")
    body_text = text_value.lower() if isinstance(text_value, str) else ""
    if body_len < 500:
        for keyword in BLOCK_KEYWORDS:
            if keyword in body_text:
                msg = f"Possible block page: body length {body_len} chars with keyword '{keyword}'"
                logger.warning(msg)
                return ChallengeDetection(
                    detected=True, challenge_type="short_body_block", message=msg
                )
        reference = EDGE_REFERENCE_RE.search(body_text)
        if reference:
            msg = f"Edge block page: body length {body_len} chars, reference {reference.group(0)}"
            logger.warning(msg)
            return ChallengeDetection(detected=True, challenge_type="edge_block", message=msg)

    if body_len < 1500:
        for keyword in GEO_BLOCK_KEYWORDS:
            if keyword in body_text:
                msg = (
                    f"Region block: body length {body_len} chars with '{keyword}' "
                    "(the site turns this country away; use a proxy in the site's country)"
                )
                logger.warning(msg)
                return ChallengeDetection(detected=True, challenge_type="geo_block", message=msg)

    return ChallengeDetection(
        detected=False, challenge_type="none", message="No challenge detected"
    )
