"""Shared JavaScript evaluation helpers.

Every browser backend runs page scripts through :func:`wrap_expression` and decodes
the result with :func:`decode_result`, so ``BrowserClient.evaluate`` returns the same
Python value for the same JavaScript result no matter which backend produced it.

The wrapper evaluates the expression inside an IIFE and returns a JSON *envelope*
string::

    {"ok": true, "v": <JSON-serialised result>}
    {"ok": false, "kind": "...", "name": "...", "message": "...", "stack": "..."}

``undefined`` is omitted by ``JSON.stringify`` and therefore decodes to ``None``.
"""

import json
from typing import Final, cast

from ..core.types import JsValue
from .errors import BrowserScriptError

MAX_RESULT_CHARS: Final = 2_000_000
"""Serialised results larger than this raise ``payload_too_large`` instead of being
truncated somewhere in the transport."""

# The expression is substituted on its own line inside ``( ... )`` so that a trailing
# ``//`` comment cannot swallow the closing parenthesis and so that the old Selenium
# automatic-semicolon-insertion bug (``return\n42``) cannot happen.
_WRAPPER: Final = """(() => {
  const __rep = (k, v) => {
    if (typeof v === 'bigint') return v.toString();
    if (typeof v === 'number' && !Number.isFinite(v)) return null;
    if (v && typeof v === 'object') {
      if (typeof v.nodeType === 'number' && typeof v.nodeName === 'string') {
        return {__node__: v.nodeName, id: v.id || null,
                className: (typeof v.className === 'string' && v.className) ? v.className : null};
      }
      if (typeof v.length === 'number' && typeof v.item === 'function') return Array.from(v);
      if (v instanceof Map) return Array.from(v.entries());
      if (v instanceof Set) return Array.from(v);
    }
    return v;
  };
  const __err = (kind, e) => JSON.stringify({ok: false, kind: kind,
    name: (e && e.name) || 'Error', message: (e && e.message) || String(e),
    stack: (e && e.stack) || null});
  let __r;
  try {
    __r = (
__EXPR__
    );
  } catch (e) { return __err('script', e); }
  if (__r && typeof __r.then === 'function') {
    return __err('unsupported_promise', {name: 'UnsupportedPromise',
      message: 'evaluate() does not await promises; return a plain value'});
  }
  let __s;
  try { __s = JSON.stringify({ok: true, v: __r}, __rep); }
  catch (e) { return __err('serialization', e); }
  if (__s.length > __MAX__) {
    return __err('payload_too_large', {name: 'PayloadTooLarge',
      message: 'result is ' + __s.length + ' chars (limit __MAX__)'});
  }
  return __s;
})()"""


def wrap_expression(expression: str, *, max_chars: int = MAX_RESULT_CHARS) -> str:
    """Wrap a synchronous JavaScript expression so it returns the JSON envelope.

    Args:
        expression: A JavaScript *expression* (IIFEs are fine; statement lists are not).
            Surrounding whitespace and trailing semicolons are ignored.
        max_chars: Cap on the serialised result length.

    Returns:
        A self-contained JavaScript expression that evaluates to the envelope string.

    Raises:
        ValueError: If the expression is empty.
    """
    expr = expression.strip()
    while expr.endswith(";"):
        expr = expr[:-1].rstrip()
    if not expr:
        raise ValueError("evaluate() needs a non-empty JavaScript expression")
    # __MAX__ first so a (pathological) "__MAX__" inside the expression is left alone.
    return _WRAPPER.replace("__MAX__", str(max_chars)).replace("__EXPR__", expr)


def decode_result(raw: object) -> JsValue:
    """Turn the backend's raw return value into the JavaScript result.

    Args:
        raw: The envelope as a JSON string (Playwright, Selenium) or as an
            already-decoded ``dict`` (transports that JSON-decode on their own).

    Returns:
        The JavaScript result as a ``JsValue``.

    Raises:
        BrowserScriptError: For every ``ok: false`` envelope, and with
            ``kind="decode"`` when ``raw`` is not an envelope at all.
    """
    if isinstance(raw, str):
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BrowserScriptError(
                "decode", f"evaluate() returned non-JSON text: {raw[:200]!r}"
            ) from exc
    elif isinstance(raw, dict):
        envelope = raw
    else:
        raise BrowserScriptError(
            "decode", f"evaluate() returned {type(raw).__name__}, expected the JSON envelope"
        )

    if not isinstance(envelope, dict) or "ok" not in envelope:
        raise BrowserScriptError("decode", "evaluate() result is not a JSON envelope")

    if envelope.get("ok") is True:
        return cast(JsValue, envelope.get("v"))

    stack = envelope.get("stack")
    raise BrowserScriptError(
        str(envelope.get("kind") or "script"),
        str(envelope.get("message") or "unknown script error"),
        name=str(envelope.get("name") or "Error"),
        stack=stack if isinstance(stack, str) else None,
    )


def coerce_int(value: JsValue, default: int = 0) -> int:
    """Best-effort integer from a JavaScript result (element counts and the like).

    Booleans, non-numeric strings and containers give ``default``.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default
