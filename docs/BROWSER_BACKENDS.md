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

### Run 1: 2026-10-27, unattended, launched browsers (no user setup)

macOS 15.7 arm64, Chrome 156, Node 24.22, chrome-devtools-mcp 1.5.0, Playwright 1.64.1,
undetected-chromedriver 3.5.5. Two queries per site from `data/queries/<site>.json`,
`chrome_devtools_mcp` in `launch` mode (its own headless Chrome), the others headless.
The Nike and Amazon rows for `playwright` and `chrome_devtools_mcp` are from a re-run after
the one-call selector probes; the `undetected` and eBay rows are from the first run (both
summaries are in `docs/spike/20261027-launch/`).

| Site | Backend | Challenge | Nav | Consent | Submit | Results | Shot | HTML | Top10 | p50 s/query | Snapshot tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|
| nike | playwright | none | W | W | W | W | W | W | W | 13.0 | – |
| nike | undetected | none | W | W | W | W | W | W | W | 13.9 | – |
| nike | chrome_devtools_mcp | none | W | W | W | W | W | W | W | 35.2 | 32,600 |
| amazon | playwright | none | W | P | W | W | W | W | W | 12.0 | – |
| amazon | undetected | none | W | P | W | W | W | W | W | 9.3 | – |
| amazon | chrome_devtools_mcp | none | W | P | W | W | W* | W | W | 14.1 | 34,400 |
| ebay | playwright | none | W | W | W | F | W | W | F | 29.3 | – |
| ebay | undetected | none | W | W | W | F | W | W | F | 26.3 | – |
| ebay | chrome_devtools_mcp | none | W | W | W | F | W | W | F | 52.4 | 280 |

All three sites use a `search_url_template`, so the search-box column is not applicable.
`*` the 2 MB full-page Amazon screenshot failed in the run and was fixed afterwards (the
server writes large images to a temp file; the transport now copies it), then verified by
hand.

What the numbers say:

- **No bot challenge on any backend** for these three sites from this machine and IP, so
  this run does not separate the backends on anti-bot resistance. That needs the
  `autoconnect` and `kimi_webbridge` runs on the sites that block Playwright today (the
  30 configs set to `undetected`), and a residential IP.
- **eBay fails on every backend in the same way**: results never become visible within
  15 s, and once the page title was "Error Page | eBay". The eBay item selectors or the
  results wait need revisiting; it is not a backend problem.
- **Amazon consent is partial everywhere**: an overlay stays visible after the consent
  step. Same on every backend, so a modal-handling issue, not a backend one.
- **chrome_devtools_mcp costs about 0.7 s per tool call** (the server waits for the page
  to settle after each). Before the one-call probes, consent handling took 18 to 90 s and
  the challenge check 3 s per query on this backend (Nike p50 138 s, Amazon 37 s); probing
  selector lists in one `evaluate` brought the challenge check to 0.2 s and the totals to
  35 s and 14 s. Navigation itself is the remaining cost on Nike (14 s, the server waits for
  `load`).
- **Snapshot size**: an accessibility snapshot of a results page is 24k to 45k tokens
  (Nike, Amazon), versus a few hundred on an error page. That is the per-step price of a
  fully agentic loop that reads snapshots; the current JavaScript extraction reads none.

### Run 2: real profile (`autoconnect`, `kimi_webbridge`)

_(pending: needs the one-time setup on the user's Chrome; run the command above with
`--bridge-mode autoconnect --backends undetected,chrome_devtools_mcp,kimi_webbridge` on the
sites that block launched browsers)_

## Decision

Provisional, from run 1; revisit after run 2.

1. **Keep the per-site defaults as they are** (`undetected` for the 30 sites configured
   that way, `playwright` elsewhere). Run 1 shows no backend failing where another works,
   so there is no evidence yet for switching any site.
2. **Wire in `chrome_devtools_mcp` as the first bridge** (done) and use `kimi_webbridge` as
   the second attach path. Both are opt-in per site. Use them where a launched browser is
   blocked or a logged-in session is needed; run 2 decides which sites move.
3. **The agentic path should keep JavaScript evaluation for extraction**, and use
   accessibility snapshots only for navigation decisions where selectors fail. A results
   page snapshot costs 24k to 45k tokens per read; the JavaScript extraction returns the
   same ten results in one call and no tokens. The screenshot-plus-vision pipeline stays the
   fallback when both fail.
4. **Every new consumer must batch**: one `evaluate` per decision, never a loop of
   `query_selector` calls, because bridge tool calls cost about 0.7 s each.

## Privacy and telemetry

- chrome-devtools-mcp is started with `--usageStatistics=false`, `--performanceCrux=false`
  (no trace URLs sent to Google's CrUX API) and `CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS=1`.
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
