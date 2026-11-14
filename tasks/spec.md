# Spec: Drawing tools, Bar replay, Screener

Status: DRAFT v2 (answers folded in: drag/edit IN, RSI/MA filters IN, right-side panel). Waiting for approval.

## Objective
Close three gaps that send people back to TradingView:
1. **More drawing tools.** Today there are only trendline, H-line and measure.
2. **Bar replay.** Step through history bar by bar to practise reading charts without seeing what comes next.
3. **Screener.** Filter and sort NSE stocks by price, volume and 52-week position, then click a row to chart it.

The user is a single trader running Orazio locally. Out of scope: alerts/notifications (rejected), broker APIs (rejected), and any new paid or keyed data source.

## Tech stack (unchanged)
- Backend: Flask + Python, `orazio/` modules, `nse_get` for NSE, `cached()` for TTLs.
- Frontend: plain ES modules with no build step, Lightweight Charts **4.1.3** (no primitives API; drawings are a DOM/SVG overlay, as in `draw.js`).
- No new dependencies.

## Commands
```
python app.py                                  # dev server, http://localhost:5000
python -m pytest                               # backend tests (~500, no network)
npm test                                       # frontend pure-logic tests (node --test)
python scripts/smoke.py                        # live-feed check against running server
```

## Project structure (new/changed files)
```
static/js/draw-math.js        NEW  pure geometry: fib levels, channel offset, ray, rect, hit-test + drag deltas; unit-tested
static/js/draw.js             CHG  new tool modes + renderers, same store and anchor model
static/js/replay-policy.js    NEW  pure: slice bars at cursor, step, speed → interval
static/js/replay.js           NEW  UI: pick start, play/pause/step/speed/exit; drives chart.js render
static/js/chart.js            CHG  render from replay slice when replay is active
static/js/data.js / live-quote.js CHG  live ticks must not touch the chart while replaying
static/js/screener.js         NEW  panel: table, filters, sort, click → load symbol
static/js/screener-policy.js  NEW  pure: filter + sort rows; unit-tested
orazio/screener.py            NEW  NSE market-watch rows + merged daily technicals, cached
orazio/technicals.py          NEW  batched yfinance 1y daily → RSI14, SMA20/50/200 per stock; parquet cache, daily refresh
orazio/routes/market.py       CHG  GET /api/screener
static/index.html, styles.css CHG  buttons + panels
tests/frontend/draw-math.test.mjs, replay-policy.test.mjs, screener-policy.test.mjs   NEW
tests/test_screener.py, tests/test_technicals.py   NEW
```

## Feature 1: Drawing tools
Add five tools to the same toolbar group, all stored per symbol in `orazio.drawings.v1` using the existing `{t, price}` anchors (so they keep working on any interval):

| Tool | Clicks | Draws |
|---|---|---|
| Fibonacci retracement | 2 | levels 0, .236, .382, .5, .618, .786, 1 between A and B, labelled with level + price |
| Rectangle | 2 | box from A to B, translucent fill, shows Δprice and Δ% |
| Horizontal ray | 1 | line from the click to the right edge only |
| Parallel channel | 3 | line A→B, plus a parallel copy through C |
| Text note | 1 + type | a short label (≤ 80 chars) anchored at the click |

- Same lifecycle as today: one active tool at a time (mutually exclusive with measure), Esc cancels the pending point, then the tool, × deletes, and Clear wipes all.
- Old saved drawings (`trend`, `hline`) load unchanged.
- **Drag/edit (in v1):**
  - Hovering a drawing shows round handles on each anchor point; dragging a handle moves that point.
  - Dragging the body moves the whole drawing, with every anchor shifted by the same Δt and Δprice.
  - The chart's own pan/scroll is suspended while a drag is in progress, and it saves on mouseup.
  - Double-clicking a text note edits its text.
  - This applies to all tools, including the existing trendline and H-line (an H-line drags vertically only).
- **Not in v1:** colour picker, drawings shared across symbols, touch drag (mouse only; marked `ponytail:`).

## Feature 2: Bar replay
- A **Replay** button enters pick mode, and a click on a bar sets the cursor there. Every bar after the cursor is hidden, along with every indicator value computed from those bars.
- Controls bar: ⏮ exit · ⏯ play/pause · ⏭ step +1 bar · speed 1 / 3 / 10 bars per second · a "Replaying from <date>" label.
- Keys: Space = play/pause, → = step.
- While replaying, live ticks and history refreshes do **not** change the chart. They keep updating `state.latestCandles` in the background, and Exit restores the live chart.
- Changing symbol or interval exits replay.
- Indicators (MA/VWAP/BB/RSI/MACD) and drawings work on the replayed slice.
- **Not in v1:** buy/sell paper trades inside replay, multi-timeframe replay, or replaying past the bars already loaded. Replay uses whatever history is loaded, and "drag back for older days" still works before entering.

## Feature 3: Screener
- **Data source:** NSE market watch `getIndicesData` (already used by `stats.py`). One call returns every constituent of a chosen universe with ltp, % change, volume, value, 52-week high/low, 30-day % and 365-day %. TTL 10 s.
- **Universes:** NIFTY 50, NIFTY BANK, NIFTY 500 (default), NIFTY TOTAL MKT (~750).
- **Technicals:**
  - `technicals.py` makes one batched `yf.download(..., period="1y", interval="1d")` call for the universe, the same pattern as `constituents._fetch_ohlcv`.
  - It refreshes once per trading day after 15:45 IST, or at startup if the cache is from an older day. The cache lives at `~/.orazio/technicals.json` (stdlib, ~1.5 MB).
  - Computed per stock: RSI(14), SMA 20/50/200, and the price's % distance from each SMA. The flags `golden50_200` / `death50_200` mean a 50/200 cross within the last 5 sessions.
  - The live LTP from market watch replaces today's close before RSI and the distances are computed, so they move intraday. The SMAs themselves stay on daily closes.
  - The first fetch for 500 stocks takes ~20–40 s (to be measured). Until it finishes, the technical columns show "…" and the price/volume filters still work.
- **Columns:** Symbol · LTP · %chg · Volume · Value (₹ Cr) · % from 52w high · % from 52w low · 30d % · 1y % · RSI14 · % vs SMA50 · % vs SMA200.
- **Filters** (min/max per numeric column, combined with AND), plus presets: *Near 52w high (≤ 2%)*, *Near 52w low (≤ 2%)*, *Top gainers*, *Top losers*, *Most active (value)*, *RSI < 30*, *RSI > 70*, *Above SMA200*, *Golden cross (5d)*.
- Click any column header to sort. Click a row to load it on the main chart; the panel stays open.
- Filters and sort are saved in `prefs.js`.
- It degrades the same way the rest of the app does: if NSE is empty or blocked, the panel shows "Screener data unavailable", with no error and no stale numbers older than 10 minutes.
- **Not in v1:** custom indicator formulas, intraday-timeframe technicals, OI/F&O filters, US stocks, and the TOTAL MKT universe for technicals (NIFTY 500 max, to stay under Yahoo's rate limit).

## Code style
Follow the existing modules: a top-of-file comment explaining *why*, pure logic in `*-policy.js` / `*-math.js` with no DOM, and the DOM in the feature module. Example of the pattern to copy:
```js
// draw-math.js
export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
export function fibPrices(a, b) {
  return FIB_LEVELS.map(l => ({ level: l, price: b.price - (b.price - a.price) * l }));
}
```
Backend: one module per concern, `cached(key, ttl, fetch)`, return `{"available": bool, ...}`, never raise to the route.

## Testing strategy
- **Pure JS** (`node --test`): fib levels, channel offset, ray/rect geometry, hit-test and drag deltas, replay slicing and step bounds, screener filter/sort/presets.
- **Backend** (pytest, NSE + yfinance mocked as in existing tests): row shaping, % from 52w maths, RSI/SMA values against a hand-computed fixture, cross detection, cache-staleness rule, missing fields → `null` not crash, universe whitelist, the empty/blocked → `available: false` path, and the `/api/screener` contract.
- **Wiring:** extend `tests/test_frontend_wiring.py` for the new button and panel IDs.
- **Manual:** one browser pass per feature (place each tool, reload, switch interval; replay 50 bars then exit; filter, sort, click a row).

## Boundaries
- **Always:** keep `npm test` and `pytest` green, keep pure logic in tested modules, and keep the existing drawings readable.
- **Ask first:** any new data source/endpoint beyond NSE market watch, changing the drawings storage key/format, or adding a dependency.
- **Never:** broker APIs, notifications, scraping that needs login, or breaking the CAS terminal or live stream.

## Success criteria
1. All five tools place correctly, survive reload and an interval switch (1m ↔ 1D), and delete individually. Old trend/hline drawings still render. Dragging a handle or a body moves the drawing, the chart doesn't pan during the drag, and the new position survives reload.
2. Replay: after picking a bar, no bar or indicator value later than the cursor is visible; play advances at the chosen speed (±10%); a live tick during replay doesn't move the chart; Exit returns the exact live chart.
3. Screener: NIFTY 500 loads in < 2 s on a warm cache; RSI14 matches the chart's RSI study for the same stock on 1D within 0.5; preset "Near 52w high" returns only rows with `(high − ltp)/high ≤ 2%`; a row click charts that stock; the NSE-blocked path shows the unavailable state.
4. `npm test` and `python -m pytest` both pass, with new tests included.

## Decisions (2026-10-19)
- Drag/edit drawings: **in v1**.
- RSI/MA screener filters: **in v1**, from a daily batched yfinance fetch.
- Screener placement: **right-side panel**, like Options/News.

## Open questions
- None blocking. The first-fetch time for technicals will be measured in the task that builds it; if it's above 60 s, the plan is to drop the universe to NIFTY 200.
