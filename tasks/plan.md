# Plan: Drawing tools, Bar replay, Screener

Spec: [spec.md](spec.md). The three features are independent, so each is a vertical slice with its own tests.

## Measured before planning (2026-10-19)
- NSE `getIndicesData` for NIFTY 500 returns 500 rows in 1.5 s. Each row has `lastPrice`, `pChange`, `yearHigh/yearLow`, `perChange30d/365d`, `totalTradedVolume/Value`, `companyName` and `lastUpdateTime`.
- `yf.download` of 500 tickers for 1y of daily bars takes **13.2 s**, and 490 of 500 have more than 200 bars. NIFTY 500 stays the technicals universe.
- Yahoo includes today's partial bar. Every bar dated on or after NSE's trade date is dropped, and the live LTP is appended in its place.

## Slice A: Drawing tools
1. `draw-math.js` (pure): `FIB_LEVELS`, `fibPrices`, `channelOffset`, `anchorsOf` / `withAnchors` (old `trend{a,b}` and `hline{price}` shapes stay unchanged on disk), `moveDrawing(d, dt, dp)`, and `TOOL_CLICKS`.
2. `anchor.js`: add `pointFromXY(x, y)` so drags can convert pixels to `{t, price}`.
3. `draw.js`: a generic N-click placement loop driven by `TOOL_CLICKS`, plus renderers for fib/rect/ray/channel/text.
   - Every drawing gets anchor handles and a wide invisible hit stroke. Mousedown starts a drag, and document mousemove/mouseup handle the rest; the overlay sits above the canvas, so the chart never sees the drag.
   - Double-clicking a text note edits it with `prompt()`.
4. HTML buttons, CSS, tests.

## Slice B: Bar replay
1. `replay-policy.js` (pure): `indexAtTime`, `nextIndex`, `SPEEDS`, `tickMs`.
2. `replay.js`: pick mode (chart click), then `state.replay = { full, idx }` and `state.latestCandles = full.slice(0, idx + 1)`, so every existing renderer (studies, volume, legend, drawings) works on the slice for free.
   - Step = push the next bar, then `syncStyleData` + `renderIndicators`.
3. `data.js` guards:
   - `foldTickIntoChart` returns while replaying.
   - The `preserveView` auto-refresh is skipped while replaying.
   - Any other `loadCandles` call (symbol, interval or range change) ends replay.
   - `loadMoreHistory` is skipped while replaying.
4. Exit puts `full` back and runs `loadCandles({ preserveView: true })` to catch up with live data.

## Slice C: Screener
1. `orazio/technicals.py`:
   - Pure `rsi` (Wilder, the same as `indicators.js`), `sma`, `cross_within`, `metrics(closes, ltp)` and `is_stale(fetched_at, now)` (the cutoff is the latest 15:45 IST).
   - `refresh_async()` runs a background thread with one batched `yf.download`. Closes are cached in `~/.orazio/technicals.json`: JSON is stdlib, about 1.5 MB, and avoids needing pandas to read the file back.
2. `orazio/screener.py`: `screen(universe_key)` takes the rows from `stats._rows`, shapes them, and merges in the technicals. It's cached for 10 s.
3. `GET /api/screener?universe=` in `routes/market.py`.
4. `screener-policy.js` (pure): `PRESETS`, `applyFilters`, `sortRows`.
5. `screener.js`: a right-side `<aside>` with a universe select, preset select, collapsible min/max filters and a sortable table. Clicking a row calls `switchSymbol`. It polls every 10 s while open, and its settings persist in `orazio.screener.v1`.

## Order and checkpoints
A → B → C. After each slice: `npm test` and `python -m pytest` pass, then a manual pass in the browser.

## Risks
- **The toolbar gets crowded** with 5 more buttons. Mitigation: captions are already short, and the toolbar wraps.
- **Replay plus a higher-timeframe MA:** the daily bar containing the cursor includes that day's close, a small lookahead. Accepted and documented.
- **Yahoo rate limiting.** It's one call per day, and if it fails the technical columns show "–" with a retry after 10 min.
