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

## D. Insights hub (one modal with tabs; each tab its own module)
- [x] D0 Compare chart styles (candle/bar/HA/line/area/baseline)
- [x] D1 Hub shell: insights.js tab registry + modal + app-strip button
- [x] D2 Flows: FII/DII cash (history persisted daily) + participant-wise OI (NSE archives)
- [x] D3 Options analytics: GEX by strike, IV smile + term structure, OI change by strike
- [x] D4 Breadth: % above 50/200 DMA, near 52W high/low (from screener rows)
- [x] D5 Delivery % + bulk/block deals
- [x] D6 Rollover (expiry week) from F&O bhavcopy cache
- [x] D7 Sector rotation (RRG) from sector index dailies
- [x] D8 Correlation/beta matrix
- [x] D9 Seasonality (month, weekday)
- [x] D10 Event study (forward returns after events / custom dates)
- [x] D11 Formula series (A/B, A-B) on compare chart
- [x] D12 Yield curve history scrubber + spread monitor
- [x] D13 Macro calendar + liquidity
- [x] D14 Command line (`:` key)
- [x] D15 Event layer on chart (corporate actions, FII/DII, deals)
- [x] D16 Alerts (price/RSI/% move) + backtest of the alert
- [x] D17 Brief: cross-asset tiles + pre-open gap + top news
- [x] D18 Watchlist with live columns
- [x] D19 Multi-chart grid (linked symbol/interval)
- [x] D20 Saved workspaces
- [x] D21 Trade journal + chart markers
