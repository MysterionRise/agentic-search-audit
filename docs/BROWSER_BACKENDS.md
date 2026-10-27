# Browser backends

The audit drives a browser through the `BrowserClient` protocol (`core/types.py`). Six
backends implement it. Three launch their own browser; three *bridge* into a Chrome that is
already running, so the audit runs with the user's real profile, cookies and fingerprint.

| Backend | Browser | Profile | Best for | One-time setup |
|---|---|---|---|---|
| `playwright` (default) | Playwright Chromium | disposable | sites with light or no bot detection | `playwright install chromium` |
| `undetected` | real Chrome via undetected-chromedriver | disposable | Akamai, PerimeterX, DataDome sites that block Playwright | `uv sync --extra undetected`; Chrome installed |
| `cdp` | any Chrome over CDP | external | Browserbase or a Chrome you started with `--remote-debugging-port` | start that Chrome |
| `chrome_devtools_mcp` | your running Chrome (or its own) | real (modes `autoconnect`, `browser_url`) or disposable (`launch`) | sites that block launched browsers; audits in a logged-in profile | Node >= 20.19 (`nvm use 24`); for `autoconnect`: Chrome 144+, enable `chrome://inspect/#remote-debugging` once, approve the dialog |
| `kimi_webbridge` | your running Chrome | real | same as above, second attach path when CDP is fingerprinted | install the Kimi WebBridge daemon and its Chrome extension; `~/.kimi-webbridge/bin/kimi-webbridge start` |
| `playwright_mcp` | your running Chrome | real | experimental | install the Playwright MCP Chrome Extension |

Select a backend per site with `run.browser_backend` in `configs/sites/<site>.yaml`, or
per run with `--browser <name>`. Bridge settings live under `run.bridge` (`BridgeConfig`):

```yaml
run:
  browser_backend: chrome_devtools_mcp
  bridge:
    mode: autoconnect            # autoconnect | browser_url | launch
    browser_url: http://127.0.0.1:9222   # for mode: browser_url
    allow_profile_mutations: false       # keep false on a real logged-in profile
    connect_timeout_s: 60                # time to approve Chrome's dialog
```

## Rules on a real profile

- The run opens exactly one tab, works only in it, and closes only that tab.
- No user-agent rotation, proxy switching, cookie clearing or window resizing. Backends
  report this through `BrowserCapabilities`; `BrowserSession` skips those steps and logs
  once. `run.bridge.allow_profile_mutations: true` opts back into user-agent override and
  cookie clearing.
- Input is trusted where the bridge allows it: chrome-devtools-mcp types through Puppeteer's
  keyboard; Kimi WebBridge keys and clicks go through raw CDP events. Clicks in
  chrome-devtools-mcp are synthetic unless `experimental_vision_click` is on.

## Protocol fit

How each `BrowserClient` method is satisfied. *native* = a tool of the bridge; *JS* = run in
the page through the bridge's evaluate; *skipped* = capability is False, the orchestrator
does not call it.

| Method | chrome_devtools_mcp | kimi_webbridge | playwright_mcp |
|---|---|---|---|
| navigate | native (`navigate_page`) + JS ready/idle waits | native (`navigate`) + JS waits | native (`browser_navigate`) + JS waits |
| evaluate | native (`evaluate_script`, JSON block) | native (`evaluate`, `{type, value}`) | native (`browser_evaluate`) |
| query_selector, get_html, get_element_* | JS | JS | JS |
| click | JS synthetic (`click_at` with vision flag) | trusted (`cdp Input.dispatchMouseEvent`) | JS synthetic |
| type_text | native keystrokes (`type_text`) | trusted (`cdp Input.dispatchKeyEvent`) | `browser_press_key` per char |
| press_key | native (`press_key`) | trusted CDP key events (Enter carries `\r`) | native |
| screenshot (full page) | native (`take_screenshot fullPage`) | `cdp Page.captureScreenshot` beyond viewport | native |
| wait_for_selector, wait_for_network_idle | JS, one call each | JS, one call each | JS, one call each |
| recover_page / reconnect | `new_page` / restart server | `navigate newTab` / reconnect daemon | `browser_tabs new` / restart |
| set_user_agent | `emulate` when allowed, else skipped | `cdp Network.setUserAgentOverride` when allowed | skipped |
| clear_cookies | isolated context (launch) / skipped | `cdp Network.clearBrowserCookies` when allowed | skipped |
| set_proxy | launch mode only | skipped | skipped |

## Measurements

Run the spike and paste `summary.md` here:

```bash
nvm use 24
uv run python scripts/backend_spike.py --sites nike,amazon,ebay,target,walmart,sephora \
    --backends undetected,chrome_devtools_mcp,kimi_webbridge --queries 3 \
    --bridge-mode autoconnect --out docs/spike/$(date +%Y%m%d)
```

Each row aggregates the queries of one site and backend: W = every query worked, P = at
least one partial, F = at least one failure (Notes carry the first failing step), – = not
applicable. `p50 s/query` is wall-clock per query; `Snapshot tokens` estimates the size of
the accessibility snapshot an LLM would read (chars / 4), which is the main cost of agentic
navigation.

_(to be filled from the spike)_

### Verified so far

- `chrome_devtools_mcp` in `launch` mode, headless, against books.toscrape.com: navigate,
  typed `evaluate`, `wait_for_selector`, full-page screenshot, HTML, key press and page
  recovery all pass (`tests/integration/test_bridge_real_browser.py`). Two bugs found this
  way: MCP context managers must be entered and exited in the same task, and
  chrome-devtools-mcp 1.5 routes page-scoped tools by `pageId`.
- `autoconnect` and `kimi_webbridge` need the user's one-time setup and are measured by the
  spike.

## Decision

_(to be written from the measurements: which backend each site defaults to, and whether the
agentic path should use snapshots, JavaScript evaluation, or the screenshot-plus-vision
pipeline)_

Rule of thumb until then: keep `undetected` where it works today; try `chrome_devtools_mcp`
(`autoconnect`) on sites that block launched browsers or require a logged-in session; use
`kimi_webbridge` as the second attach path when a vendor fingerprints the first.

## Privacy and telemetry

- chrome-devtools-mcp is started with `--usageStatistics=false` and
  `CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS=1`.
- The Kimi WebBridge daemon sends usage telemetry to Moonshot (hourly `webbridge_daemon_alive`
  events); this cannot be disabled from this tool.
- In `autoconnect` mode chrome-devtools-mcp can see every window of the attached profile;
  this tool only ever addresses the tab it opened.
- Screenshots and HTML snapshots of a logged-in session can contain account details; review
  `runs/` before sharing.

## Known limitations

- Cross-origin iframes are unreachable from the page's JavaScript on every backend.
- Sites that check `event.isTrusted` ignore synthetic clicks; prefer Kimi WebBridge or
  `experimental_vision_click` there.
- Anti-bot vendors can fingerprint CDP (`Runtime.enable`); the real profile's cookies and
  fingerprint are the main lever, and the spike measures each vendor.
- `playwright_mcp` has not been exercised end to end.
