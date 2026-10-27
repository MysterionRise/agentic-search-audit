"""CDP ``Input.dispatchKeyEvent`` parameters for the keys the audit presses."""

from typing import Any

CdpEvent = tuple[str, dict[str, Any]]

#: key -> (windowsVirtualKeyCode, code, text sent with keyDown)
KEY_TABLE: dict[str, tuple[int, str, str | None]] = {
    "Enter": (13, "Enter", "\r"),
    "Escape": (27, "Escape", None),
    "Backspace": (8, "Backspace", None),
    "Tab": (9, "Tab", "\t"),
    "Delete": (46, "Delete", None),
    "ArrowDown": (40, "ArrowDown", None),
    "ArrowUp": (38, "ArrowUp", None),
    "ArrowLeft": (37, "ArrowLeft", None),
    "ArrowRight": (39, "ArrowRight", None),
    "Home": (36, "Home", None),
    "End": (35, "End", None),
    "Space": (32, "Space", " "),
}


def key_events(key: str) -> list[CdpEvent]:
    """keyDown + keyUp events for a named key or a single printable character.

    Enter must carry ``text: "\\r"`` on keyDown, otherwise Chrome generates no keypress
    and forms do not submit.
    """
    if key in KEY_TABLE:
        vk, code, text = KEY_TABLE[key]
        down: dict[str, Any] = {
            "type": "keyDown" if text else "rawKeyDown",
            "key": key,
            "code": code,
            "windowsVirtualKeyCode": vk,
            "nativeVirtualKeyCode": vk,
        }
        if text:
            down["text"] = text
            down["unmodifiedText"] = text
        up = {"type": "keyUp", "key": key, "code": code, "windowsVirtualKeyCode": vk}
        return [("Input.dispatchKeyEvent", down), ("Input.dispatchKeyEvent", up)]
    if len(key) == 1:
        return char_events(key)
    raise ValueError(f"unsupported key: {key!r}")


def char_events(char: str) -> list[CdpEvent]:
    """keyDown (with text) + keyUp for one printable character."""
    down = {"type": "keyDown", "key": char, "text": char, "unmodifiedText": char}
    up = {"type": "keyUp", "key": char}
    return [("Input.dispatchKeyEvent", down), ("Input.dispatchKeyEvent", up)]


def click_events(x: float, y: float) -> list[CdpEvent]:
    """A trusted left click at viewport coordinates."""
    base = {"x": x, "y": y, "button": "left", "clickCount": 1}
    return [
        ("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y}),
        ("Input.dispatchMouseEvent", {"type": "mousePressed", **base}),
        ("Input.dispatchMouseEvent", {"type": "mouseReleased", **base}),
    ]
