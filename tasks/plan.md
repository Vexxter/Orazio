# Plan: Live chart parity + TradingView-style UX

Source spec: `tasks/spec.md`

## Components

1. **Candle freshness fix** (backend: none; frontend: `static/index.html`)
   Patch the in-progress last candle from each 5s quote tick (update close/high/low,
   call `candleSeries.update()`), instead of waiting for the 60s full candle refetch.
   Keep the 60s refetch as the authoritative resync (fixes any drift/volume lag).

2. **Symbol map + left index rail** (backend: `app.py` `SYMBOL_ALIASES`; frontend: new
   sidebar in `static/index.html`)
   Add NIFTYIT/SPX/NASDAQ/DOWJONES/KOSPI/TAIEX aliases (tickers verified in spec). Static
   HTML list, one click = set `currentSymbol` + reload.

3. **Volume pane resize** (frontend only)
   `scaleMargins` on the histogram series: `top: 0.88, bottom: 0`ish so volume is a thin
   strip, not overlapping candles.

4. **Prior-day drag-to-load history** (backend: new `/api/candles/history`; frontend:
   scroll-triggered lazy load)
   - Backend: given `symbol`, `interval`, `before` (unix ts), fetch up to 7d of history
     at that interval (yfinance's real 1m ceiling) and return bars strictly before
     `before`, oldest-first, capped at one "page" (e.g. one extra trading day per call).
   - Frontend: `chart.timeScale().subscribeVisibleLogicalRangeChange()` — when the
     visible range nears the oldest loaded bar, call the endpoint, prepend results to
     the in-memory dataset, `setData()` the merged array, then restore the visible
     logical range so the view doesn't jump.
   - Depends on: nothing structurally, but must land before (5) since markers are drawn
     against the merged multi-day dataset.

5. **Session-boundary markers** (frontend only, depends on 4)
   Walk the merged candle array, detect each point where the calendar day changes,
   call `candleSeries.setMarkers()` with a small vertical marker + date label there.

6. **Cash/Futures toggle for global indices** (backend: `app.py` futures symbol map;
   frontend: toggle shown only for SPX/NASDAQ/DOWJONES)
   Map: SPX→ES=F, NASDAQ→NQ=F, DOWJONES→YM=F. Toggle switches `currentSymbol` between
   the cash and futures ticker and reloads candles/quote. Not shown for
   NIFTY/BANKNIFTY/NIFTYIT (spec decision: cash/spot only, no toggle).

7. **Option premium panel** (backend: new `/api/options`; frontend: modal/panel)
   - Backend: `Ticker(symbol).options` for expiries; `Ticker(symbol).option_chain(date)`
     for calls/puts. Return `{available: false, reason: "no option chain for this symbol"}`
     when `.options` is empty (this will be the actual response for NIFTY/BANKNIFTY/
     NIFTYIT — verified live during spec).
   - Frontend: a button on the symbol page opens the panel; shows expiry picker + a
     calls/puts premium table when available, an "unavailable" message otherwise.

## Build order

Independent, can be done in any order / parallel (no shared state, low risk):
- (2) symbol map + left rail
- (3) volume pane resize

Sequential (each depends on the previous landing and working):
1. (1) candle freshness fix — verify chart visibly keeps pace before touching anything else
2. (4) drag-to-load history — new endpoint + frontend lazy-load
3. (5) session-boundary markers — needs (4)'s merged dataset to draw against
4. (6) futures toggle — independent of 4/5, but sequenced after so the symbol-switch
   code path (already touched by (2)) is stable
5. (7) options panel — fully independent backend endpoint; do last since it's the most
   isolated, most likely to hit the "unavailable" data-gap path

## Risks & mitigations

- **yfinance rate limiting** from more frequent calls (per-tick patching avoids extra
  calls — it reuses the existing 5s quote poll, no new backend load). Only the history
  endpoint (4) and options endpoint (7) add new backend calls, and both are
  user-triggered (scroll / panel-open), not polled.
- **Lightweight-Charts jump-on-prepend**: prepending older bars via `setData()` resets
  the visible range unless explicitly restored — plan (4) accounts for this
  (`setVisibleLogicalRange` after merge).
- **Options/futures data gaps are real, not bugs** — both endpoints must return a
  structured `available: false` response, never throw a 500, so the frontend can render
  the "unavailable" state cleanly.

## Verification checkpoints

- After (1): watch the chart next to a live index quote for 2 minutes; last bar should
  never lag the printed price by more than ~5s.
- After (4)+(5): drag left from today's session on NIFTY 1m; should smoothly reveal
  prior day(s) up to ~5-7 days back with a marker at each boundary, no gaps/dupes.
- After (6): toggle on SPX loads ES=F and back; toggle absent entirely on NIFTY page.
- After (7): open options panel on AAPL (real data) and NIFTY (unavailable state) —
  both must render without console errors.

---

# Plan: Increment 6 (real-time quotes, SENSEX, futures naming)

Order (each step verified before the next):
1. Backend quote layer: `yahoo_live_quote()` (v8 meta, 1 KB), `bse_live_quote()` (SENSEX), remove NSE code,
   `/api/quote` returns `marketTime` + `source` + `delaySec`. Fallback chain v8 -> yfinance.
2. Backend metadata: futures display names + alias map exposed via `/api/config`.
3. Frontend live-bar rule uses the quote's own freshness (not the newest Yahoo bar's age), so delayed
   history (SENSEX, 15 min hole) no longer disables live candles.
4. Frontend freshness badge + friendly futures names + rail highlight for futures.
5. Verify with curl + devtools (NIFTY tick cadence, SENSEX age, futures labels), update README/spec/todo.

Risks: BSE/Yahoo endpoints are unofficial (mitigate: fallbacks, short timeouts, cached session for BSE);
a 15-minute hole between SENSEX's last Yahoo bar and the first live bar is shown as a time gap, not faked.

---

# Plan: Increment 10 (hover color, measure tool, full OHLC, breadth, movers, SMA200, light mode)

Source spec: `tasks/spec.md`, Increment 10. All four flagged design choices confirmed as proposed.

## Components

1. **Hover-color fix (Line/Area) + full OHLC legend words** (frontend only: `static/js/chart.js`,
   `static/js/data.js`)
   - `chart.js`: legend head/body text changes from `O`/`H`/`L`/`C` to `Open`/`High`/`Low`/`Close`
     (candle/bar: all four; line/area: `Close` only). Pure string/template change in `updateLegend()`.
   - Color: `lineSeries`/`areaSeries` currently take a fixed `color: COLORS.accent`. Add an
     `applyLineAreaColor(isUp)` helper that calls `lineSeries.applyOptions({color, ...})` /
     `areaSeries.applyOptions({lineColor, topColor, bottomColor})` with `COLORS.up`/`COLORS.down`
     variants, and recolors the legend's Close `<span class="num">` with the `up`/`down` class.
   - Driven by `pollQuote()` in `data.js`, which already has `q.change >= 0` — call the new helper
     there (same place the price chip already gets its up/down class) so it's session-vs-prevClose,
     matching assumption 1. No new endpoint.

2. **Full OHLC + hover color are pure frontend, zero backend risk** — build and verify first, since
   they're the smallest, most isolated pieces and immediately visible.

3. **200 SMA** (frontend only: `static/js/chart.js`, `static/index.html`, `static/styles.css`)
   - Add `sma200Series` next to `sma20Series`/`sma50Series` (new distinct color, e.g. `#4fd1c5`
     cyan — doesn't collide with amber/purple/up/down/accent).
   - `renderIndicators()`: extend with the `$('sma200').checked ? sma(latestCandles, 200) : []` branch
     (the existing `sma()` helper is period-agnostic, no change needed there).
   - `index.html`: one more `<label class="toggle">` checkbox next to SMA 20/50.
   - `prefs.js`: persist `sma200` alongside `sma20`/`sma50`.

4. **Market breadth** (backend: new `GET /api/breadth`; frontend: `static/js/rail.js`,
   `static/styles.css`)
   - Backend (`orazio/cas.py` or a new `orazio/breadth.py`): a `breadth_rows()` function that calls
     the already-cached `nse_get("/api/allIndices")`, and for each of `NIFTY_INDEX_NAMES` maps
     `{alias, advances, declines, unchanged}` — pure shaping function, unit-testable like
     `normalise_cas_rows`. New route in `routes.py`: `GET /api/breadth` returning
     `{indices: [...]}` for NIFTY/BANKNIFTY/NIFTYIT only (SENSEX and non-Indian indices simply
     absent from the list — no placeholder rows, per assumption 5).
   - Frontend (`rail.js`): after rendering rail buttons, a small poll (`setInterval`, 5s) hits
     `/api/breadth` and injects a `▲35 ▼15` line under the matching `.rail-item` (new child span,
     only for aliases present in the response).
   - Depends on: nothing else in this increment; fully independent, can build in parallel with (3).

5. **Top Gainers/Losers modal** (backend: new `GET /api/movers`; frontend: new `static/js/movers.js`,
   modal markup in `index.html`, new toolbar button)
   - Backend: a `movers(universe, direction)` function wrapping
     `nse_get("/api/live-analysis-variations", {"index": direction})` (direction = `gainers`/
     `loosers` — NSE's own spelling), then indexes into the response by `universe`
     (`allSec`/`NIFTY`/`BANKNIFTY`), shapes each row to `{symbol, ltp, perChange, open, high, low,
     volume}`. Route: `GET /api/movers?universe=allSec` returns
     `{gainers: [...], losers: [...], universe, asOf}`. Same one call serves both tables (NSE
     conveniently exposes `gainers`/`loosers` as sibling top-level calls; fetch both directions
     server-side in one route handler so the frontend gets both lists in one round trip).
   - Frontend (`movers.js`, follows the exact open/close/poll/render pattern already established by
     `cas-feed.js`): a toolbar button opens the modal; a 3-way segmented toggle (Market/NIFTY/
     BankNifty) switches `universe` and re-fetches; two tables (Gainers, Losers) sorted by
     `perChange` descending/ascending; polls every 10s while open, stops on close (same
     `clearInterval` pattern as every other modal here).
   - Depends on: nothing else; independent of (4) despite both touching NSE, since they hit
     different NSE endpoints.

6. **Two-point measure tool** (frontend only, new `static/js/measure.js`, `static/styles.css`)
   - New toolbar toggle button ("Measure", ruler icon) next to the existing chart-style select.
   - On activate: chart click handler (`chart.subscribeClick`) captures point A (time+price via the
     click param's `time` and the series' `coordinateToPrice`), draws nothing yet. Second click
     captures point B, and a DOM overlay (positioned via `timeToCoordinate`/`priceToCoordinate`,
     same technique as `renderDayLines`) draws a line between the two screen points plus a floating
     label with Δ price, Δ % `((B-A)/A*100)`, and bar/time span. Third click starts a fresh A.
     Escape or toggling the button off removes the overlay and unsubscribes the click handler.
   - Depends on: nothing else; can build any time. Riskiest single piece (most new interaction
     surface), so sequenced after the more mechanical items land and are verified.

7. **Light mode** (frontend only: `static/styles.css`, `static/js/state.js`, `static/js/chart.js`,
   `static/js/cas-movement.js`, `static/js/main.js`, `static/js/prefs.js`)
   - `styles.css`: new `:root[data-theme="light"] { ... }` block redefining every `--bg-*`/`--line*`/
     `--text*` token (accent/up/down/warn stay the same in both themes — they're semantic, not
     surface colors) plus `color-scheme: light`.
   - `state.js`: `COLORS` becomes a function `computeColors()` (re-reads `getComputedStyle` +
     `token()`/`alpha()`) instead of a frozen object computed once; export a `refreshColors()` that
     recomputes and mutates the existing `COLORS` object in place (keeps every existing `import {
     COLORS }` reference valid without touching every consumer file).
   - `chart.js`: a `applyThemeToChart()` that calls `chart.applyOptions()` (layout background/text/
     grid/border) and `applyOptions()` on every series (candle/bar/line/area/volume/sma20/50/200)
     with the refreshed `COLORS`.
   - `cas-movement.js`: since its quad charts are only ever built when the modal opens
     (`buildQuads()` already reads current `COLORS` fresh each call), no extra work needed there —
     document this as a known limitation: switching theme while the Live CAS modal is already open
     doesn't recolor it until it's closed and reopened.
   - `main.js`: new theme-toggle button handler: flip `document.documentElement.dataset.theme`,
     call `refreshColors()` + `applyThemeToChart()`, save via `prefs.js`.
   - `prefs.js`: persist `theme: 'dark' | 'light'`; default `'dark'` when absent (assumption 9).
   - Depends on: nothing else, but touches the most shared code (`COLORS`), so sequenced last —
     land and verify every other visual feature against the stable dark theme first, so a light-mode
     regression is never confused with a different increment's bug.

## Build order

Parallel-safe (independent, low risk, no shared state):
- (1)/(2) hover-color fix + full OHLC legend words
- (3) 200 SMA
- (4) market breadth
- (5) top movers

Sequential, after the above land and are verified:
1. (6) measure tool — new interaction surface, wants a stable chart to interact with first
2. (7) light mode — touches `COLORS`, which by now several of the above (hover-color fix, SMA200 color)
   will have added new call sites to; doing it last means recoloring logic only needs to be written once
   against the final set of series/colors, not revisited after each earlier item lands

## Risks & mitigations

- **NSE endpoint fragility** (both new backend calls hit unofficial NSE JSON endpoints, same as every
  existing NSE integration here): both new routes follow the established fallback pattern — return
  `{available: false, ...}` / an empty list, never a 500, on any NSE failure. No new risk class, same
  mitigation already proven in `cas.py`.
- **`COLORS` becoming mutable** is the one structural change with blast radius: every module that does
  `import { COLORS } from './state.js'` and reads a property at *call time* (not destructuring at
  import time into a local const) is safe; a quick grep before landing (7) confirms which consumers
  read `COLORS.x` live vs. cache it in a local — any caching call site needs updating to re-read.
- **Measure tool click-handling collision**: `chart.subscribeClick` firing while normal crosshair/pan
  is also active could double-fire. Mitigation: the click handler is only subscribed while Measure
  mode is active (subscribe on toggle-on, unsubscribe on toggle-off/Escape), not always-on.
- **SMA 200 on short ranges**: with <200 bars loaded (e.g. "1D" range on a symbol with a short
  session) the line simply doesn't render — same as SMA20/50 today, not a new failure mode.

## Verification checkpoints

- After (1)+(2)+(3): switch to Line style on an up day and a down day (or force via search to a
  currently-down symbol) — line/tag/legend all read green or red, never blue; legend shows full
  words in every chart style; SMA 200 checkbox draws once a wide-enough range is loaded.
- After (4): NIFTY/BANKNIFTY/NIFTYIT rail rows show live counts that change on their own within a
  few polls; SENSEX and every non-Indian row show nothing extra.
- After (5): open Top Movers, confirm two sorted tables render for the market default, and switching
  to NIFTY/BankNifty changes the data.
- After (6): measure between two visibly different bars, confirm the Δ% matches a hand calculation;
  confirm Escape and re-toggling both clear it cleanly with no leftover DOM.
- After (7): toggle light mode, confirm rail/toolbar/modals/chart all recolor together (open each
  modal once to confirm), reload the page and confirm the choice persisted, toggle back to dark and
  confirm nothing regressed from (1)-(6).
