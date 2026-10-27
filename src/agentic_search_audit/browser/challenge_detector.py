"""CAPTCHA and challenge page detection.

Detects bot-detection challenge pages (Cloudflare, PerimeterX, DataDome, Akamai)
so the orchestrator can avoid extracting garbage results and instead retry with
increased backoff.
"""

import json
import logging
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
]


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
  var selectorHit = null;
  for (var i = 0; i < selectors.length; i++) {{
    try {{ if (document.querySelector(selectors[i])) {{ selectorHit = selectors[i]; break; }} }}
    catch (e) {{}}
  }}
  var iframeHit = null;
  var iframes = document.querySelectorAll('iframe');
  for (var k = 0; k < iframes.length && !iframeHit; k++) {{
    var src = (iframes[k].src || '').toLowerCase();
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
    4. Short body with block keywords

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

    return ChallengeDetection(
        detected=False, challenge_type="none", message="No challenge detected"
    )
