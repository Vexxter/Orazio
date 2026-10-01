- [x] Task: Extend `SYMBOL_ALIASES` with NIFTYIT/SPX/NASDAQ/DOWJONES/KOSPI/TAIEX
  - Acceptance: `/api/quote?symbol=NIFTYIT` (etc. for all 6) returns the correct
    Yahoo-ticker price (^CNXIT, ^GSPC, ^IXIC, ^DJI, ^KS11, ^TWII)
  - Verify: curl each alias and diff against the raw ticker — all 6 confirmed live
  - Files: app.py (also added `/api/config` exposing `quickIndices` + `futuresMap` for
    the frontend rail/toggle tasks)

- [x] Task: Frontend left index rail (NIFTY, BANKNIFTY, NIFTYIT, SPX, NASDAQ, DOWJONES, KOSPI, TAIEX)
  - Acceptance: clicking any entry sets it as `currentSymbol` and reloads candles+quote;
    active entry visually highlighted
  - Verify: rendered from `/api/config`'s `quickIndices`; page loads at 200 with the
    new `#rail` markup. **Not yet click-tested in an actual browser** — flag this for a
    manual pass.
  - Files: static/index.html

- [x] Task: Shrink volume pane
  - Acceptance: volume histogram's `scaleMargins` gives it ~10-12% of pane height and no
    longer visually overlaps candle wicks/bodies at default zoom
  - Verify: `scaleMargins.top` raised 0.8 → 0.88 (volume now ~12% of pane height).
    **Not yet visually confirmed in-browser.**
  - Files: static/index.html

- [x] Task: Patch last candle from live quote ticks instead of waiting on 60s refetch
  - Acceptance: on each 5s `/api/quote` poll, update the last bar's close/high/low (and
    call `candleSeries.update()`); keep the existing 60s `loadCandles` as the
    authoritative resync
  - **Finding: this already existed in the codebase** (index.html pollQuote, lines
    ~304-314) before this build session — it was not actually the bug. The 1-minute lag
    the user perceives is most likely yfinance/Yahoo's own upstream delay on Indian
    index quotes, which this app cannot control (see spec assumption 1). No code change
    made here beyond what was already present.
  - Files: static/index.html (no change)

- [x] Task: Add `/api/candles/history` endpoint for older intraday bars
  - Acceptance: `GET /api/candles/history?symbol=&interval=&before=<unix_ts>` returns
    bars strictly earlier than `before`, oldest-first, sourced from up to 7d of yfinance
    intraday history; returns `{available: false}`-style empty result gracefully past
    the 7-day ceiling instead of erroring
  - Verify: curled with `before=now` on NIFTY 1m — returned 293 bars (one full prior
    session), `exhausted: false`; response is capped to one trading day per call
  - Files: app.py

- [x] Task: Frontend drag-to-load-previous-day
  - Acceptance: scrolling/panning the chart left past the oldest loaded bar triggers a
    call to `/api/candles/history`, prepends results to the dataset via `setData()`, and
    restores the visible logical range so the view doesn't jump; repeats up to ~5-7 days back
  - Verify: implemented via `subscribeVisibleLogicalRangeChange` (fires when scrolled
    within 10 bars of the start) calling `loadMoreHistory()`, which prepends and
    re-anchors the visible logical range by the added bar count. Backend endpoint
    verified separately (293 bars/call). **Not yet drag-tested in an actual browser.**
  - Files: static/index.html

- [x] Task: Session-boundary markers
  - Acceptance: `setMarkers()` places a marker + date label at the first bar of each
    calendar day once multi-day data is loaded
  - Verify: `renderSessionMarkers()` walks `latestCandles` comparing IST day-keys,
    applies to whichever series is active, re-applied after style switches and after
    history prepends. **Not yet visually confirmed in-browser.**
  - Files: static/index.html

- [x] Task: Futures ticker map + cash/futures toggle (SPX/NASDAQ/DOWJONES only)
  - Acceptance: a toggle switches `currentSymbol` between cash (^GSPC/^IXIC/^DJI) and
    futures (ES=F/NQ=F/YM=F) and reloads candles+quote; toggle is not rendered at all
    when `currentSymbol` is NIFTY/BANKNIFTY/NIFTYIT
  - Verify: `FUTURES_MAP` (app.py) served via `/api/config`; frontend shows/hides
    `#futures-toggle` based on whether the resolved symbol has a cash/futures
    counterpart. **Not yet toggle-tested in an actual browser.**
  - Files: app.py, static/index.html

- [x] Task: `/api/options` endpoint
  - Acceptance: `GET /api/options?symbol=&expiry=` returns `{available: true, expiries,
    calls, puts}` when `Ticker(symbol).options` is non-empty, else
    `{available: false, reason: "..."}` — never a 500 for a symbol with no chain
  - Verify: curled AAPL (available: true, 107 call strikes, 2 expiries) and NIFTY
    (available: false, "no option chain for this symbol") — matches spec's verified gap
  - Files: app.py

- [x] Task: Frontend option premium panel
  - Acceptance: a button opens a panel; on a symbol with `available: true` it shows an
    expiry picker + calls/puts premium table; on `available: false` it shows a plain
    "options data unavailable for this symbol" message, no console errors either way
  - Verify: modal wired to `/api/options`, renders expiry select + calls/puts tables on
    success or the unavailable message otherwise. Backend confirmed separately (AAPL
    available, NIFTY not). **Not yet opened in an actual browser.**
  - Files: static/index.html

---

## Increment 2

- [x] Task: Fix subscribeVisibleLogicalRangeChange firing on programmatic range changes
  - Acceptance: a suppress flag guards loadCandles/loadMoreHistory/zoom-switch so the
    history-prefetch and zoom-interval listeners only react to genuine user scroll,
    not fitContent()/setData() side effects; loadMoreHistory also defensively filters
    out any incoming row whose time is not strictly less than the current oldest bar
  - Verify: `suppressRangeEvents` set at the top of loadCandles/loadMoreHistory, cleared
    ~80ms after their final chart mutation; both listeners check it first. Also fixed a
    second bug found during this pass: the 60s auto-refresh called fitContent()
    unconditionally, resetting zoom/pan every minute even while idle — now passes
    `preserveView: true`. **Not confirmed in an actual browser** (no devtools MCP here).
  - Files: static/index.html

- [x] Task: Replace on-chart day markers with time-axis boundary labels
  - Acceptance: candleSeries.setMarkers() no longer used; tickMarkFormatter shows a
    full date+time label instead of just time when a tick lands on a session-boundary
    bar; no arrow/label drawn over candle bodies
  - Verify: `setMarkers` calls removed entirely; `computeDayBoundaries()` populates a
    Set consulted by `tickMarkFormatter`. **Not visually confirmed in-browser.**
  - Files: static/index.html

- [x] Task: Mouse-wheel granularity auto-switch (TradingView-style)
  - Acceptance: zooming out/in past defined visible-span thresholds switches the
    interval dropdown and reloads candles at the new interval while preserving the
    current visible time window (no fit-to-content reset)
  - Verify: `subscribeVisibleTimeRangeChange` (debounced 350ms) → `intervalForSpanSeconds`
    thresholds → `loadCandles({ interval, range, preserveView: true })`. Also explicitly
    enabled `handleScroll.mouseWheel`/`handleScale.mouseWheel` (were implicit defaults).
    **Not confirmed in-browser.**
  - Files: static/index.html

- [x] Task: NSE low-latency quote source for NIFTY/BANKNIFTY/NIFTYIT
  - Acceptance: /api/quote tries nseindia.com/api/allIndices (session-cookie handshake,
    cached ~4min) for these 3 symbols first, falls back to yfinance on any failure;
    other symbols unaffected
  - Verify: curled NIFTY — `"source": "nse"`, live price returned. CHINA/SENSEX curled
    and confirmed `"source": "yfinance"` (unaffected, as intended).
  - Files: app.py

- [x] Task: Add SENSEX + CHINA (000001.SS) to quick-access rail
  - Acceptance: QUICK_INDICES includes SENSEX and CHINA; /api/config reflects both
  - Verify: curled /api/config — both present (10 total); /api/quote?symbol=CHINA
    resolves to 000001.SS with a live CNY price
  - Files: app.py

---

## Increment 3

- [x] Task: Show year in date labels (tick axis + crosshair tooltip)
  - Files: static/index.html (dateFmt/dateTimeFmt now include year:numeric)
- [x] Task: Disable SMA20/SMA50 by default
  - Files: static/index.html (checked attribute removed)
- [x] Task: Rename app to Orazio
  - Files: static/index.html (<title>, <h1>)
- [x] Task: Shrink volume further + rebalance price-scale margins
  - Files: static/index.html (volume top margin 0.88->0.93; rightPriceScale bottom 0.3->0.35, top 0.1->0.08, autoScale explicit)
- [x] Task: Replace tick-label day-boundary hint with thin dotted vertical line overlay
  - Files: static/index.html (#day-lines DOM overlay, positioned via timeToCoordinate, updates on pan/zoom/resize)

---

## Increment 4 — real browser testing via Playwright (chrome-devtools MCP still not active)

Since the MCP restart had not happened yet, installed Playwright directly (`npm install playwright` + `npx playwright install chromium`) and drove real headless Chrome against the running Flask server to reproduce the reported "bugs out on range switch" issue instead of guessing further.

- [x] Task: Root-cause + fix "switch range back to 1D goes to extreme right / wrong granularity"
  - Finding 1 (confirmed via 5+ real browser runs): clicking a range button reused whatever
    interval a WIDER previous range had auto-escalated to (e.g. 1h from YTD), because the
    backend interval ladder only escalates to coarser, never back down. Fix: range-bar
    clicks now always request interval=1m baseline explicitly.
  - Finding 2 (the actual "still shows 5m for a plain 1D view" bug): the mouse-wheel
    auto-granularity feature (increment 2) thresholded on CALENDAR TIME SPAN ("more than
    2 hours visible = zoomed out"). A completely normal single trading day of 1m bars
    spans 6+ hours, so it was self-triggering on every ordinary load, not just real zoom
    gestures. Rewrote to threshold on VISIBLE BAR COUNT instead (40-500 comfortable
    band) — market/timezone-agnostic, verified via repeated automated clicks that a
    plain 1D/1m load now correctly stays at 1m.
  - Finding 3 (real race, confirmed via network-timed repro): rapid clicking queued
    requests server-side because Flask's dev server is single-threaded by default —
    your latest click's data had to wait behind a backlog of stale requests you no
    longer wanted. Fixed with `threaded=True` on app.run, plus client-side
    AbortController so superseded fetches are actually cancelled (not just ignored on
    arrival) — verified via request-log inspection that stale requests now show
    net::ERR_ABORTED instead of queuing.
  - Also added a loadGeneration counter as defense-in-depth against any response that
    still lands after being superseded.
  - Verify: 5-scenario automated stress test (rapid range clicks, range+symbol race,
    style+range race, rapid rail clicks, futures-toggle+range race) — all pass cleanly
    with matching visible-range/data state and zero console/page errors, screenshot
    confirms correct rendering.
  - Files: app.py (threaded=True), static/index.html (bar-count granularity logic,
    AbortController, range-button interval reset)

- [x] Task: Fix search-dropdown reappearing after Enter (found during this testing pass, not user-reported)
  - Acceptance: pressing Enter to select a typed symbol cancels the pending debounced
    search fetch so it can't reopen the results dropdown afterward
  - Files: static/index.html

---

## Increment 5 — QA subagent findings (real chrome-devtools MCP testing)

Spawned a QA subagent with live chrome-devtools MCP access to manually test every feature
like a real user. Findings and fixes:

- [x] Task: Fix "All" (and any very-large-bar-count range) silently truncating to recent data
  - Finding: Lightweight-Charts default minBarSpacing (0.5px) caps how far fitContent()
    can zoom out — past ~2300 bars on a ~1150px chart it clamps and anchors to the most
    recent data with zero visual indication. "All" (4662 daily bars) hit this: only the
    most recent ~2170 bars were ever shown despite currentRange/interval state being
    100 orrect — this was a pure rendering-limit bug, unrelated to any of the
    race-condition fixes from prior increments.
  - Fix: set timeScale.minBarSpacing: 0.05 at chart creation.
  - Verify: after fix, `getVisibleLogicalRange()` for ALL (4662 bars) = {from:0, to:4661}
    (previously {from:2502, to:4661}) — confirmed via live devtools + screenshot showing
    full 2007-2026 history in one view.
  - Files: static/index.html

- [x] Task: Fix pollQuote() applying a stale-symbol response after a rapid symbol switch
  - Finding: unlike loadCandles() (already guarded with loadGeneration+AbortController),
    pollQuote() had no guard — a quote fetch issued for the pre-switch symbol could
    resolve after the switch and overwrite the price display with the WRONG symbol's
    number, and (when range===1D) fold that wrong price into the current chart's last
    candle. Reproduced by the QA subagent: NASDAQ's price (26418.30) appeared on the
    NIFTY UI mid-switch.
  - Fix: capture `currentSymbol` at fetch time, discard the response if it no longer
    matches `currentSymbol` when the fetch resolves (same pattern as loadCandles).
  - Verify: 20 rounds of rapid BANKNIFTY->SPX->NASDAQ->NIFTY switching + pollQuote()
    calls — final displayed price (23334.70) matched a fresh curl of /api/quote?symbol=
    NIFTY exactly, no cross-symbol contamination.
  - Files: static/index.html

- [x] Task: Add a "Loading…" indicator during candle fetches
  - Rationale: the QA subagent could NOT reproduce the user's literal "ALL/YTD -> 1D
    doesn't readjust" complaint after extensive adversarial-timing testing (40+
    iterations, concurrent backend stress) — state was always internally consistent
    once a ~1.5-2.5s yfinance round-trip settled. Working theory: with zero loading
    feedback, an impatient click during that window reads as "broken" even though it
    resolves correctly. This is a mitigation for that perception, not a fix for a
    confirmed bug.
  - Files: static/index.html (reuses the existing #note element)

- Not yet tested this pass (per subagent time-box): wheel-zoom granularity, drag/pan
  lazy-load visual smoothness, style+range combos, SMA/Volume toggles, futures toggle,
  search-box dropdown, 70s-idle-no-jump. Recommend a follow-up pass if issues persist
  in these areas.
- New minor cosmetic finding (not yet fixed, not user-reported): at extreme zoom-out
  (e.g. ALL range with decades of volume history), the main price axis bleeds into
  negative-looking tick labels to accommodate the volume pane's reserved bottom
  margin. Cosmetic only, flagged for a future pass.

---

## Increment 6

- [x] Task: Backend live-quote layer (Yahoo v8 + BSE), drop NSE allIndices
  - Acceptance: /api/quote NIFTY returns marketTime <=15s old; SENSEX source=bse and <=60s old
  - Verify: curl x5 over 30s; compare to direct v8/BSE calls
  - Files: app.py
- [x] Task: Futures metadata (names, alias) in /api/config
  - Acceptance: config lists ES=F -> "S&P 500 Futures (ES)", alias SPX
  - Files: app.py
- [x] Task: Frontend live-bar rule keyed to quote freshness (fixes SENSEX 15-min hole)
  - Files: static/index.html
- [x] Task: Freshness badge + friendly futures names + rail highlight on futures
  - Files: static/index.html
- [x] Task: Docs (README data-source table) and spec sync
  - Files: README.md, tasks/*

Results (verified live, market open): NIFTY/BANKNIFTY/NIFTYIT/stocks ticks 1-5s old at 30-120ms per call
(was ~2s per call and up to 2 min stale via NSE); SENSEX from BSE at ~65s (was ~900s); status badge shows
"Live - 6s" / "Delayed 10m" / "Closed"; futures show "S&P 500 Futures (ES)" and the rail keeps SPX active.
Open: SENSEX has a ~15 min hole between Yahoo's last bar and the first live BSE bar (shown, not faked).

---

## Increment 7

- [x] Task: Rebuild SENSEX intraday bars from BSE (Yahoo delays the bars, not just the price)
  - Acceptance: newest SENSEX candle <=2 min old, candles not flat
  - Verify: newest bar age 64s then 74s in-browser (was 989s); 12:59 and 13:00 bars carry real OHLC
  - Files: app.py (live-bar poller + splice in /api/candles)
- [x] Task: /api/cas endpoint (pre-open + closing session, NSE + BSE)
  - Verify: curl returns phase `waiting:post-close`, 9904s remaining, open/change for the 4 Indian
    indices, explicit unavailable for the other 7
  - Files: app.py
- [x] Task: Call Auction panel under the index rail
  - Verify: in-browser — phase "Post-close in 2h 43m", 4 index rows, unavailable note, collapse
    persists; no console errors
  - Files: static/index.html, static/styles.css
- [x] Task: Raise the live-badge threshold to 150s for minute-stamped feeds
  - Files: static/index.html
- [x] Task: Docs (README SENSEX + CAS sections, API table, spec, todo)
  - Files: README.md, tasks/*

Not verified: the CAS panel during an actual auction window (next pre-open 09:00 IST). Built and
tested against this morning's frozen pre-open snapshot and the live allIndices fields.

- [x] Task: Live CAS feed window (per-stock auction data + order book)
  - Acceptance: opens from the CAS panel; shows IEP/change/ATO/buy/sell per stock, sortable and
    filterable; row click reveals the 10-rung auction order book; refreshes every 3s; states
    live-vs-snapshot with a timestamp
  - Verify: in-browser - 210 F&O rows, breadth 93/97/20, sort by symbol -> 360ONE, filter
    "RELIANCE" -> 1 row, order book renders 10 rungs with the IEP rung marked; ladder stayed at
    10 rungs across 8 samples over 7s (an earlier version blanked it on every poll); no console errors
  - Files: app.py (/api/cas/feed), static/index.html, static/styles.css

- [x] Task: Correct CAS timings against primary documentation
  - Was: pre-open 09:00-09:15 + "post-close" 15:40-16:00 (wrong, from memory)
  - Now: pre-open 09:00-09:15, closing auction 15:15-15:35, post-market 15:50-16:00, each with
    per-stage labels; phase read from NSE marketStatus with the clock only for countdowns
  - Verify: cas_phase() walked across 14 times of day + a Saturday - every phase, stage and
    countdown correct; all five UI states render; no console errors
  - Files: app.py, static/index.html, static/styles.css, README.md

- [x] Task: Point the live feed at NSE's real closing-auction endpoint (casApi/getCASData)
  - Verify: endpoint answers with 210 eligible symbols; feed routes to CAS during the closing
    auction and to pre-open otherwise; renders CAS columns, the reference-price-stage empty state,
    and an order book with NSE's flag shown verbatim; no console errors
  - NOT verified against real rows (empty outside 15:15-15:35) - see spec 7d
  - Files: app.py, static/index.html, static/styles.css, README.md

## Increment 8

- [x] Task: BSE push-stream client (bse_stream.py) with verified TLS
  - Verify: connected, 3-4 ticks in 14s with stamps ~3s behind wall clock; TLS verified via AIA intermediate
- [x] Task: SENSEX quote + candles from the stream (REST as fallback)
  - Verify: quote age 2-3s (was 65-88s); bars have real ranges 10.40 / 17.66 / 8.52
- [x] Task: /api/cas/movement + separate "Live CAS movement" window for all 11 indices
  - Verify: 11 cards, 4 live with sparklines (SENSEX 95 points in ~10s), 7 honestly unavailable, no console errors
- [x] Task: verify real CAS rows against the recorder capture (done at 15:21; mapping corrected, see spec 8c)
- [x] Task: add websockets / certifi / cryptography to requirements.txt

- [x] Task: Redesign Live CAS as a 2x2 quadrant window, Indian indices only, measured against the 15:14:59 reference
  - Verify: 4 quadrants, each with a live chart; reference locked at 15:15:00 with real values; dotted REF
    line, green/red about it, header delta in pts and %; other markets removed; no console errors
  - Files: app.py, static/index.html, static/styles.css, README.md

- [x] Task: Correct the CAS row mapping against real data (IEP, imbalances, bands, equilibrium-rung flag)
- [x] Task: Persist reference + chart history so a server restart cannot wipe them mid-auction

## Increment 9
- [x] Task: use NSE's official close when Yahoo's NSE-index tick is stale (fixes NIFTY showing 23429.00 vs the official 23414.30)
  - Verify: all four indices match the official closes; RELIANCE.NS / SPX / KOSPI unchanged
  - Files: app.py, static/index.html
- [x] Task: README - per-index data-source map, source priority, what is not real-time
- [ ] Known gap: NSE-index candle chart ends at 15:14 (no Yahoo bars for the auction)

---

## Increment 10 (spec: tasks/spec.md § Increment 10; plan: tasks/plan.md § Increment 10)

- [x] Task: Full OHLC legend words
  - Acceptance: legend shows "Open"/"High"/"Low"/"Close" in Candle/Bar mode, "Close" alone in
    Line/Area mode, for both the default (last-bar) and hover (crosshair-bar) states
  - Verify: hover the chart in each of the 4 chart styles, screenshot, confirm full words
  - Files: static/js/chart.js

- [x] Task: Hover-color fix — Line/Area series, axis tag, and legend Close value follow up/down
  - Acceptance: `lineSeries`/`areaSeries` color and the legend's Close value switch between
    `--up`/`--down` based on current price vs. session previous close (not a fixed blue); Candle/Bar
    styles unchanged
  - Verify: force a down day (or a currently-down symbol) and an up day in Line style — confirm red
    vs. green on the line, its axis tag, and the legend value, matching the price chip's own color
  - Files: static/js/chart.js, static/js/data.js

- [x] Task: 200 SMA
  - Acceptance: a new "SMA 200" checkbox draws a 4th distinct-colored line using the existing
    period-agnostic `sma()` helper; empty until 200 bars are loaded, same as SMA 20/50
  - Verify: enable on a range with 200+ bars, confirm the line draws; enable on a short range,
    confirm it silently draws nothing (no error)
  - Files: static/js/chart.js, static/index.html, static/js/prefs.js

- [x] Task: `GET /api/breadth` — live advances/declines for NIFTY/BANKNIFTY/NIFTYIT
  - Acceptance: returns `{indices: [{alias, advances, declines, unchanged}, ...]}` for exactly the
    3 NSE-covered indices, sourced from the already-cached `allIndices` call (no new NSE traffic);
    never 500s
  - Verify: curl `/api/breadth`, confirm 3 rows with live-looking advances/declines
  - Files: orazio/cas.py (or new orazio/breadth.py), orazio/routes.py, tests/test_breadth.py

- [x] Task: Rail breadth counts (frontend)
  - Acceptance: NIFTY/BANKNIFTY/NIFTYIT rail rows show a small "▲35 ▼15" line that updates every 5s
    without a page reload; every other rail row shows nothing extra
  - Verify: in-browser, watch counts change across a couple of poll cycles; confirm no line appears
    under SENSEX/SPX/etc.
  - Files: static/js/rail.js, static/styles.css

- [x] Task: `GET /api/movers` — top gainers/losers by universe
  - Acceptance: `?universe=allSec|NIFTY|BANKNIFTY` returns `{gainers: [...], losers: [...], universe,
    asOf}`, each row `{symbol, ltp, perChange, open, high, low, volume}`; never 500s
  - Verify: curl all 3 universes, confirm sorted, non-empty lists during market hours
  - Files: orazio/cas.py (or new orazio/movers.py), orazio/routes.py, tests/test_movers.py

- [x] Task: Top Gainers/Losers modal (frontend)
  - Acceptance: new toolbar button opens a modal defaulting to whole-market movers; a segmented
    Market/NIFTY/BankNifty toggle re-fetches; two tables (Gainers, Losers) sorted by % change;
    polls every 10s while open, stops on close
  - Verify: in-browser, open modal, confirm both tables populated, switch universe, confirm data
    changes, close and confirm polling stops (no lingering network calls)
  - Files: static/js/movers.js (new), static/index.html, static/styles.css, static/js/main.js

- [x] Task: Two-point measure tool
  - Acceptance: a "Measure" toolbar toggle; click-click on the chart draws a line + label with
    Δ price and Δ % between the two points; a third click starts fresh; Escape or toggling off
    clears it; no interference with normal pan/zoom/crosshair when inactive
  - Verify: in-browser, measure across a few different bar spans in both directions (price up and
    down), confirm the Δ% matches a hand calculation; confirm clean teardown on Escape and re-toggle
  - Files: static/js/measure.js (new), static/index.html, static/styles.css, static/js/main.js

- [x] Task: Light mode
  - Acceptance: a theme toggle button flips the whole app (rail, toolbar, all modals, chart colors)
    between the existing dark theme and a new light theme; defaults to dark; choice persists across
    reload
  - Verify: in-browser, toggle on, confirm every surface recolors including an already-open chart's
    series/legend/axes; open each modal once under light mode to confirm it recolors too; reload,
    confirm the choice persisted; toggle back to dark, confirm no regression in items above
  - Files: static/styles.css, static/js/state.js, static/js/chart.js, static/js/main.js,
    static/js/prefs.js

- [x] Task: Docs sync
  - Acceptance: README features list mentions the measure tool, breadth counts, top movers, SMA 200,
    and light mode
  - Files: README.md, tasks/*
