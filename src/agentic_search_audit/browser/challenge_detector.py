"""CAPTCHA and challenge page detection.

Detects bot-detection challenge pages (Cloudflare, PerimeterX, DataDome, Akamai)
so the orchestrator can avoid extracting garbage results and instead retry with
increased backoff.
"""

import logging
from dataclasses import dataclass

from ..core.types import BrowserClient

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


async def detect_challenge(client: BrowserClient) -> ChallengeDetection:
    """Check whether the current page is a bot-detection challenge.

    Runs multiple heuristics against the current page:
    1. Page title matches known challenge strings
    2. Known challenge-page CSS selectors exist
    3. CAPTCHA iframes present
    4. Short body with block keywords

    Args:
        client: Active browser client with a loaded page.

    Returns:
        ChallengeDetection with detection result.
    """
    # 1. Check page title
    try:
        title = await client.evaluate("document.title")
        if title:
            title_lower = str(title).lower()
            for pattern in CHALLENGE_TITLE_PATTERNS:
                if pattern in title_lower:
                    msg = f"Challenge page detected via title: '{title}'"
                    logger.warning(msg)
                    return ChallengeDetection(
                        detected=True,
                        challenge_type="title_match",
                        message=msg,
                    )
    except Exception as e:
        logger.debug(f"Title check failed: {e}")

    # 2. Check for known challenge selectors
    for selector in CHALLENGE_SELECTORS:
        try:
            el = await client.query_selector(selector)
            if el:
                msg = f"Challenge page detected via selector: {selector}"
                logger.warning(msg)
                return ChallengeDetection(
                    detected=True,
                    challenge_type="selector_match",
                    message=msg,
                )
        except Exception:
            continue

    # 3. Check for CAPTCHA iframes
    try:
        patterns_json = str(CAPTCHA_IFRAME_PATTERNS).replace("'", '"')
        iframe_check_js = (
            "(function() {"
            "  var iframes = document.querySelectorAll('iframe');"
            "  for (var i = 0; i < iframes.length; i++) {"
            "    var src = (iframes[i].src || '').toLowerCase();"
            f"    var patterns = {patterns_json};"
            "    for (var j = 0; j < patterns.length; j++) {"
            "      if (src.indexOf(patterns[j]) !== -1) {"
            "        return patterns[j];"
            "      }"
            "    }"
            "  }"
            "  return '';"
            "})()"
        )
        result = await client.evaluate(iframe_check_js)
        if result and str(result).strip():
            msg = f"CAPTCHA iframe detected: {result}"
            logger.warning(msg)
            return ChallengeDetection(
                detected=True,
                challenge_type="captcha_iframe",
                message=msg,
            )
    except Exception as e:
        logger.debug(f"Iframe check failed: {e}")

    # 4. Short body with block keywords
    try:
        body_info = await client.evaluate(
            "(function() {"
            "  var body = document.body;"
            "  if (!body) return JSON.stringify({len: 0, text: ''});"
            "  var text = body.innerText || '';"
            "  return JSON.stringify({len: text.length, text: text.substring(0, 1000)});"
            "})()"
        )
        if body_info:
            import json

            try:
                info = json.loads(str(body_info))
                body_len = info.get("len", 0)
                body_text = info.get("text", "").lower()

                if body_len < 500:
                    for keyword in BLOCK_KEYWORDS:
                        if keyword in body_text:
                            msg = (
                                f"Possible block page: body length {body_len} chars "
                                f"with keyword '{keyword}'"
                            )
                            logger.warning(msg)
                            return ChallengeDetection(
                                detected=True,
                                challenge_type="short_body_block",
                                message=msg,
                            )
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception as e:
        logger.debug(f"Body text check failed: {e}")

    return ChallengeDetection(
        detected=False,
        challenge_type="none",
        message="No challenge detected",
    )
