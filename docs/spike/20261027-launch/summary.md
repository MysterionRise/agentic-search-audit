# Backend spike 2026-10-27 16:57

W = works, P = partial, F = fails, – = not applicable. One row per site and backend; Notes carry the first failing step's detail.

| Site | Backend | Challenge | Nav | Consent | SearchBox | Submit | Results | Shot | HTML | Top10 | p50 s/query | Snapshot tokens | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| www.amazon.com | chrome_devtools_mcp | none | W | P | – | W | W | F | W | W | 14.1 | 34448 | screenshot: BridgeToolError: take_screenshot: the server returned no image content |
| www.amazon.com | playwright | none | W | P | – | W | W | W | W | W | 12.0 | – |  |
| www.nike.com | chrome_devtools_mcp | none | W | W | – | W | W | W | W | W | 35.2 | 32608 |  |
| www.nike.com | playwright | none | W | W | – | W | W | W | W | W | 13.0 | – |  |

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
