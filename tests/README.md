# Tests

Three layers, each answering a different question.

| Command | Question it answers | Needs |
|---|---|---|
| `python -m pytest` | Is the **backend logic** right? (parsing, maths, validation, API shapes) | nothing — no network, no real files |
| `npm test` | Is the **frontend logic** right? (click geometry, formatting, saved drawings, legend) | Node 20+ only, no packages |
| `python scripts/smoke.py` | Do the **real feeds** still work *today*? (NSE/Yahoo/Sina/... changing under us) | a running server + internet |

The first two are deterministic and run in about two seconds. Run both before committing.
The smoke script is the only one that can tell you NSE moved an endpoint — run it when something looks wrong
on screen, or once a day.

## Which test proves which feature

| Feature | Backend test | Frontend test |
|---|---|---|
| Measure + trendline click accuracy, trend readout | — | `frontend/anchor-math.test.mjs` |
| Saved drawings, the **Clear** button's storage side | — | `frontend/drawings-store.test.mjs` |
| Chart legend: per-bar volume, 52W / 30D / day volume | `test_corporate_actions_names_stats.py` (stats) | `frontend/legend-html.test.mjs` |
| Lakh/crore formatting, "6m ago", HTML escaping | — | `frontend/format.test.mjs` |
| GIFT Nifty: live bars, and daily history from NSE IX | `test_gift_nifty.py`, `test_gift_nifty_history.py` | — |
| Background refresh never cancels a long range load | — | `frontend/refresh-policy.test.mjs` |
| Commodities: real-time Binance quote/candles, Yahoo fallback and history split | `test_commodities.py` | `frontend/refresh-policy.test.mjs` (when live ticks are folded) |
| Live push: Binance websocket parsing, the shared quote builder, the SSE stream, the Binance/Yahoo source switch | `test_streaming.py` | `frontend/stream-policy.test.mjs`, `frontend/feed-policy.test.mjs` |
| BSE stream recovers from a stale certificate chain (SENSEX latency) | `test_bse_stream.py` | — |
| Options panel (NSE F&O): futures, option chain, max pain, futures chart | `test_fno.py` | — |
| Live index volume (NSE total + Yahoo minutes) | `test_live_volume.py` | — |
| News panel | `test_news.py` | — |
| Breadth (NASDAQ / TAIEX / SSE), movers | `test_market_breadth_and_movers.py`, `test_movers.py`, `test_breadth.py`, `test_constituents.py` | — |
| Company names | `test_corporate_actions_names_stats.py` | — |
| Bonus/split gap-fill | `test_corporate_actions_names_stats.py` | — |
| Download dialog + end-of-day schedule | `test_exports.py` | — |
| Closing Auction Session (CAS) | `test_cas.py`, `test_api_auction.py` | — |
| Every HTTP route's shape and status codes | `test_api_contract.py`, `test_api_auction.py` | — |
| Symbols, candles shaping | `test_symbols.py`, `test_candles.py` | — |
| Page wiring: element ids, imports, toolbar captions, rail names | `test_frontend_wiring.py` | — |
| Code hygiene: unused imports, docstrings, bare `except` | `test_code_quality.py` | — |

## Rules the suite follows

* **No real network, no real home directory.** `conftest.py` clears the TTL cache around every test and
  redirects every file the app writes into a temp folder (`isolated_state`). A test that reaches the
  internet is a bug.
* **Fake at the service boundary.** Route tests replace `orazio.fno.panel`, `orazio.gift_nifty.quote`, ...
  — not `requests` — so they test routing and response shapes, and survive internal refactors.
* **Name the behaviour, not the function.** `test_a_reset_seen_mid_session_must_not_dump_the_whole_day_into_one_bar`
  says what broke when it fails. Keep that style.
* **A bug fix starts with a failing test.** The suite has one for each bug found in use: Clear ignoring the
  measure tool, trendlines vanishing on other bar sizes, double-adjusted split prices, the 09:15 volume dump.

## Adding a feature

1. Put the logic in a module with **pure functions** that take data and return data (see `gift_nifty.parse_reading`,
   `fno.max_pain`, `static/js/anchor-math.js`). Network and DOM stay in thin wrappers.
2. Write the test for the pure part, named after the behaviour.
3. Add a route test in `test_api_contract.py` for the response shape.
4. Add a line to `scripts/smoke.py` so the live feed is checked too.
5. Run `python -m pytest && npm test`. `test_frontend_wiring.py` will tell you if you forgot an element id, an
   import, or a caption under a new toolbar button.
