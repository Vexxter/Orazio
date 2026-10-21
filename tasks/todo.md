# Todo

## A. Drawing tools
- [x] A1 draw-math.js + tests/frontend/draw-math.test.mjs
- [x] A2 anchor.js pointFromXY; draw.js generic tools + renderers + drag/edit
- [x] A3 index.html buttons, styles.css. Browser check passed: all tools place, drag (body and anchor), survive reload and the 1m→5m switch, and legacy trend/hline still render.

## B. Bar replay
- [x] B1 replay-policy.js + test
- [x] B2 replay.js + data.js guards + controls. Browser check passed: 10 bars/s gave 10 bars in 1 s, live ticks didn't change the paused chart over 4 s, exit restored all bars, and an interval switch ends replay.

## C. Screener
- [x] C1 orazio/technicals.py + tests (Wilder RSI checked against StockCharts' example)
- [x] C2 orazio/screener.py + /api/screener + tests
- [x] C3 screener-policy.js + test
- [x] C4 screener.js + panel. Browser check passed: NIFTY 500 in 0.7 s; RSI equals the chart's RSI exactly (ICICIBANK, RELIANCE, TCS); "Near 52W high" matched the hand filter (4/4); a row click charts the stock.

## Done
- [x] README features updated, full test run green

## Follow-ups (not in spec)
- [ ] The toolbar wraps to 3–4 rows on a ~1250 px window now. Move the drawing tools into a vertical strip on the chart's left edge, as TradingView does.
- [x] Older than this work: on a symbol switch, a live tick for the new symbol briefly folded into the old symbol's last candle. Fixed: data.js only folds a tick when `state.candlesFor === state.currentSymbol`.
- [x] Toolbar reorganized: drawing strip on the left, panel strip on the right, two-group top bar.
