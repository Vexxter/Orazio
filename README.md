<p align="center"><img src="docs/logo.svg" width="96" alt="Orazio logo"></p>
<h1 align="center">Orazio</h1>
<p align="center"><b>A self-hosted market terminal for Indian and global markets. For quants, by quants.</b></p>

<p align="center">
Stock Lens · plain-English stock screens · fundamentals, earnings and insiders · Closing Auction Session (CAS) terminal · research hub (flows, gamma exposure, rotation, correlation, seasonality, rates, macro) · Bloomberg-style command line · alerts with backtests · drawing tools · bar replay · screener · options · bonds for 37 countries · spot and futures commodities · use it from Claude on your own plan<br>
<b>No login, no API keys, nothing to pay for.</b> Runs on your machine from public exchange data (NSE, BSE, CCIL and more).
</p>

<p align="center">
<a href="#quick-start">Quick start</a> ·
<a href="#charting-and-drawing">Charting</a> ·
<a href="#bar-replay">Replay</a> ·
<a href="#screener">Screener</a> ·
<a href="#options">Options</a> ·
<a href="#insights">Insights</a> ·
<a href="#finding-your-way">Finding your way</a> ·
<a href="#command-line">Commands</a> ·
<a href="#use-it-from-claude-on-your-own-plan">Claude</a> ·
<a href="#closing-auction-session-cas-terminal">CAS</a> ·
<a href="#bonds">Bonds</a> ·
<a href="#commodities-spot-and-futures">Commodities</a> ·
<a href="#where-the-data-comes-from">Data sources</a> ·
<a href="#limits-measured">Limits</a>
</p>

<p align="center"><a href="docs/demo.mp4"><img src="docs/demo.webp" width="100%" alt="The Orazio tour: the Stock Lens and results edge, one box for everything, plain-English screens, What changed, Insights grouped by job, the cheat sheet, volume profile, events on the chart, drawing, bar replay, grid, formulas, fundamentals and peers, earnings, insiders, the calendar, dealer gamma and IV rank, the option chain and payoffs, the brief, flows, rotation, correlation, yield curves, the rate path, bonds, movers, portfolio Monte Carlo, the sizer, alert backtests, Excel links and provenance"></a></p>
<p align="center"><b><a href="docs/demo.mp4">▶ Watch the full tour (7:22, MP4): every feature, in seven chapters</a></b> · the preview above is its first 80 seconds at 2×</p>
<p align="center">Direct link to the 7½-minute review: <a href="https://github.com/prathamkul007-max/trading-view-self-host/raw/main/docs/demo.mp4">docs/demo.mp4</a></p>

![NIFTY on 5-minute bars with EMA 20, SMA 50, VWAP, RSI, a Fibonacci retracement and a measured trendline](docs/screenshots/chart.png)

> **Educational and informational project.** Orazio is not a replacement for licensed exchange data or professional trading tools, and nothing it shows is financial advice. Data can be delayed, wrong or missing. Use it at your own risk.

## Why it's built for quants

- **Every latency is measured, not claimed.** Each number in the [data table](#where-the-data-comes-from) was timed against the exchange. Where a free source is late (CME futures on every free site run 10 minutes behind), the README says so.
- **Sources are chosen by accuracy.** The futures feed, for example, was picked by lining each candidate up against real CME/ICE trades at the same moment and keeping the one that tracks the contract most closely ([results](#commodities-spot-and-futures)).
- **Everything is inspectable.** It's plain Python and ES modules with no build step. About 1,400 tests run offline in seconds, and [tests/README.md](tests/README.md) maps every feature to the test that proves it.
- **Every number names its source.** Each data response carries a `provenance` object (source, link, delay, units, as-of time), and `:SRC` shows every feed's last result.
- **Your data stays local.** It runs on `localhost`: no account, no telemetry. Download any series as CSV or Parquet. The one exception is the optional MCP server, if you connect it: what your Claude app reads through it goes to Anthropic under your plan.

## Quick start

```bash
pip install -r requirements.txt
python app.py          # open http://localhost:5000
```

## Charting and drawing

- **Live charts:**
  - Candles, bars, line or area; 1-minute to weekly bars.
  - Volume, and drag left for older history. Light and dark themes.
  - Prices are pushed to the page (server-sent events), not polled.
- **Indicators:**
  - Three moving averages (SMA or EMA, any length). Each can run on another timeframe, e.g. the 200-day SMA on a 5-minute chart.
  - VWAP, Bollinger Bands, RSI and MACD.
  - Volume profile over the bars on screen: volume by price split into buying and selling, the point of control, and the 70% value area. It redraws as you scroll.
- **Drawing tools** (the labelled strip left of the chart):
  - Trendline, horizontal line, ray, box, Fibonacci retracement, parallel channel, text note and a measure tool.
  - Every drawing is anchored to price and time, so it survives pan, zoom, interval changes and reloads.
  - Drag a point to reshape a drawing, drag a line to move it, and double-click a note to edit it.
- **Compare:** a second chart beside the first, synced by time (scroll, zoom, crosshair), with both symbols' % change over the window on screen.
  - Its own style: candles, bars, Heikin Ashi, line, area or baseline.
  - **Formula series:** type `NIFTY / BANKNIFTY`, `IN10Y-IN - US10Y` (spaces around the minus) or `GOLD * INR=X`.
- **Events on the chart** (the Events toggle): results days, dividends, splits, bonuses, bulk and block deals for NSE stocks; RBI rate decisions and big FII days for Indian indices. Hover a marker to read it. Your journal trades always show as Buy/Sell markers.
- **Multi-chart grid** (Grid, right edge): 2–4 charts side by side, each with its own bar size. Leave a pane's symbol empty and it follows the main chart (one symbol on several timeframes); crosshairs are synced.

![RELIANCE on four linked timeframes in the grid](docs/screenshots/grid.png)

![NIFTY and BANKNIFTY compared on 1-minute bars](docs/screenshots/compare.png)

## Bar replay

Click **Replay → Start**, then click a bar, and everything after it disappears. Step one bar at a time (→) or play (Space) at 1, 3 or 10 bars a second. Indicators and drawings follow the replayed bars, and live prices stay off the chart until you press Stop.

![Bar replay on NIFTY at 10 bars a second](docs/screenshots/replay.webp)

## Screener

- **Universes:** NIFTY 50, NIFTY BANK, NIFTY 500 or NIFTY Total Market (~750), from NSE's own market watch.
- **Columns:**
  - Live price, % change, traded value, distance from the 52-week high and low, 30-day and 1-year change.
  - RSI(14), distance from the 50- and 200-day SMAs, and golden or death crosses in the last 5 sessions.
- **Presets** (near 52W high, RSI < 30, above 200-day SMA, …) or your own min/max filters. Sort any column, and click a row to chart it.
- **Formula filters:** `rsi < 30 and vsSma200 > 0`, `valueCr / ltp > 2`, `ch30 > 10 or cross = golden`.
- RSI and SMAs come from one daily Yahoo download (~15 s for 500 stocks), then update intraday with the live price. RSI matched the chart's own RSI exactly in testing.

![The NIFTY 500 filtered to stocks above their 200-day SMA](docs/screenshots/screener.png)

## Options

- NSE futures table and option chain for NIFTY, BANKNIFTY and ~213 F&O stocks.
- OI, change in OI (heatmap), IV, volume, PCR, max pain and ATM straddle; an IV smile chart.
- A **payoff-at-expiry builder:** click any LTP to add a leg. It shows max profit and loss, breakevens, live P&L and real lot sizes.
- Yahoo option chains for US stocks. You can also chart the front-month future instead of spot.

![NIFTY option chain with OI-change heatmap, PCR, max pain and ATM straddle](docs/screenshots/options.png)

## Insights

One window (**Insights**, right edge) with a tab per research view. Click any row or tile to chart it.

- **Brief:** 14 cross-asset tiles (Indian indices, GIFT Nifty, India VIX, USD/INR, India and US 10Y, dollar index, Brent, gold, US indices, Bitcoin), the gap GIFT Nifty implies for the open, FII/DII cash, system liquidity, today's high-impact releases and the top headlines.
- **Market structure:**
  - **Flows:** FII/DII cash net, and participant-wise derivatives OI (FII, DII, Pro, Client) for 30 sessions: net index futures, FII long %, net index calls and puts.
  - **Breadth:** advance/decline, % above the 50/200-day SMA, stocks near 52-week highs and lows, RSI extremes, fresh golden/death crosses, and the spread of today's moves.
  - **Delivery & deals:** stocks whose delivered quantity jumped against their own 20-session average, and the latest bulk and block deals.
  - **Rollover:** futures rollover % and roll spread per underlying, against the previous series at the same number of sessions before expiry.
- **Options analytics:** dealer gamma exposure (GEX) by strike, the zero-gamma flip level, call and put walls, max pain, PCR, the IV smile, the ATM IV term structure across six expiries, and today's OI change by strike. Any NSE F&O underlying.
  **Cheap or dear:** IV30 with its IV rank and percentile (Orazio records IV history locally, since NSE publishes none), realised HV20, IV minus HV, and India VIX's 1-year rank for NIFTY.
- **Insider (`:INS`):** open-market buys and sells by promoters, directors and key managers (SEBI PIT filings), netted per company. ESOPs, gifts and pledges are left out. The same trades show as chart markers under **Events**.
- **Company (`:FA`):** what the business does, market cap, P/E, P/B, EV/EBITDA, ROE, margin, growth, five quarters and four years of results, balance sheet, cash flow, and a peer table (same NSE industry, nearest in size) with the peer median. Profile, ratios, quarters and peers come from NSE's own MarketLens; Yahoo fills what it lacks (annual statements, balance sheet and cash-flow history, EV/EBITDA) and anything MarketLens leaves blank or hasn't updated yet.
- **Earnings (`:ERN`):** the results calendar for your watchlist or all of NSE, and how the charted stock moved around each past result: typical two-session move, how often it rose, five-day drift.
- **Calendar (`:IPO`):** IPOs open and upcoming, recent listings against their issue price, and every dividend, split, bonus and buyback ex-date in the next 30 days.
- **Rate path (`:WIRP`):** basis points of RBI and Fed moves priced over 1, 3, 6 and 12 months, read from the bill curve (CCIL T-bills against TREPS; US bills against the fed funds target).
- **Excel (`:XL`):** `=WEBSERVICE("http://127.0.0.1:5000/xl/quote?s=TCS.NS&f=price")` puts a live price in a cell. CSV links for history, tables and ratios work with Data › From Web.
- **Quant research:**
  - **Rotation:** a relative rotation graph of 13 NSE sectors against NIFTY 50 (weekly).
  - **Correlation:** correlation or beta of daily returns across an editable cross-asset basket, over 3M to 3Y. Yields use level changes. Click a cell to compare the pair.
  - **Seasonality:** average and median return by month and weekday, with the share of positive periods, over the full history (NIFTY: since 2007).
  - **Event study:** what a symbol did 1–20 sessions after RBI hikes or cuts, big up/down days, opening gaps, or your own dates. Average path, hit rate and every event.
- **Filings and ownership:**
  - **Filings:** NSE corporate announcements from the last 3 days for your watchlist or the whole market, with each PDF. Save phrases like `order win` to be notified when one appears.
  - **Holdings:** promoter, public and employee-trust share by quarter, back to 2021 where filed.
- **Option backtest:** a strategy (straddle, condor, your own legs) entered before each expiry and held to it, net of STT, charges and slippage, on NSE's end-of-day files. Every rate is editable.
- **Rates and macro:**
  - **Rates:** a yield curve you can scrub back five years (16 countries) against today's; US 10Y−2Y, 10Y−3M, India−US 10Y and Bund spreads; Indian corporate bond spreads over G-secs by rating.
  - **Macro:** the week's economic calendar in IST, and RBI's daily liquidity: net injection or absorption, call/TREPS/repo rates, SDF and MSF use.
- **Your tools:**
  - **Alerts:** price, day-change, RSI and moving-average alerts, checked every 20 s by the server, so they fire with the page closed. They go to your desktop, Telegram, a webhook or email. **Backtest any rule first:** how often it fired over the full history and what followed 1–20 sessions later.
  - **Portfolio:** import a holdings CSV for value, P&L, weights, concentration, beta to NIFTY, volatility, drawdown and VaR, plus a 2,000-path Monte Carlo of the next 12 months: likely range, typical and 1-in-20 drawdown, chance of a loss. It stays in your browser.
  - **Risk (`:SIZE`):** position sizer. Capital, risk % and stop give the quantity, rounded down to F&O lots, with 1R/2R/3R targets.
  - **Settings:** notification channels and a weekday morning brief.
  - **Watchlist:** live price and change, 52-week distance, RSI, distance from the 50/200-day SMA, volume against its 20-day average, and NSE delivery %.
  - **Journal:** log trades; see FIFO-matched P&L, win rate, profit factor, P&L by setup, the equity curve and open positions marked to market. Export to CSV.
  - **Workspaces:** save a layout (symbol, style, studies, compare, grid, panels) under a name, or start from a preset: Expiry day, Bond desk, Pre-open.

| Brief | Options analytics | Sector rotation |
|---|---|---|
| ![The Brief: cross-asset tiles, GIFT Nifty gap, flows, liquidity, releases and headlines](docs/screenshots/insights-brief.png) | ![NIFTY gamma exposure by strike, flip level and walls](docs/screenshots/insights-options.png) | ![Relative rotation graph of NSE sectors against NIFTY 50](docs/screenshots/insights-rotation.png) |

## Finding your way

Orazio answers before you ask, and teaches its shortcuts as you go.

- **The Lens** (top of the right-hand column): for whatever is charted, the few facts that matter now, one line each with a verdict. Results coming, and whether options price more or less than the stock usually moves on results (the *results edge*); promoter/director money; P/E and ROE against NSE's own peer list; IV rank; trend. For NIFTY: dealer-gamma regime, India VIX rank, FII cash, put/call. Click a line for the evidence.
- **One box for everything**: the search box takes a ticker, a view on it (`tcs peers`, `nifty gex`, `reliance results`), a comparison (`tcs vs infy`) or a question (`debt free companies with ROCE above 20`). Each suggestion shows the command it runs.
- **What changed** (`:NEW`, the first Insights view): one ranked inbox of surprises across your watchlist: moves that are big *for that stock* (in σ of its own last 60 days), volume spikes, 52-week breaks, results this week, insider money, ex-dates. The Insights button shows how many are notable.
- **Find** (`:FIND`): screen ~1,100 NSE stocks in plain English. NSE MarketLens reads the question ("'Debt free' read as Long Term Borrowings = 0") and Orazio runs it, with looser/stricter versions one click away, plus NSE's 70+ ready-made screens. If a word stumps the parser, it can optionally ask a model you set up in Settings: the Claude or Codex CLI on your own plan, or a local/OpenAI-compatible server (Ollama, LM Studio, llama.cpp, OpenRouter). The model can only pick from Orazio's own fields and operators; every clause is checked before it runs.
- **Insights grouped by job**: Today, Find, Stock, Derivatives, Rates & macro, My book, More. Every tab shows its command.
- **Learn by doing**: a 60-second tour on first run (`:TOUR`), `?` for the whole product on one page, and a one-time "next time, type `:FA`" hint the first time you open a view by mouse.

## Command line

Type a command in the symbol search and press Enter, Bloomberg-style. Press `:` anywhere to start one.

| Type | Does |
|---|---|
| `NIFTY OPT` · `RELIANCE SEAS` · `BANKNIFTY ROLL` | Charts the symbol and opens that view |
| `BANKNIFTY 5M` · `NIFTY 1W` | Charts it at that bar size |
| `NIFTY CMP SPX` · `CMP IN10Y-IN - US10Y` | Opens Compare with a symbol or a formula |
| `:FLOW` · `:BRIEF` · `:ECO` · `:WS` | A view on its own (single words need the colon) |
| `:HELP` | Lists every function and its aliases |

Links work too: `http://localhost:5000/?cmd=NIFTY%20OPT` opens that view.

## Use it from Claude, on your own plan

Ask Claude Code or Claude Desktop about live data and filings. There's no API key to buy or store: the app you're signed in to calls Orazio, and Orazio never sees your login.

1. Start Orazio: `python app.py`
2. Add it once. In Claude Code:
   ```bash
   claude mcp add --transport stdio orazio -- python /path/to/scripts/orazio_mcp.py
   ```
   In Claude Desktop, add this to `claude_desktop_config.json`:
   ```json
   {"mcpServers": {"orazio": {"command": "python", "args": ["/path/to/scripts/orazio_mcp.py"]}}}
   ```
3. Ask: "Summarise TCS's latest filing, with page numbers." or "How has a NIFTY short straddle done over 3 months?"

It's read-only with 16 tools, and every answer carries its provenance. Your journal, alerts and settings aren't exposed, and no tool can place an order. What Claude reads goes to Anthropic under your plan and counts toward its limits. Scanned PDFs have no text to read.

## Closing Auction Session (CAS) terminal

- **Overview:** a countdown, live NIFTY / BANKNIFTY / NIFTY IT / SENSEX movement, and a stock-by-stock auction feed with order books.
- **Real-time auction estimate** for NIFTY, BANKNIFTY and NIFTY IT, rebuilt every 2 s from their stocks:
  - It starts from NSE's own auction price for each stock. Between NSE's prints it's carried forward by BSE's live auction on the same stocks: the 30 SENSEX stocks over BSE's socket (~0.7 s), the rest from BSE's market watch.
  - Each index is rebuilt with NSE's own free-float weights, refined daily against a week of 1-minute data. On a day the fit hadn't seen it was off by ~1 pt for NIFTY, ~3 for NIFTY IT and ~18 for BANKNIFTY.
- **Futures-implied close** for NIFTY and BANKNIFTY:
  - Index futures trade until 15:40, through the auction, so the front-month future minus its 15:14:59 basis estimates where the close is heading.
  - It's available from 15:15, before NSE's own index indicative appears (~15:20).

![Auction feed: every F&O stock's indicative price, quantity and buy/sell interest](docs/screenshots/auction-feed.png)
<sub>The same feed outside the closing auction, showing that morning's pre-open session (21 Oct 2026, 09:08).</sub>

## Bonds

**Global:**
- Government bond yields for **37 countries**, every maturity CNBC carries: 161 in all, including the full US, German, Japanese and Italian curves.
- Real time, grouped by region. Open a country to see its whole curve, and click any maturity to chart it.

**India:**
- **Live from CCIL's NDS-OM** (the RBI's own G-sec trading platform): ~80 central government G-secs, ~150 state development loans, ~40 T-bills and when-issued. Each row shows last traded yield and price, best bid and offer, and traded volume.
- **~570 NSE-listed corporate bonds** with rating, coupon, maturity, price and an approximate yield to maturity.

**Charts:**
- Yields chart with the full toolset (drawings, indicators, replay), at 3 decimals, with changes in basis points.
- Intraday bars from CNBC: 1-minute for about a week, 5- and 15-minute for about 40 days, hourly for about 3 months. Daily and weekly bars go back decades.
- India's 10Y has daily history from 2015 (worldgovernmentbonds.com).
- CCIL only shows today, so Orazio records every G-sec trade while it runs. Each security's chart starts on the day Orazio first saw it trade.

| Global yields, US curve open | India: CCIL G-secs and the 10Y since 2022 |
|---|---|
| ![Global yields with the US curve expanded and the US 10Y over 5 years](docs/screenshots/bonds-global.png) | ![CCIL G-secs with bids and offers, and India's 10Y yield](docs/screenshots/bonds-india.png) |

## Commodities: spot and futures

WTI, Brent, natural gas, copper, gold and silver, live. A switch beside the price picks **Spot** (the default) or **Futures**.

| | Spot | Futures |
|---|---|---|
| WTI, Brent | Dukascopy: matches TradingView's USOIL/UKOIL to a cent or two | Hyperliquid oracle |
| Natural gas, copper | Dukascopy front-month price | Hyperliquid oracle |
| Gold, silver | Swissquote live, Dukascopy history (agree to cents) | Binance |

Free real-time CME/ICE data doesn't exist, so futures come from perpetual contracts. The futures sources were picked by lining each candidate up against **real exchange trades at the same moment** (21 Oct 2026, 26–42 trades each):

| | Binance | Hyperliquid oracle | Contract tracked |
|---|---|---|---|
| WTI | +5.2¢ | **+0.4¢** | Dec |
| Brent | +4.4¢ | **−0.6¢** | Jan |
| Natural gas | +0.5¢ | **0.0¢** | Dec |
| Gold | **−$10.5** vs COMEX | −$18.1 (tracks spot) | — |

Type `CRUDE`, `WTI` or `USOIL` for WTI, and `BRENT` or `UKOIL` for Brent. Futures charts beyond a year use CME history via Yahoo.

![Brent switching from spot (110.4) to futures (106.6) and back](docs/screenshots/spot-futures.webp)

## Also included

- **SENSEX in real time** from BSE's own push stream. **GIFT Nifty**, with history back to 2023.
- **Market breadth and Top Movers** for Indian, US and Asian indices, in the left rail.
- **News panel** for the symbol on the chart. Company names, 52-week stats and live index volume in the legend.
- **Download** any series as CSV or Parquet, or schedule an end-of-day export.
- **Layout:**
  - The instrument and chart controls sit in the top bar.
  - Drawing tools and replay are in a labelled strip left of the chart.
  - The panels (News, Screener, Bonds, Options, Movers, Compare, Grid, Insights) are on the right edge.
  - Narrow screens stack everything.

## Where the data comes from

| Market | Source | Latency |
|---|---|---|
| NIFTY, BANKNIFTY, NIFTY IT | Yahoo tick, NSE for the official close | 1–5 s |
| SENSEX | BSE push stream | ~1 s |
| Commodities, spot | WTI, Brent, gas, copper: Dukascopy · gold, silver: Swissquote live + Dukascopy history | 3–8 s |
| Commodities, futures | Hyperliquid oracle (oil, gas, copper) · Binance websocket (gold, silver) · Yahoo CME for long history | ≤1 s |
| NSE futures, options, GIFT Nifty | NSE / NSE IX public endpoints | ~1 min |
| US, Korea, Taiwan, China indices | Yahoo / Sina / Naver / TWSE | seconds |
| Government yields, 37 countries | CNBC quote service | real time (measured 15–40 s since the last tick while each market trades) |
| Indian G-secs, SDLs, T-bills | CCIL NDS-OM market watch | each trade, on the next 5 s poll (CCIL's server sometimes takes ~10 s) |
| Indian corporate bonds | NSE listed-bonds feed | ~15 s |
| NSE auction (CAS) | NSE public feed | ~54 s (measured) |
| NIFTY / BANKNIFTY / NIFTY IT CAS, rebuilt | NSE's indicative print + a rebuild from each stock's auction price (NSE, then BSE) between prints | ~2 s (NSE prints ~15 s) |
| NIFTY / BANKNIFTY CAS, futures-implied | NSE front-month futures (basis held at 15:14:59) | ~54 s (measured 14 Oct 2026) |
| FII/DII cash, participant-wise OI | NSE `fiidiiTradeReact` · NSE `fao_participant_oi` archive | daily, ~6 pm IST |
| Delivery %, bulk and block deals | NSE `sec_bhavdata_full` archive · NSE large-deal API | daily, after the close |
| Rollover | NSE F&O bhavcopy (the futures history cache) | daily |
| Options analytics | NSE option chain (GEX computed here: Black-Scholes, r = 0) | polled every 30 s |
| RBI liquidity | RBI's daily "Money Market Operations" release | next morning |
| Economic calendar | ForexFactory weekly feed | hourly |
| Corporate filings | NSE corporate announcements | polled every 5 min |
| Shareholding | NSE shareholding pattern | quarterly, after each filing |
| Option backtest | NSE F&O bhavcopy, from July 2024 | daily, after the close |
| Fundamentals, peers, plain-English screens | NSE MarketLens · Yahoo statements (fallback and annual history) · NSE NIFTY 500 industry list | MarketLens 30 min, Yahoo 6 h |
| Insider trades | NSE `corporates-pit` (SEBI PIT disclosures) | cached 30 min |
| Earnings calendar | NSE event calendar (board meetings for results) | cached 30 min |
| IPOs, corporate actions | NSE IPO and `corporates-corporateActions` APIs | cached 15 min |
| Rate path | CCIL T-bills + TREPS (RBI) · US T-bills (CNBC) + fed funds target (FRED) | live bills, daily anchors |
| IV rank | Recorded locally from the option chain (IV30) | every 30 min in market hours |

## Limits, measured

- **Public endpoints:** Orazio uses the same public endpoints the exchanges' own websites call, not supported APIs. Any of them can change or block access; the app falls back instead of erroring.
- **CAS estimate (measured on the 14 Oct 2026 auction):**
  - NSE's indicative index updated about every 15 s.
  - The raw rebuild finished +10.5 pts from NIFTY's official close, −8.6 for NIFTY IT and +56 for BANKNIFTY (mostly a constant offset from its starting level). So the estimate snaps to each NSE print and lands on NSE's own number.
  - Between prints it was no better than NSE's last print: BSE's auction doesn't lead NSE's. Treat the live line as NSE's latest value plus noise-level drift, not a forecast.
- **NSE futures** update about once a minute (quote API median 54 s; tick chart 108 s and ~30 s behind).
  - The rebuild tracks NSE's close closely rather than exactly, because BSE's auction is a separate order book. It says what share of the index has an auction price so far.
  - The futures-implied close can drift with the basis, and NIFTY IT has no index future.
- **Commodity futures are perpetuals** (see the table above). They roll on their own schedule; on 21 Oct 2026 they tracked WTI Dec, Brent Jan, gas Dec and copper Dec.
- **"Spot"** for oil, gas and copper is the front-month price trading screens show (TradingView's USOIL/UKOIL), not the physical benchmark. The official EIA Cushing spot is published about a week late.
- **Bonds:** charts of single Indian G-secs only cover days Orazio was running. Corporate-bond yields are approximate (annual coupons, simple accrued interest, call dates ignored).
- **Insights history:** NSE publishes only the latest day's FII/DII cash figures and RBI lists only its last ~8 liquidity releases, so those charts build up day by day from the first day Orazio ran. Participant OI, delivery and rollover come from archives and have history at once.
- **Gamma exposure** assumes dealers are long the calls and short the puts the public holds (the common convention). It's a positioning estimate, not a measured dealer book.
- **Economic calendar:** the free feed covers the major currencies only (no INR events) and has forecasts but no actual figures. It rate-limits, so the last good copy is kept on disk.
- **RBI decisions** built in for the event study and chart markers run from 2019 to June 2025; add newer ones as custom dates.
- **Alerts** run while Orazio runs, so they stop if the app or the machine does. Start it at login to keep them on.
- **Option backtest:**
  - End-of-day closes only, held to expiry: no intraday entries or stops. An expiry is skipped when a leg didn't trade on entry day.
  - Settlement is intrinsic value against the underlying's close, and today's charge rates apply to every date.
  - History starts in July 2024, when NSE's current file format does.
- **Filings** cover NSE only, for the last 3 days, and BSE-only companies are missing. **Holdings** have no pledge data, which sits in XBRL filings that Orazio doesn't parse yet.
- **Fundamentals** are reported figures only: no analyst estimates. MarketLens is an unofficial NSE API and can change without notice; Yahoo fills in when it fails.
- **Insider** filings come from NSE's PIT feed, which can lag by weeks; the view widens its window when recent days are empty.
- **IV rank** builds from the first day Orazio runs (NSE publishes no IV history); NIFTY uses India VIX's year meanwhile.
- **Deep search's model fallback** is off by default. The Claude and Codex CLIs use your existing login; a hosted OpenAI-compatible server may need its own key.
- **MCX:** Indian commodities aren't available, because MCX blocks scripted access and NSE has no commodity feed.
- **Flask dev server:** don't expose it to the internet.

## Tests

```bash
python -m pytest        # ~1,130 backend tests, a few seconds, no network
npm test                # ~280 frontend tests (logic, plus a parse check of every module), Node's built-in runner
python scripts/smoke.py # live-feed check against a running server
```

[tests/README.md](tests/README.md) maps each feature to its tests.

## How it works

One local Flask process serves the page, answers `/api/*` and polls the exchanges in background threads. The frontend is plain ES modules with no build step.

```
orazio/            backend: one module per concern (market_data, cas, fno, quotes, spot, futures, bonds, gsec, screener, flows, options_analytics, delivery, rollover, macro, fundamentals, marketlens, filings, insider, earnings, alerts, deep, ...)
orazio/routes/     HTTP routes, one file per feature area
static/js/         frontend modules; *-policy.js, *-math.js and format.js are pure and unit-tested; insights-*.js are the Insights tabs
scripts/orazio_mcp.py  the read-only MCP server for Claude Code / Claude Desktop
tests/  scripts/   pytest + node tests, live smoke script
docs/screenshots/  the images in this README
```
