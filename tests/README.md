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
| Drawing tools: Fibonacci levels, channel offset, moving/editing drawings, old saved formats | — | `frontend/draw-math.test.mjs` |
| Bar replay: start bar from a click, stepping bounds, speeds | — | `frontend/replay-policy.test.mjs` |
| Screener: NSE rows, technicals (Wilder RSI, SMAs, crosses, daily refresh), presets, filters, sorting | `test_screener.py`, `test_technicals.py` | `frontend/screener-policy.test.mjs` |
| Bonds, global: 37-country CNBC catalog, yields in bp, charts (CNBC bars, India 10Y daily from worldgovernmentbonds) | `test_bonds.py` | `frontend/bonds-policy.test.mjs` |
| Bonds, India: CCIL G-sec/SDL/T-bill segments (swapped fields), trade recorder + charts | `test_gsec.py` | `frontend/bonds-policy.test.mjs` |
| Bonds, India corporate: NSE rows, yield to maturity with accrued interest | `test_corp_bonds.py` | — |
| Saved drawings, the **Clear** button's storage side | — | `frontend/drawings-store.test.mjs` |
| Chart legend: per-bar volume, 52W / 30D / day volume | `test_corporate_actions_names_stats.py` (stats) | `frontend/legend-html.test.mjs` |
| Lakh/crore formatting, "6m ago", HTML escaping | — | `frontend/format.test.mjs` |
| GIFT Nifty: live bars, and daily history from NSE IX | `test_gift_nifty.py`, `test_gift_nifty_history.py` | — |
| Background refresh never cancels a long range load | — | `frontend/refresh-policy.test.mjs` |
| Commodity spot (default): Dukascopy oil/gas/copper, Swissquote gold/silver, history, WTI/USOIL/UKOIL aliases | `test_spot.py` | `frontend/feed-policy.test.mjs` |
| Commodity futures: Hyperliquid oracle (oil, gas, copper) vs Binance (gold, silver), fallbacks, scroll-back | `test_futures.py`, `test_commodities.py` | `frontend/refresh-policy.test.mjs` (when live ticks are folded) |
| Live push: Binance websocket parsing, the shared quote builder, the SSE stream, the Spot/Futures switch | `test_streaming.py` | `frontend/stream-policy.test.mjs`, `frontend/feed-policy.test.mjs` |
| BSE stream recovers from a stale certificate chain (SENSEX latency) | `test_bse_stream.py` | — |
| Options panel (NSE F&O): futures, option chain, max pain, futures chart, lot sizes | `test_fno.py` | — |
| Payoff builder: P&L at expiry, breakevens, max profit/loss | — | `frontend/options-math.test.mjs` |
| Indicators: SMA/EMA (incl. on another timeframe, no look-ahead), VWAP, Bollinger, RSI, MACD, band layout | — | `frontend/indicators.test.mjs` |
| Live index volume (NSE total + Yahoo minutes) | `test_live_volume.py` | — |
| News panel | `test_news.py` | — |
| Breadth (NASDAQ / TAIEX / SSE), movers | `test_market_breadth_and_movers.py`, `test_movers.py`, `test_breadth.py`, `test_constituents.py` | — |
| Company names | `test_corporate_actions_names_stats.py` | — |
| Bonus/split gap-fill | `test_corporate_actions_names_stats.py` | — |
| Download dialog + end-of-day schedule | `test_exports.py` | — |
| Closing Auction Session (CAS), futures-implied close | `test_cas.py`, `test_api_auction.py` | — |
| Real-time CAS rebuild from BSE (composition fit, BSE frames, estimate) | `test_cas_rebuild.py` | — |
| Weekly bars, 1W range | `test_candles.py`, `test_commodities.py` | — |
| Typed symbols resolve to their NSE listing (ADANIENT → ADANIENT.NS) | — | `frontend/search-box.test.mjs` |
| TTL cache: one upstream call per concurrent miss, stale keys swept | `test_cache.py` | — |
| Every HTTP route's shape and status codes | `test_api_contract.py`, `test_api_auction.py` | — |
| Symbols, candles shaping | `test_symbols.py`, `test_candles.py` | — |
| Page wiring: element ids, imports, panel-strip captions, drawing-strip names, rail names | `test_frontend_wiring.py` | — |
| Code hygiene: unused imports, docstrings, bare `except` | `test_code_quality.py` | — |
| Compare: chart styles (Heikin Ashi), formula series (`A / B`, `A - B`) | — | `frontend/indicators.test.mjs`, `frontend/formula.test.mjs` |
| Insights charts and tables (axis labels, bars, lines, sorting) | — | `frontend/minichart.test.mjs` |
| Flows: FII/DII rows, participant-wise OI CSV | `test_flows.py` | — |
| Options analytics: Black-Scholes gamma, GEX sign, zero-gamma flip, smile | `test_options_analytics.py` | — |
| Delivery vs 20-day average, rollover by sessions to expiry | `test_delivery_rollover.py` | `frontend/insights-math.test.mjs` (alignment) |
| Breadth, correlation/beta, RRG, seasonality, event study, yield curve, rating spreads, watchlist columns | — | `frontend/insights-math.test.mjs` |
| RBI money-market release parsing | `test_macro.py` | — |
| Chart events (corporate actions, big FII days) and their placement on bars | `test_chart_events.py` | `frontend/insights-math.test.mjs` |
| Command line: what is a command, what stays a search | — | `frontend/command-parse.test.mjs` |
| Alerts: crossings, day change, live price folded into today | — | `frontend/alert-rules.test.mjs` |
| Journal: FIFO P&L for longs and shorts, stats by setup | — | `frontend/journal-math.test.mjs` |
| Workspaces: layout keys only, presets merge | — | `frontend/workspace-store.test.mjs` |
| Every frontend module parses (one syntax error blanks the page) | — | `frontend/syntax.test.mjs` |

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
