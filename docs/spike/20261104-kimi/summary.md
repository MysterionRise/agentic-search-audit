# Backend spike 2026-11-04 11:26

W = works, P = partial, F = fails, – = not applicable. One row per site and backend; Notes carry the first failing step's detail.

| Site | Backend | Challenge | Nav | Consent | SearchBox | Submit | Results | Shot | HTML | Top10 | p50 s/query | Snapshot tokens | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| www.amazon.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 12.6 | 14168 |  |
| www.boots.com | kimi_webbridge | none | W | W | – | W | P | W | W | P | 16.4 | 14008 |  |
| www.ebay.com | kimi_webbridge | none | W | W | – | W | F | W | W | F | 36.4 | 13901 | results_wait: no result items became visible within 15s |
| www.nike.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 12.0 | 15150 |  |

## Environment

- platform: macOS-15.7.4-arm64-arm-64bit
- python: 3.12.13
- chrome: 156
- playwright: 1.64.1
- playwright-stealth: 2.0.3
- undetected-chromedriver: 3.5.5
- mcp: 2.3.0
- node: v20.18.0
- chrome-devtools-mcp (npx cache): 1.12.0
