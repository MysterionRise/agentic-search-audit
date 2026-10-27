"""JavaScript function sources used by ``BridgeBrowserClient``.

Every function returns the source of a JS *function* (``() => {...}`` or
``async () => {...}``) so transports can pass it straight to their evaluate tool.
Selectors and other values are embedded with ``json.dumps``.
"""

import json


def function_from_expression(expression: str) -> str:
    """Wrap an expression (for example the envelope IIFE) as a function."""
    return "() => { return (\n" + expression + "\n); }"


def current_url() -> str:
    return "() => window.location.href"


def document_html() -> str:
    return "() => document.documentElement.outerHTML"


def document_ready_state() -> str:
    return "() => document.readyState"


_VISIBLE = """
  function __visible(el) {
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  }"""


def query_selector_info(selector: str) -> str:
    return f"""() => {{{_VISIBLE}
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return {{exists: true, tag: el.tagName.toLowerCase(), visible: __visible(el),
          rect: {{x: r.x, y: r.y, width: r.width, height: r.height}}}};
}}"""


def query_selector_all_info(selector: str, limit: int = 200) -> str:
    return f"""() => Array.from(document.querySelectorAll({json.dumps(selector)}))
  .slice(0, {int(limit)})
  .map((el, i) => ({{index: i, tag: el.tagName.toLowerCase(),
                     text: (el.textContent || '').trim().slice(0, 80)}}))"""


def element_center(selector: str) -> str:
    """Scroll the element into view and return its viewport centre, or null."""
    return f"""() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return null;
  el.scrollIntoView({{block: 'center', inline: 'center'}});
  const r = el.getBoundingClientRect();
  if (!(r.width > 0 && r.height > 0)) return null;
  return {{x: r.x + r.width / 2, y: r.y + r.height / 2, width: r.width, height: r.height}};
}}"""


def synthetic_click(selector: str) -> str:
    return f"""() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return false;
  el.scrollIntoView({{block: 'center', inline: 'center'}});
  const r = el.getBoundingClientRect();
  const init = {{bubbles: true, cancelable: true, clientX: r.x + r.width / 2,
                clientY: r.y + r.height / 2}};
  for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup']) {{
    el.dispatchEvent(new MouseEvent(type, init));
  }}
  el.click();
  return true;
}}"""


def focus_element(selector: str) -> str:
    return f"""() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return false;
  el.focus();
  return document.activeElement === el;
}}"""


def clear_input(selector: str) -> str:
    """Empty an input through the native value setter so frameworks notice."""
    return f"""() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return false;
  el.focus();
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
                                                   : HTMLInputElement.prototype;
  const desc = Object.getOwnPropertyDescriptor(proto, 'value');
  if (desc && desc.set) desc.set.call(el, ''); else el.value = '';
  el.dispatchEvent(new Event('input', {{bubbles: true}}));
  el.dispatchEvent(new Event('change', {{bubbles: true}}));
  return true;
}}"""


def append_text(selector: str, text: str) -> str:
    """Append ``text`` to an input's value through the native setter (synthetic typing)."""
    return f"""() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return false;
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
                                                   : HTMLInputElement.prototype;
  const desc = Object.getOwnPropertyDescriptor(proto, 'value');
  const next = (el.value || '') + {json.dumps(text)};
  if (desc && desc.set) desc.set.call(el, next); else el.value = next;
  el.dispatchEvent(new Event('input', {{bubbles: true}}));
  return true;
}}"""


def wait_for_selector(selector: str, timeout_ms: int, visible: bool) -> str:
    """Poll inside the page until the selector exists (and is visible), in one call."""
    return f"""async () => {{{_VISIBLE}
  const deadline = Date.now() + {int(timeout_ms)};
  while (Date.now() < deadline) {{
    const el = document.querySelector({json.dumps(selector)});
    if (el && (!{json.dumps(bool(visible))} || __visible(el))) return true;
    await new Promise(r => setTimeout(r, 100));
  }}
  return false;
}}"""


def wait_ready_state(timeout_ms: int) -> str:
    return f"""async () => {{
  const deadline = Date.now() + {int(timeout_ms)};
  while (document.readyState !== 'complete' && Date.now() < deadline) {{
    await new Promise(r => setTimeout(r, 100));
  }}
  return document.readyState;
}}"""


def wait_network_idle(timeout_ms: int, quiet_ms: int = 500) -> str:
    """Resolve when no resource finished loading for ``quiet_ms``, or at ``timeout_ms``."""
    return f"""async () => {{
  const timeout = {int(timeout_ms)}, quiet = {int(quiet_ms)};
  const start = Date.now();
  let last = Date.now();
  let observer = null;
  if (typeof PerformanceObserver !== 'undefined') {{
    observer = new PerformanceObserver(() => {{ last = Date.now(); }});
    try {{ observer.observe({{entryTypes: ['resource']}}); }} catch (e) {{ observer = null; }}
  }}
  while (Date.now() - start < timeout) {{
    if (Date.now() - last >= quiet) break;
    await new Promise(r => setTimeout(r, 100));
  }}
  if (observer) observer.disconnect();
  return {{idle: Date.now() - last >= quiet, waited: Date.now() - start}};
}}"""


def element_text(selector: str) -> str:
    return f"""() => {{
  const el = document.querySelector({json.dumps(selector)});
  return el ? (el.textContent || '').trim() : null;
}}"""


def element_attribute(selector: str, attribute: str) -> str:
    return f"""() => {{
  const el = document.querySelector({json.dumps(selector)});
  return el ? el.getAttribute({json.dumps(attribute)}) : null;
}}"""
