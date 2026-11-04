# Backend spike 2026-11-04 11:19

W = works, P = partial, F = fails, – = not applicable. One row per site and backend; Notes carry the first failing step's detail.

| Site | Backend | Challenge | Nav | Consent | SearchBox | Submit | Results | Shot | HTML | Top10 | p50 s/query | Snapshot tokens | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| www.amazon.com | chrome_devtools_mcp | none | W | W | – | W | W | W | W | W | 15.2 | 52265 |  |
| www.boots.com | chrome_devtools_mcp | none | F | W | – | W | P | W | W | P | 11.0 | 13160 | navigate: BridgeToolError: evaluate_script: Error: Execution context was destroyed, most likely because of a navigation. |
| www.ebay.com | chrome_devtools_mcp | none | W | W | – | W | F | F | W | F | 37.8 | 49272 | results_wait: no result items became visible within 15s |
| www.nike.com | chrome_devtools_mcp | none | W | W | – | W | W | W | W | W | 38.0 | 32172 |  |

## Environment

- platform: macOS-15.7.4-arm64-arm-64bit
- python: 3.12.13
- chrome: 156
- playwright: 1.64.1
- playwright-stealth: 2.0.3
- undetected-chromedriver: 3.5.5
- mcp: 2.3.0
- node: v24.22.0
- chrome-devtools-mcp (npx cache): 1.12.0
