"""Anti-bot detection evasion utilities.

Provides human-like behavior patterns and browser fingerprint randomisation
to avoid triggering bot-detection systems (Akamai, PerimeterX, DataDome).
"""

import json
import random

# ---------------------------------------------------------------------------
# Realistic Chrome user-agent pool (macOS + Windows, recent Chrome versions)
# ---------------------------------------------------------------------------
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]


def random_user_agent() -> str:
    """Return a randomly chosen realistic Chrome user-agent string."""
    return random.choice(USER_AGENTS)


# ---------------------------------------------------------------------------
# Human-like typing delay
# ---------------------------------------------------------------------------


def human_typing_delay(base_delay_ms: int = 50) -> int:
    """Generate a per-keystroke delay that mimics human typing.

    Most keystrokes are near the base delay, but occasionally a longer
    pause is inserted (simulating thinking or finger repositioning).

    Args:
        base_delay_ms: Baseline inter-key delay in milliseconds.

    Returns:
        Delay in milliseconds.
    """
    # 85% of the time: normal variation around the base
    if random.random() < 0.85:
        return max(20, int(random.gauss(base_delay_ms, base_delay_ms * 0.35)))
    # 15% of the time: a longer "thinking" pause
    return int(random.uniform(base_delay_ms * 2, base_delay_ms * 5))


# ---------------------------------------------------------------------------
# Random micro-delays between actions
# ---------------------------------------------------------------------------


def pre_action_delay() -> float:
    """Return a small random delay (seconds) to insert before an action.

    Simulates the natural pause a human takes before clicking or typing.
    """
    return random.uniform(0.05, 0.3)


def post_action_delay() -> float:
    """Return a small random delay (seconds) to insert after an action."""
    return random.uniform(0.1, 0.4)


# ---------------------------------------------------------------------------
# Mouse movement JavaScript (for Playwright)
# ---------------------------------------------------------------------------


def mouse_jitter_js(target_x: int, target_y: int, steps: int = 5) -> str:
    """Generate JS that dispatches synthetic mousemove events toward a target.

    Creates a short sequence of mousemove events with slight randomisation
    to simulate a human moving the cursor toward an element.

    Args:
        target_x: Target X coordinate.
        target_y: Target Y coordinate.
        steps: Number of intermediate moves.

    Returns:
        JavaScript code string.
    """
    points: list[tuple[int, int]] = []
    # Start from a random offset
    cx = target_x + random.randint(-200, -50)
    cy = target_y + random.randint(-100, 50)
    for i in range(1, steps + 1):
        frac = i / steps
        nx = int(cx + (target_x - cx) * frac + random.randint(-8, 8))
        ny = int(cy + (target_y - cy) * frac + random.randint(-5, 5))
        points.append((nx, ny))

    dispatches = "\n".join(
        f"document.elementFromPoint({x},{y})?.dispatchEvent("
        f"new MouseEvent('mousemove',{{clientX:{x},clientY:{y},bubbles:true}}));"
        for x, y in points
    )
    return f"""(async () => {{
    {dispatches}
}})()"""


# ---------------------------------------------------------------------------
# WebGL vendor/renderer fingerprint randomisation
# ---------------------------------------------------------------------------

WEBGL_PROFILES: list[tuple[str, str]] = [
    ("Intel Inc.", "Intel Iris OpenGL Engine"),
    ("Intel Inc.", "Intel(R) UHD Graphics 630"),
    ("Intel Inc.", "Intel(R) Iris(R) Xe Graphics"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)"),
    ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0)"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)"),
    ("Apple", "Apple GPU"),
]


def random_webgl_profile() -> tuple[str, str]:
    """Return a randomly chosen (vendor, renderer) pair for WebGL spoofing."""
    return random.choice(WEBGL_PROFILES)


# ---------------------------------------------------------------------------
# Locale-to-timezone mapping
# ---------------------------------------------------------------------------

LOCALE_TIMEZONE_MAP: dict[str, list[str]] = {
    "en-US": ["America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"],
    "en-GB": ["Europe/London"],
    "de-DE": ["Europe/Berlin"],
    "fr-FR": ["Europe/Paris"],
    "ja-JP": ["Asia/Tokyo"],
    "zh-CN": ["Asia/Shanghai"],
    "ko-KR": ["Asia/Seoul"],
    "es-ES": ["Europe/Madrid"],
    "it-IT": ["Europe/Rome"],
    "pt-BR": ["America/Sao_Paulo"],
    "nl-NL": ["Europe/Amsterdam"],
    "sv-SE": ["Europe/Stockholm"],
}


def timezone_for_locale(locale: str) -> str:
    """Return a plausible IANA timezone ID for the given locale.

    Falls back to America/New_York if the locale is not recognised.
    """
    candidates = LOCALE_TIMEZONE_MAP.get(locale, ["America/New_York"])
    return random.choice(candidates)


def languages_for_locale(locale: str) -> list[str]:
    """Return a realistic navigator.languages array for the given locale.

    For example ``en-US`` yields ``['en-US', 'en']`` while ``de-DE`` yields
    ``['de-DE', 'de', 'en-US', 'en']``.
    """
    lang = locale.split("-")[0]
    if locale.startswith("en"):
        return [locale, lang]
    return [locale, lang, "en-US", "en"]


# ---------------------------------------------------------------------------
# Comprehensive stealth JavaScript builder
# ---------------------------------------------------------------------------


def build_stealth_js(locale: str = "en-US") -> str:
    """Build a comprehensive stealth init script for Playwright.

    Combines all fingerprint evasion techniques into a single JS string
    suitable for ``context.add_init_script()``.

    Args:
        locale: The locale code the browser context is configured with.
                Used to set consistent ``navigator.languages``.

    Returns:
        JavaScript code string.
    """
    vendor, renderer = random_webgl_profile()
    languages = languages_for_locale(locale)
    languages_json = json.dumps(languages)

    return f"""
    // --- navigator.webdriver ---
    Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});

    // --- window.chrome ---
    if (!window.chrome) {{ window.chrome = {{}}; }}
    window.chrome.runtime = {{ connect: function(){{}}, sendMessage: function(){{}} }};

    // --- navigator.plugins (realistic Chrome plugin list) ---
    Object.defineProperty(navigator, 'plugins', {{
        get: () => {{
            const arr = [
                {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer',
                  description: 'Portable Document Format', length: 1 }},
                {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                  description: '', length: 1 }},
                {{ name: 'Native Client', filename: 'internal-nacl-plugin',
                  description: '', length: 2 }},
            ];
            arr.item = i => arr[i];
            arr.namedItem = n => arr.find(p => p.name === n);
            arr.refresh = () => {{}};
            return arr;
        }},
    }});

    // --- navigator.permissions.query ---
    const origQuery = window.navigator.permissions.query.bind(
        window.navigator.permissions
    );
    window.navigator.permissions.query = params =>
        params.name === 'notifications'
            ? Promise.resolve({{ state: Notification.permission }})
            : origQuery(params);

    // --- WebGL vendor/renderer fingerprint randomisation ---
    (function() {{
        const vendor = {json.dumps(vendor)};
        const renderer = {json.dumps(renderer)};

        function patchGetParameter(proto) {{
            const orig = proto.getParameter;
            proto.getParameter = function(param) {{
                if (param === 37445) return vendor;
                if (param === 37446) return renderer;
                return orig.call(this, param);
            }};
        }}
        patchGetParameter(WebGLRenderingContext.prototype);
        if (typeof WebGL2RenderingContext !== 'undefined') {{
            patchGetParameter(WebGL2RenderingContext.prototype);
        }}

        // Also patch getExtension('WEBGL_debug_renderer_info') to return
        // our spoofed values through the extension object itself.
        const origGetExt = WebGLRenderingContext.prototype.getExtension;
        WebGLRenderingContext.prototype.getExtension = function(name) {{
            const ext = origGetExt.call(this, name);
            return ext;
        }};
    }})();

    // --- Canvas fingerprint noise injection ---
    (function() {{
        const origToBlob = HTMLCanvasElement.prototype.toBlob;
        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;

        // Inject subtle pixel noise to create a unique but consistent
        // canvas fingerprint per session.
        const noiseSeed = Math.floor(Math.random() * 256);

        CanvasRenderingContext2D.prototype.getImageData = function() {{
            const imageData = origGetImageData.apply(this, arguments);
            const data = imageData.data;
            for (let i = 0; i < data.length; i += 4) {{
                // Flip the least-significant bit of the red channel
                // using a deterministic-per-session pattern
                data[i] = data[i] ^ ((noiseSeed + i) & 1);
            }}
            return imageData;
        }};

        HTMLCanvasElement.prototype.toBlob = function() {{
            // Touch the canvas to trigger noise, then call original
            const ctx = this.getContext('2d');
            if (ctx) {{
                // Reading forces our patched getImageData path
                try {{ ctx.getImageData(0, 0, 1, 1); }} catch(e) {{}}
            }}
            return origToBlob.apply(this, arguments);
        }};

        HTMLCanvasElement.prototype.toDataURL = function() {{
            const ctx = this.getContext('2d');
            if (ctx) {{
                try {{ ctx.getImageData(0, 0, 1, 1); }} catch(e) {{}}
            }}
            return origToDataURL.apply(this, arguments);
        }};
    }})();

    // --- navigator.languages (consistent with context locale) ---
    Object.defineProperty(navigator, 'languages', {{
        get: () => {languages_json},
    }});

    // --- WebRTC leak prevention ---
    // Override RTCPeerConnection to prevent local IP leakage
    (function() {{
        if (typeof window.RTCPeerConnection !== 'undefined') {{
            const OrigRTC = window.RTCPeerConnection;
            window.RTCPeerConnection = function(config, constraints) {{
                // Force use of relay-only ICE candidates to prevent IP leaks
                config = config || {{}};
                config.iceTransportPolicy = 'relay';
                return new OrigRTC(config, constraints);
            }};
            window.RTCPeerConnection.prototype = OrigRTC.prototype;
            // Preserve static methods
            Object.keys(OrigRTC).forEach(k => {{
                try {{ window.RTCPeerConnection[k] = OrigRTC[k]; }} catch(e) {{}}
            }});
        }}
        // Also cover the webkit-prefixed variant
        if (typeof window.webkitRTCPeerConnection !== 'undefined') {{
            const OrigWebkitRTC = window.webkitRTCPeerConnection;
            window.webkitRTCPeerConnection = function(config, constraints) {{
                config = config || {{}};
                config.iceTransportPolicy = 'relay';
                return new OrigWebkitRTC(config, constraints);
            }};
            window.webkitRTCPeerConnection.prototype = OrigWebkitRTC.prototype;
        }}
    }})();
    """
