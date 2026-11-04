# Backend spike 2026-11-04 12:36

W = works, P = partial, F = fails, – = not applicable. One row per site and backend; Notes carry the first failing step's detail.

| Site | Backend | Challenge | Nav | Consent | SearchBox | Submit | Results | Shot | HTML | Top10 | p50 s/query | Snapshot tokens | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| oldnavy.gap.com | kimi_webbridge | selector_match | W | W | – | – | – | – | – | – | 14.5 | – | challenge: Challenge page detected via selector: #sec-overlay |
| uk.burberry.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 26.6 | 3006 |  |
| www.adidas.com | kimi_webbridge | none | W | W | – | W | F | W | W | F | 23.8 | 378 | results_wait: no result items became visible within 15s |
| www.amazon.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 12.7 | 14148 |  |
| www.argos.co.uk | kimi_webbridge | none | W | W | – | W | W | W | W | W | 22.1 | 14080 |  |
| www.bestbuy.com | kimi_webbridge | none | W | W | – | W | F | W | W | F | 24.7 | 371 | results_wait: no result items became visible within 15s |
| www.boots.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 14.8 | 14046 |  |
| www.costco.com | kimi_webbridge | none | W | W | – | W | F | W | W | F | 32.8 | 14113 | results_wait: no result items became visible within 15s |
| www.currys.co.uk | kimi_webbridge | none | W | P | – | W | F | W | W | F | 38.7 | 13760 | results_wait: no result items became visible within 15s |
| www.diy.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 19.0 | 13560 |  |
| www.ebay.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 23.0 | 13800 |  |
| www.etsy.com | kimi_webbridge | none | W | P | – | W | W | W | W | W | 34.8 | 14042 |  |
| www.gap.com | kimi_webbridge | selector_match | W | W | – | – | – | – | – | – | 4.4 | – | challenge: Challenge page detected via selector: #sec-overlay |
| www.homedepot.com | kimi_webbridge | none | W | W | – | W | P | W | W | W | 27.6 | 13439 |  |
| www.jcpenney.com | kimi_webbridge | none | W | W | – | W | F | W | W | F | 24.3 | 104 | results_wait: no result items became visible within 15s |
| www.johnlewis.com | kimi_webbridge | none | W | W | – | W | F | F | W | W | 86.5 | 14799 | results_wait: BridgeTimeoutError: evaluate timed out after 8.0s |
| www.kohls.com | kimi_webbridge | selector_match | W | W | – | – | – | – | – | – | 11.3 | – | challenge: Challenge page detected via selector: #sec-overlay |
| www.lowes.com | kimi_webbridge | selector_match | W | W | – | – | – | – | – | – | 8.8 | – | challenge: Challenge page detected via selector: #sec-overlay |
| www.macys.com | kimi_webbridge | none | W | W | – | W | W | W | W | P | 22.2 | 14432 |  |
| www.mixbook.com | kimi_webbridge | none | W | P | W | W | W | W | W | P | 27.8 | 7248 |  |
| www.nike.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 13.7 | 15212 |  |
| www.nordstrom.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 18.3 | 14365 |  |
| www.sephora.com | kimi_webbridge | captcha_iframe | W | W | – | – | – | – | – | – | 12.2 | – | challenge: CAPTCHA iframe detected: captcha |
| www.shutterfly.com | kimi_webbridge | none | W | W | W | W | F | W | W | F | 45.0 | 12049 | results_wait: no result items became visible within 15s |
| www.target.com | kimi_webbridge | none | W | W | – | W | F | W | W | F | 31.1 | 13627 | results_wait: no result items became visible within 15s |
| www.walmart.com | kimi_webbridge | none | W | W | – | W | W | W | W | W | 21.9 | 13944 |  |
| www.wayfair.com | kimi_webbridge | none | W | W | – | W | F | W | W | F | 36.0 | 14026 | results_wait: no result items became visible within 15s |
| www.wickes.co.uk | kimi_webbridge | none | W | P | – | W | W | W | W | W | 19.5 | 11244 |  |
| www.zalando.co.uk | kimi_webbridge | none | W | W | – | W | W | W | W | P | 28.3 | 14213 |  |

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
