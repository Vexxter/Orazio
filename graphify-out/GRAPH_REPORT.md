# Graph Report - sasta-trading-view  (2026-09-22)

## Corpus Check
- 38 files · ~23,027 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 305 nodes · 617 edges · 19 communities (13 shown, 6 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 34 edges (avg confidence: 0.72)
- Token cost: 0 input · 105,044 output

## Community Hubs (Navigation)
- Live Quote Sources & Caching
- Charting UI & Indicators
- CAS Terminal (Auction Modals)
- Derivatives: Futures & Options
- BSE Push Stream Client
- Symbol & Range Validation
- CAS Session & Auction Feed Logic
- App Entry Point & Config
- Candle Shaping & Tests
- Backend/Frontend Wiring Increment
- Real-Time Quotes & SENSEX Planning
- Chrome DevTools MCP Config
- Live Chart Parity Planning
- Range-Event Race-Condition Fix
- Project Root
- Test Runner Dependency
- HTTP Client Dependency
- Session Boundary Markers

## God Nodes (most connected - your core abstractions)
1. `loadCandles()` - 18 edges
2. `esc()` - 17 edges
3. `cas_phase()` - 11 edges
4. `clean_symbol()` - 11 edges
5. `BseStream` - 10 edges
6. `cached()` - 10 edges
7. `nse_get()` - 10 edges
8. `displayName()` - 10 edges
9. `state` - 10 edges
10. `ensure_poller()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `test_normalise_cas_rows_handles_empty_payload()` --calls--> `normalise_cas_rows()`  [EXTRACTED]
  tests/test_cas.py → orazio/cas.py
- `test_normalise_cas_rows_maps_nse_field_names()` --calls--> `normalise_cas_rows()`  [EXTRACTED]
  tests/test_cas.py → orazio/cas.py
- `test_normalise_cas_book_flags_the_equilibrium_rung()` --calls--> `normalise_cas_book()`  [EXTRACTED]
  tests/test_cas.py → orazio/cas.py
- `test_normalise_cas_book_handles_non_list_input()` --calls--> `normalise_cas_book()`  [EXTRACTED]
  tests/test_cas.py → orazio/cas.py
- `test_clean_symbol_defaults_when_blank()` --calls--> `clean_symbol()`  [EXTRACTED]
  tests/test_symbols.py → orazio/symbols.py

## Import Cycles
- 3-file cycle: `static/js/data.js -> static/js/futures.js -> static/js/symbol.js -> static/js/data.js`

## Hyperedges (group relationships)
- **CAS terminal: panel, movement view, feed and backend logic form one feature** — readme_cas_terminal, orazio_cas, static_js_cas_panel, static_js_cas_movement, static_js_cas_feed [EXTRACTED 1.00]
- **Real-time price pipeline across Yahoo, BSE stream and websockets dependency** — orazio_market_data, orazio_bse_stream, readme_yahoo_finance, readme_bse_push_stream, requirements_websockets [INFERRED 0.85]
- **Spec -> plan -> todo development lifecycle documents for the same increments** — tasks_spec_objective, tasks_plan_live_chart_parity, tasks_todo_increment4_race_fix [EXTRACTED 1.00]

## Communities (19 total, 6 thin omitted)

### Community 0 - "Live Quote Sources & Caching"
Cohesion: 0.06
Nodes (63): cached(), A tiny TTL cache for coalescing concurrent polls (several tabs / retries)., df_to_rows(), cas_feed_payload(), cas_payload(), cas_reference(), cas_reference_epoch(), ensure_nse_poller() (+55 more)

### Community 1 - "Charting UI & Indicators"
Cohesion: 0.08
Nodes (51): Charting feature set, Data-age badge, Live candles feature, #interval-seg bar-interval buttons, #range-bar history range buttons, applyStyle(), areaSeries, barSeries (+43 more)

### Community 2 - "CAS Terminal (Auction Modals)"
Cohesion: 0.09
Nodes (36): CAS terminal, #cas-move-open Live CAS movement button, #cas-open stock feed button, #cas call-auction rail section, #feed-modal live auction feed modal, #move-modal Live CAS movement modal, CAS_COLS, fcell() (+28 more)

### Community 3 - "Derivatives: Futures & Options"
Cohesion: 0.09
Nodes (28): Derivatives (futures/options), #options-btn button, #options-modal, #symbol-input search box, priceSeriesByStyle, futuresCounterpart(), symbolInput, openOptions() (+20 more)

### Community 4 - "BSE Push Stream Client"
Cohesion: 0.11
Nodes (15): BseStream, build_ssl_context(), _num(), Client for BSE's live push stream. BSE's own website connects to a Socket.IO v4…, BSE sends numbers as strings with thousands separators, and '-' for 'not set'., 2026-09-21 14:55:0' (seconds are not zero-padded) -> epoch seconds., A verifying SSL context that trusts certifi's roots plus BSE's missing…, _stamp() (+7 more)

### Community 5 - "Symbol & Range Validation"
Cohesion: 0.19
Nodes (15): fixture, clean_symbol(), Symbol validation and interval/range resolution — pure functions, no I/O., Pick the coarsest interval that can actually serve the requested range.…, resolve_interval_range(), parametrize, app_context(), test_clean_symbol_defaults_when_blank() (+7 more)

### Community 6 - "CAS Session & Auction Feed Logic"
Cohesion: 0.21
Nodes (16): cas_phase(), _mins(), normalise_cas_book(), normalise_cas_rows(), Map NSE's CAS row fields to ours. Verified against the live 15:20 payload (210…, `orderBook` items: price / buyQuantity / sellQuantity / flag. Observed: `flag`…, Which auction window we are in, its current stage, and seconds to its…, _ist() (+8 more)

### Community 7 - "App Entry Point & Config"
Cohesion: 0.22
Nodes (7): Entry point. All application code lives in the `orazio` package., load_seed(), Restore today's reference and series after a restart. Ignored if it is from…, Environment-driven app settings. Kept deliberately tiny: everything a deployer…, Settings, create_app(), Orazio: a self-hosted TradingView-style chart backed by yfinance/NSE/BSE.

### Community 8 - "Candle Shaping & Tests"
Cohesion: 0.42
Nodes (7): drop_spurious_flat_rows(), Shaping yfinance OHLCV data into the JSON rows the frontend consumes., Yahoo occasionally leaks a non-trading-day row (e.g. a Sunday) into daily…, _row(), test_drops_zero_volume_flat_rows(), test_keeps_a_real_quiet_session_with_actual_volume(), test_keeps_rows_with_real_range()

### Community 9 - "Backend/Frontend Wiring Increment"
Cohesion: 0.25
Nodes (8): orazio/__init__.py (app factory), app.py (entry point), flask, flask-cors, static/index.html (page + wired UI), Increment 4: fix range/interval race conditions via threaded Flask + AbortController, Increment 5: minBarSpacing rendering-limit bug truncating 'All' range, Increment 5: pollQuote stale-symbol response guard

### Community 10 - "Real-Time Quotes & SENSEX Planning"
Cohesion: 0.40
Nodes (5): Prior-day drag-to-load history, Plan Increment 6: real-time quotes, SENSEX, futures naming, Rationale: avoid new yfinance calls by reusing existing quote poll, Spec Increment 6: true real-time quotes, SENSEX delay, futures naming, Rationale: NSE allIndices worse than Yahoo; Yahoo direct chart API is freshest for NSE indices; SENSEX delayed ~15min on Yahoo so BSE feed used instead

### Community 12 - "Live Chart Parity Planning"
Cohesion: 0.67
Nodes (3): Candle freshness fix (patch last candle each tick), Plan: Live chart parity + TradingView-style UX, Spec: Live chart parity + TradingView-style UX objective

## Knowledge Gaps
- **54 isolated node(s):** `npx`, `Settings`, `feedModal`, `feedRows`, `feedSort` (+49 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Live candles feature` connect `Charting UI & Indicators` to `Live Quote Sources & Caching`?**
  _High betweenness centrality (0.226) - this node is a cross-community bridge._
- **Why does `CAS terminal` connect `CAS Terminal (Auction Modals)` to `Live Quote Sources & Caching`?**
  _High betweenness centrality (0.224) - this node is a cross-community bridge._
- **Why does `BseStream` connect `BSE Push Stream Client` to `Live Quote Sources & Caching`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **What connects `npx`, `Settings`, `feedModal` to the rest of the system?**
  _54 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Live Quote Sources & Caching` be split into smaller, more focused modules?**
  _Cohesion score 0.059154929577464786 - nodes in this community are weakly interconnected._
- **Should `Charting UI & Indicators` be split into smaller, more focused modules?**
  _Cohesion score 0.08148148148148149 - nodes in this community are weakly interconnected._
- **Should `CAS Terminal (Auction Modals)` be split into smaller, more focused modules?**
  _Cohesion score 0.09102564102564102 - nodes in this community are weakly interconnected._