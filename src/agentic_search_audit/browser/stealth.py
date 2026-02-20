"""Anti-bot detection evasion utilities.

Provides human-like behavior patterns and browser fingerprint randomisation
to avoid triggering bot-detection systems (Akamai, PerimeterX, DataDome).
"""

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
