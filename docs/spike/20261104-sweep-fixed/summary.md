# Backend spike 2026-11-04 12:56

W = works, P = partial, F = fails, – = not applicable. One row per site and backend; Notes carry the first failing step's detail.

| Site | Backend | Challenge | Nav | Consent | SearchBox | Submit | Results | Shot | HTML | Top10 | p50 s/query | Snapshot tokens | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| oldnavy.gap.com | kimi_webbridge | none | W | W | – | W | W | W | W | P | 11.4 | 5749 |  |
| www.adidas.com | kimi_webbridge | none | W | W | – | W | F | W | W | F | 24.9 | 378 | results_wait: no result items became visible within 15s |
| www.bestbuy.com | kimi_webbridge | none | W | W | – | W | W | W | W | P | 14.5 | 7151 |  |
| www.costco.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 12.4 | 14107 |  |
| www.currys.co.uk | kimi_webbridge | none | W | P | – | W | W | W | W | W | 20.6 | 13760 |  |
| www.gap.com | kimi_webbridge | geo_block | W | W | – | – | – | – | – | – | 3.4 | – | challenge: Region block: body length 567 chars with 'does not support shipping outside' (the site turns this country away; use a pr |
| www.jcpenney.com | kimi_webbridge | geo_block | W | W | – | – | – | – | – | – | 3.0 | – | challenge: Region block: body length 97 chars with 'unable to provide a shopping experience for this country' (the site turns this  |
| www.johnlewis.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 18.5 | 14799 |  |
| www.kohls.com | kimi_webbridge | none | W | W | – | W | P | W | W | P | 30.5 | 14475 |  |
| www.lowes.com | kimi_webbridge | title_match | W | W | – | W | F | W | W | F | 25.9 | 100 | results_wait: no result items became visible within 15s |
| www.sephora.com | kimi_webbridge | none | W | W | – | W | P | W | W | P | 25.7 | 7083 |  |
| www.shutterfly.com | kimi_webbridge | none | W | W | W | W | F | W | W | F | 42.4 | 12119 | results_wait: no result items became visible within 15s |
| www.target.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 17.8 | 13665 |  |
| www.wayfair.com | kimi_webbridge | none | W | W | – | W | F | W | W | F | 33.4 | 13980 | results_wait: no result items became visible within 15s |

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
