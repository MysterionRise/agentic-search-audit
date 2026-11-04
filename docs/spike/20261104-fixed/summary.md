# Backend spike 2026-11-04 11:33

W = works, P = partial, F = fails, – = not applicable. One row per site and backend; Notes carry the first failing step's detail.

| Site | Backend | Challenge | Nav | Consent | SearchBox | Submit | Results | Shot | HTML | Top10 | p50 s/query | Snapshot tokens | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| www.boots.com | chrome_devtools_mcp | none | W | W | – | W | W | W | W | W | 20.5 | 12874 |  |
| www.boots.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 19.6 | 14020 |  |
| www.ebay.com | chrome_devtools_mcp | none | W | W | – | W | W | W | W | W | 23.1 | 49281 |  |
| www.ebay.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 24.3 | 13890 |  |

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
