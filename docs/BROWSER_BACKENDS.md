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

For eBay, "none" in the challenge column was wrong: the page was eBay's edge block page,
which the detector did not recognise at the time (see below).

All three sites use a `search_url_template`, so the search-box column is not applicable.
`*` the 2 MB full-page Amazon screenshot failed in the run and was fixed afterwards (the
server writes large images to a temp file; the transport now copies it), then verified by
hand.

What the numbers say:

- **eBay blocks every launched browser, and the challenge column said "none"**. A
  follow-up on 2026-11-03 showed eBay's search answers Playwright, undetected-chromedriver
  and chrome_devtools_mcp (launch) with its edge block page ("SORRY / Something went wrong
  on our end" and an Akamai-style reference ID, title "Error Page | eBay", about 155
  characters). Repeated visits escalated the block to the homepage for a while. The
  detector did not know that page, so run 1 reported "no results" instead of a challenge;
  it now reports `edge_block`. eBay is a real anti-bot case for run 2, not a selector
  problem. (Run 2 got past the block and found the selectors were out of date as well.)
- **Boots is blocked the same way** by Imperva (Incapsula): an empty page whose iframe
  points at `/_Incapsula_Resource`. The detector now reports it as `captcha_iframe`.
- **Amazon consent was a false "partial"**. The overlay check counted any large element
  whose class contains "overlay", and every Amazon product image sits in an
  `s-image-overlay-grey` container. Overlays now have to be visible, in the viewport and
  either a dialog or floating above the page. The one real overlay left was Amazon's
  delivery-location toaster for non-US visitors, whose Dismiss control is an `<input>`
  labelled through `aria-labelledby`; the close-button finder now reads that, and the
  consent step reports `works` on Amazon.
- **No other bot challenge** showed up for Nike and Amazon from this machine and IP, so
  run 1 does not separate the backends on anti-bot resistance. That needs the
  `autoconnect` and `kimi_webbridge` runs on eBay, Boots and the other sites that block
  launched browsers, and ideally a residential IP.
- **chrome_devtools_mcp costs about 0.7 s per tool call** (the server waits for the page
  to settle after each). Before the one-call probes, consent handling took 18 to 90 s and
  the challenge check 3 s per query on this backend (Nike p50 138 s, Amazon 37 s); probing
  selector lists in one `evaluate` brought the challenge check to 0.2 s and the totals to
  35 s and 14 s. Navigation itself is the remaining cost on Nike (14 s, the server waits for
  `load`).
- **Snapshot size**: an accessibility snapshot of a results page is 24k to 45k tokens
  (Nike, Amazon), versus a few hundred on an error page. That is the per-step price of a
  fully agentic loop that reads snapshots; the current JavaScript extraction reads none.

### Run 2: 2026-11-04, the user's real profile (`autoconnect`, `kimi_webbridge`)

Same machine and UK IP as run 1, the user's everyday Chrome profile (Chrome 155 running),
chrome-devtools-mcp 1.12.0 in `autoconnect` mode, Kimi WebBridge daemon 2.0.5 with
extension 2.0.32. Two queries per site. The Nike and Amazon rows are from the first pass;
the eBay and Boots rows are from a re-run after the fixes listed below (the first-pass
summaries are kept in `docs/spike/20261104-autoconnect/` and `20261104-kimi/`, the re-run
in `20261104-fixed/`).

| Site | Backend | Challenge | Nav | Consent | Submit | Results | Shot | HTML | Top10 | p50 s/query | Snapshot tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|
| nike | chrome_devtools_mcp | none | W | W | W | W | W | W | W | 38.0 | 32,172 |
| nike | kimi_webbridge | none | W | W | W | W | W | W | W | 12.0 | 15,150 |
| amazon | chrome_devtools_mcp | none | W | W | W | W | W | W | W | 15.2 | 52,265 |
| amazon | kimi_webbridge | none | W | W | W | W | W | W | W | 12.6 | 14,168 |
| ebay | chrome_devtools_mcp | none | W | W | W | W | W | W | W | 23.1 | 49,281 |
| ebay | kimi_webbridge | none | W | W | W | W | W | W | W | 24.3 | 13,890 |
| boots | chrome_devtools_mcp | none | W | W | W | W | W | W | W | 20.5 | 12,874 |
| boots | kimi_webbridge | none | W | W | W | W | W | W | W | 19.6 | 14,020 |

Snapshot tokens are not comparable across backends: each server formats its accessibility
snapshot differently, and Kimi's is the more compact.

What the numbers say:

- **The real profile gets past both blocks.** eBay and Boots served normal pages, with no
  challenge, to both bridges. The day before, the same machine and IP got block pages from
  every launched browser. About a dozen eBay searches on the real profile caused no block.
- **The first-pass failures were ours, not the sites' anti-bot.** eBay has moved from
  `.s-item` to `.s-card` markup and puts two hidden "Shop on eBay" placeholder listings in
  front of the results. Boots uses `oct-teaser` tiles and redirects category words
  (`shampoo`) to a category page; that redirect destroyed the page context while
  chrome-devtools-mcp waited for the load. The selectors were checked by running the
  extraction script on the live pages, and the bridge waits now re-run on the new document.
- **Kimi WebBridge is the faster bridge**: 12 to 13 s per query on Nike and Amazon against
  15 to 38 s for chrome-devtools-mcp, whose server waits for the page to settle after every
  call. On eBay and Boots both take 20 to 24 s.
- **Kimi needed one fix**: extension 2.0.32 never reports a new `about:blank` tab as loaded,
  so opening the run's tab there timed out. The tab now opens with the first navigation.
  Until then the daemon refuses page commands for the session ("has no tab"), so a run
  cannot act on another tab.

## Decision

From runs 1 and 2.

1. **Sites that block launched browsers run on a bridge.** eBay and Boots block Playwright,
   undetected-chromedriver and chrome-devtools-mcp's own Chrome from this IP, and work on
   the real profile through either bridge. Their configs keep `undetected` so unattended
   runs need no setup; audit them with `--browser kimi_webbridge` or
   `--browser chrome_devtools_mcp`. The other sites keep their defaults until a run shows
   them blocked.
2. **Prefer `kimi_webbridge` when it is installed**: it is faster, its input is trusted and
   Chrome shows no approval dialog for it. Use `chrome_devtools_mcp` when the Moonshot
   telemetry (below) is not acceptable or Kimi is not installed; both pass the same sites.
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
