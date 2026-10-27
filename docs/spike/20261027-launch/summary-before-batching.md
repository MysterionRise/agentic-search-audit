# Backend spike 2026-10-27 16:42

W = works, P = partial, F = fails, – = not applicable. One row per site and backend; Notes carry the first failing step's detail.

| Site | Backend | Challenge | Nav | Consent | SearchBox | Submit | Results | Shot | HTML | Top10 | p50 s/query | Snapshot tokens | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| www.amazon.com | chrome_devtools_mcp | none | W | P | – | W | W | F | W | W | 36.6 | 36261 | screenshot: BridgeToolError: take_screenshot: Error: Access denied: path "/private/tmp/asa_spike_launch/screenshots/www.amazon.com_chrome_devtools_mcp_1.png" (canonical: "/private/tmp/asa_s |
| www.amazon.com | playwright | none | W | P | – | W | W | W | W | W | 11.9 | – |  |
| www.amazon.com | undetected | none | W | P | – | W | W | W | W | W | 9.3 | – |  |
| www.ebay.com | chrome_devtools_mcp | none | W | W | – | W | F | F | W | F | 52.4 | 279 | results_wait: no result items became visible within 15s |
| www.ebay.com | playwright | none | W | W | – | W | F | W | W | F | 29.3 | – | results_wait: no result items became visible within 15s |
| www.ebay.com | undetected | none | W | W | – | W | F | W | W | F | 26.3 | – | results_wait: no result items became visible within 15s |
| www.nike.com | chrome_devtools_mcp | none | W | W | – | W | W | F | W | W | 137.6 | 36421 | screenshot: BridgeToolError: take_screenshot: Error: Access denied: path "/private/tmp/asa_spike_launch/screenshots/www.nike.com_chrome_devtools_mcp_1.png" (canonical: "/private/tmp/asa_spi |
| www.nike.com | playwright | none | W | W | – | W | W | W | W | W | 13.0 | – |  |
| www.nike.com | undetected | none | W | W | – | W | W | W | W | W | 13.9 | – |  |

## Environment

- platform: macOS-15.7.4-arm64-arm-64bit
- python: 3.12.13
- chrome: 156
- playwright: 1.64.1
- playwright-stealth: 2.0.3
- undetected-chromedriver: 3.5.5
- mcp: 1.30.0
- node: v24.22.0
- chrome-devtools-mcp (npx cache): 1.5.0
