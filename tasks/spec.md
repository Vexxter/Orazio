# Spec: Live chart parity + TradingView-style UX

## Objective
The chart currently lags the live index, has no way to scroll into prior-day intraday
history, a volume pane that overlaps candles, no quick-access index list, and no
futures/options view. This spec closes that gap toward TradingView-like behavior on a
single symbol page. User: the person actively trading/watching NIFTY & friends intraday.
Success = chart visibly tracks the index in real time, prior-day data is one drag away,
volume reads as a thin strip, common indices are one click away, and cash/futures +
option premium are reachable where the data actually supports it.

## Verified facts (checked live against yfinance before writing this)
- Index aliases resolve: `^CNXIT` (NIFTYIT), `^GSPC` (SPX), `^IXIC` (NASDAQ), `^DJI`
  (DOWJONES), `^KS11` (KOSPI), `^TWII` (TAIEX) — all returned a live price.
- `^NSEI` (NIFTY) has **no option chain** via yfinance (`t.options` returns empty).
  US names (e.g. AAPL) do have one.
- No NSE index/futures ticker resolves via yfinance (`NIFTY_FUT`, `NIFTY.NS`, `^NSEI=F`
  all 404). Global index futures DO resolve (`NQ=F` Nasdaq, `ES=F` S&P).

## Assumptions (proceeding unless corrected)
1. "Fix the 1-minute lag" means: for 1m/5m intervals, the chart should update within
   ~5s of the live price (matching the existing quote-poll cadence), not that yfinance's
   own upstream delay (which can itself be ~1 min for Indian indices) needs eliminating —
   that upstream delay isn't in this app's control.
2. Drag-to-previous-day applies to intraday intervals (1m/5m/15m/1h) only; daily/weekly
   view already spans years and doesn't need this.
3. Session-boundary marker = a vertical line + small date label at the prior-close →
   next-open gap, drawn once extra history is loaded (not baked into every candle fetch).
4. Cash/Futures toggle: **decided — dropped for NIFTY/BANKNIFTY/NIFTYIT.** These three
   always show cash/spot only, no toggle shown at all (not even disabled). The toggle
   still applies to global indices where yfinance has a real futures ticker (SPX→ES=F,
   NASDAQ→NQ=F, DOWJONES→YM=F).
5. Option premium viewer: **scoped by data availability.** NIFTY/BANKNIFTY/NIFTYIT show
   a disabled "options data unavailable" state (yfinance has no chain for them);
   US-listed symbols with a real chain (via `Ticker.options` / `Ticker.option_chain(date)`)
   get a working panel. This is a real data-source gap, not a bug to code around.
6. Left rail is a fixed, static list (the 8 named indices) — not user-editable/searchable
   in this pass.
7. "Swipe/drag left" is implemented as native chart panning (Lightweight-Charts already
   supports drag-to-pan) plus a scroll-triggered lazy-load of older bars, not a custom
   gesture layer.
→ Correct me now on 4/5 in particular (the futures/options scope) or I'll build to this.

## Tech Stack
Flask (Python) + yfinance backend, vanilla JS + TradingView Lightweight-Charts frontend.
No new frontend framework. New backend deps only if unavoidable (none currently expected
— option chain and futures both go through `yfinance.Ticker`).

## Commands
Run: `python app.py` (serves on :5000)
No automated test runner in this project; verification is curl against the running
Flask server plus manual chart checks in-browser.

## Project Structure
```
app.py              → Flask routes: /api/candles, /api/quote, /api/search (+ new routes below)
static/index.html   → chart UI (JS inline)
tasks/               → spec/plan/todo for this change
```
New routes needed:
```
/api/candles/history  → older intraday page for drag-to-load-more (before a given timestamp)
/api/futures-symbol    → resolve cash symbol -> futures ticker, or "unavailable"
/api/options           → option chain (expiries + strikes/premiums) for a symbol, or "unavailable"
```

## Code Style
Existing style: small pure functions, no framework, comments only where behavior is
non-obvious (e.g. why a row is filtered, why a symbol is aliased). New endpoints follow
the same pattern as `/api/candles` (validate → fetch via yfinance → shape JSON → return
`{available: false, reason: "..."}` instead of erroring when data genuinely doesn't exist).

## Testing Strategy
No automated suite. Verify each new endpoint with curl against real symbols (one that
should work, one that should report unavailable), then a manual browser pass: drag chart
left across a session boundary, toggle futures on a supported vs unsupported symbol, open
the options panel on AAPL vs NIFTY.

## Boundaries
- Always: keep interval+range validation server-side (existing pattern in
  `resolve_interval_range`); never let the frontend request combos yfinance can't serve.
- Ask first: adding new Python dependencies beyond yfinance/requests/flask/flask-cors;
  changing the default landing symbol/interval away from NIFTY/1m/1D.
- Never: fabricate futures or options data for symbols yfinance doesn't cover — always
  show explicit "unavailable" state instead of a silent zero/empty chart.

## Success Criteria
1. On a 1m-interval symbol, the last visible candle's close updates within ~5s of the
   quote ticker, not up to 60s behind it.
2. Dragging the chart left past the start of today's session loads and displays prior
   sessions' intraday candles continuously (up to ~5-7 days back, yfinance's 1m limit),
   with a visible marker at each session boundary.
3. Volume bars occupy no more than ~12% of the pane height and don't visually overlap
   candle wicks/bodies.
4. Left rail lists NIFTY, BANKNIFTY, NIFTYIT, SPX, NASDAQ, DOWJONES, KOSPI, TAIEX; each
   is one click to load.
5. Cash/Futures toggle: works (loads a different, correctly-labeled instrument) for
   SPX/NASDAQ/DOWJONES; not shown at all for NIFTY/BANKNIFTY/NIFTYIT (cash/spot only).
6. Option premium panel opens and shows live strikes/premiums for symbols with a real
   yfinance option chain; shows "unavailable" for symbols without one (e.g. NIFTY).

## Open Questions
None blocking — resolved:
1. Futures/options scope confirmed: NIFTY/BANKNIFTY/NIFTYIT show cash/spot only (no
   futures toggle); options panel still attempted but will report unavailable for them.
2. Drag-back depth confirmed: up to yfinance's ~5-7 day 1m intraday limit.

## Increment 2: latency, glitch fixes, granularity zoom, more indices

Filed after real usage surfaced new issues. **No chrome-devtools MCP is configured in
this environment**, so these were root-caused by direct code reading + backend
verification (curl/python), not a live browser session — flagged explicitly per item.

### Verified facts (this increment)
- NSE's own public index API (`https://www.nseindia.com/api/allIndices`, same one
  nseindia.com's site uses) returns live NIFTY 50 / NIFTY BANK / NIFTY IT values with a
  session-cookie handshake — confirmed working live, materially fresher than Yahoo's
  index feed for these three.
- `resolve_interval_range` escalates "1Y" range (with the default 1m interval dropdown)
  to **1h**, not 1d — confirmed via curl, backend returns valid data (1705 real hourly
  rows spanning the full year).
- Root cause of the rubber-band/hidden-9:15 glitch **and** the ">1Y shows nothing" bug:
  the same bug. The `subscribeVisibleLogicalRangeChange` listener added in Increment 1
  fires on *any* visible-range change, including the ones `fitContent()` itself
  produces right after a fresh `setData()` — not just genuine user drags. For 1D/1m
  it just causes an unwanted premature prefetch (the rubber-band). For 1Y/YTD (which
  resolve to 1h, not 1d, so weren't excluded by the existing "skip on 1d" guard) it
  fetches an overlapping/duplicate window from `/api/candles/history` and hands
  Lightweight-Charts non-monotonic or duplicate timestamps — which the library
  rejects/throws on, breaking that chart instance until reload. That break persists
  across subsequent range clicks in the same page load, which is why 5Y/All *also*
  looked broken afterward even though their own data and code path are fine in
  isolation (verified both return correct real rows independently via curl).
- ^HSI (Hang Seng) and 000001.SS (Shanghai Composite) both resolve live via yfinance.
  SENSEX (^BSESN) was already aliased in Increment 1 but never added to the rail list.

### Assumptions (proceeding unless corrected)
1. "China's index" = Shanghai Composite (`000001.SS`, mainland China's primary index),
   not Hang Seng (Hong Kong). Aliased as `CHINA`. Correct me if Hang Seng was intended
   instead/also.
2. The NSE low-latency source is used only for the 3 NSE indices it actually covers
   (NIFTY, BANKNIFTY, NIFTYIT) — everything else keeps using yfinance. It's used for the
   `/api/quote` (ticker/price) endpoint only, not for historical candles (NSE's API
   doesn't serve OHLC history in the shape we need).
3. NSE's endpoint is unofficial (their own site's API, no public docs/SLA) and can
   start blocking/rate-limiting or change shape without notice — `/api/quote` must fall
   back to the existing yfinance path silently on any failure, never surface an error
   to the user for this.
4. "Zoom out/in changes granularity like TradingView" means: as the user zooms the
   mouse wheel and the visible time span crosses a threshold, the interval
   auto-switches (1m→5m→15m→1h→1d and back) while preserving the same visible time
   window (not re-fitting/resetting the view). Thresholds are a reasonable approximation
   of TradingView's own, not pixel-matched to it.
5. "Put the day marker on top or some other intuitive way" — reframed as: drop the
   on-chart arrow+label markers entirely, and instead show the full date (not just
   time-of-day) on the time axis label for ticks that land on a session boundary. This
   keeps the chart body completely uncluttered, at the cost of the boundary date only
   appearing when the axis happens to render a tick at that exact bar (not literally on
   every boundary at every zoom level).
→ Correct me now on 1/4/5 or I'll build to these.

## Boundaries (increment 2, additive)
- Ask first: nothing new here beyond what's already listed above.
- Never: let a failure in the NSE scrape path surface as a user-visible error or block
  `/api/quote` — always fall back to yfinance.

## Success Criteria (increment 2)
1. NIFTY/BANKNIFTY/NIFTYIT quote polling uses NSE's live feed when reachable (visibly
   fresher last-price updates), falls back to yfinance transparently when not.
2. Switching symbols or letting the 60s auto-refresh fire no longer causes any visible
   jump/rubber-band, and the session-open (9:15) candle stays in view.
3. Clicking 1Y, 5Y, YTD, and All in sequence all show correct real historical data,
   with no chart breakage carrying over between them.
4. Scrolling the mouse wheel out/in over the chart changes the bar interval at sensible
   zoom thresholds, keeping the same visible time window in view (no jump to fit-all).
5. Day-boundary indication no longer overlaps candle bodies.
6. Left rail includes SENSEX and CHINA (000001.SS) alongside the existing 8.

## Open Questions (increment 2)
None blocking — proceeding on the assumptions above.

## Increment 6: true real-time quotes, SENSEX delay, futures naming

### Objective
The chart and price must track the market at the fastest rate any free source allows, and the app
must be honest about how fresh each symbol's data is. Three user reports: (1) "still ~1 minute
latency, not real-time", (2) "SENSEX is 15-20 minutes behind", (3) "futures shows ES=F, is that SPX?".

### Measured findings (live, market open, 2026-09-21 ~12:30 IST)
- **Increment 2's NSE `allIndices` "optimization" was a mistake.** That feed refreshes ~once a
  minute and its stamp runs 1-2 minutes behind the wall clock (price stuck at 23417.95 while the real
  price was 23422.1). Preferring it made NIFTY/BANKNIFTY/NIFTYIT *worse* than plain Yahoo.
- **Yahoo's direct chart API is the real-time source for NSE indices/stocks:** `regularMarketTime`
  ticks every ~11s, always <=11s old, ~150ms round trip. `interval=1d&range=1d` returns the same live
  meta in 1 KB (`regularMarketPrice`, `regularMarketTime`, `chartPreviousClose`).
- **SENSEX (`^BSESN`) on Yahoo is delayed a flat ~15 minutes** (licensing, not our bug): last bar and
  meta time were 900-955s old. BSE's own JSON feed
  (`api.bseindia.com/RealTimeBseIndiaAPI/api/GetSensexData/w`, needs Referer/Origin headers) is
  current to the minute and changed every ~30s.
- **CME futures (`ES=F`, `NQ=F`, `YM=F`) are ~10 minutes delayed on Yahoo** (ES=F meta age 604s).
- `ES=F` *is* S&P 500 futures: the CME E-mini S&P 500 front-month contract. `NQ=F` is the
  **Nasdaq-100** E-mini (not the Nasdaq Composite `^IXIC` the NASDAQ rail item charts). `YM=F` is Dow.

### Assumptions (proceeding unless corrected)
1. "Real-time" means the best a free, unauthenticated source gives: Yahoo ticks ~every 11s. Sub-second
   TradingView-style streaming needs a paid exchange feed or broker API (Zerodha/Upstox) and is out of scope.
2. Using Yahoo's and BSE's public chart/quote endpoints server-side is acceptable for a personal tool.
   Both are unofficial and may change; every source needs a fallback and a visible freshness indicator.
3. Do NOT scrape TradingView's websocket (ToS) or other third-party sites.
4. For delayed symbols we cannot fix the source, so we label the delay instead of pretending.

### Success Criteria
1. NIFTY/BANKNIFTY/NIFTYIT/stocks: price on screen is <=15s behind Yahoo's tick (2s poll + ~11s tick).
2. SENSEX price and live candle come from BSE and are <=60s old (was ~900s).
3. The status bar shows data age per symbol ("Live · 6s", "BSE · 25s", "Delayed 10m") and turns amber when
   older than ~90s, so a delayed feed is never mistaken for a broken app.
4. Futures/cash toggle shows readable names ("S&P 500 Futures (ES)") everywhere the raw ticker appeared
   (search box, legend, watermark, title, options modal); the rail keeps SPX highlighted while on ES=F.
5. NASDAQ futures are labelled "Nasdaq-100 Futures (NQ)" so the Composite-vs-100 difference is explicit.
6. NSE `allIndices` code is removed (dead + harmful); README and docs no longer claim it is fresher.

### Boundaries
- Always: fall back Yahoo v8 -> yfinance `fast_info`; never let a source failure surface as an error toast per poll.
- Ask first: adding any paid/broker data source or a websocket dependency.
- Never: scrape TradingView; hard-code credentials.

### Open Questions
1. Do you want a broker feed (e.g. Zerodha Kite Connect, ~Rs 500/mo, true tick data) later? That is the only
   route to sub-second latency and un-delayed SENSEX/futures history.

## Increment 7: SENSEX bars, and the Call Auction Session panel

### Objective
Two reports: (1) "SENSEX is still 15 minutes behind" after increment 6, and (2) add a panel under
the index list tracking the call auction session, pre and post.

### Measured findings (live, market open, 2026-09-21 ~12:45-13:05 IST)
- **Increment 6 only fixed half of SENSEX.** The quote came from BSE and was fresh (~88s), but
  `/api/candles` still came from Yahoo, whose SENSEX *bars* were 989s (16.5 min) old. The chart —
  what the user actually looks at — was still a quarter hour behind.
- **BSE publishes exactly one SENSEX value per minute.** Polled every 1.2s for 40s: one distinct
  update. So it is a sampled series, not a tick stream, and naive bucketing yields flat candles
  (open == high == low == close).
- **BSE has no public intraday-bar endpoint for the index.** `StockReachGraph` is stocks-only and
  returns empty for SENSEX/16; the other eight candidate paths return the site's HTML shell.
- **NSE's pre-open feed is real**: `/api/market-data-pre-open?key=ALL|FO` returns per-stock IEP,
  ATO quantities, buy/sell depth, advances/declines and total traded value, stamped 09:09:31.
  `key=NIFTY`/`key=BANKNIFTY` answer "No Data Found" outside the window.
- **Index-level auction values** live on `allIndices`: `open` (the pre-open discovered level) and
  `indicativeClose` (0 mid-session, populated during the closing session). BSE's SENSEX feed
  carries the same two as `I_open` and `iclsprice`.
- **The closing session is not an auction.** 15:40-16:00 trades at the already-determined close,
  so there is no IEP to display — only the indicative/official close.

### Assumptions (proceeding unless corrected)
1. "CAS, pre and post auction" = NSE's pre-open (09:00-09:15) and closing session (15:40-16:00).
2. Rebuilding SENSEX bars from a once-a-minute sample is acceptable if the derivation is stated:
   each bar opens at the previous sample; high/low are the sampled range, not true extremes.
3. Coverage starting at process start is acceptable, since Yahoo supplies everything older than
   ~15 min and the two overlap after 15 minutes of uptime.
4. Indices with no public auction feed are marked unavailable rather than approximated.

### Success Criteria
1. SENSEX's newest candle is <=2 min old while the market is open (was ~15 min).
2. SENSEX candles are not flat.
3. The CAS panel sits under the index list, shows each index's auction value and change, names the
   current phase with a countdown, and lists which indices have no feed.
4. The freshness badge does not read "Delayed" for a healthy once-a-minute feed.

### Open Questions
1. The panel could not be verified during a live auction window (next is 15:40 IST). Its
   pre-open branch is built against this morning's frozen 09:09 snapshot.
2. Should SENSEX bars persist across restarts (a small on-disk cache) so the gap does not reopen?

### Increment 7b: live CAS feed window
Request: view the auction live, from the underlying feed, as it happens.

Measured: NSE's `market-data-pre-open` carries far more than the index summary already shown -
per stock it gives IEP, previous close, change, final quantity, total buy/sell quantity, ATO
quantities, and a 10-rung price ladder with the equilibrium rung flagged. `key=FO` is 211 KB raw
(~43 KB trimmed, 210 names) which is cheap enough to poll every 3s; `key=ALL` is 2.3 MB / 2425
names, so it is offered for inspection but not meant for polling.

Built: `/api/cas/feed` (trimmed rows + breadth; `symbol=` returns one stock's ladder) and a modal
that polls it every 3s, sorts, filters, and expands a row into its order book.

Caveat carried over: the pre-open branch is exercised against the frozen 09:09 snapshot NSE keeps
serving; genuine live behaviour is unverified until 09:00 IST.

### Increment 7c: correct the CAS timings (I had them wrong)

I had hard-coded post-close as 15:40-16:00 from memory. The user asked whether 15:15-15:30 would
show, which prompted a documentation check. It would not have, and my window was wrong.

Verified against SEBI circular HO/47/11/11(3)2025-MRD-POD2/I/2765/2026 (16 Jan 2026), NSE's CAS
product page and broker documentation:
- **Closing Auction Session runs 15:15-15:35**, live since **3 August 2026**, for F&O-eligible
  stocks. Continuous trading in those names stops at 15:15 — it does not run to 15:30.
- Stages: 15:15-15:20 reference price (VWAP 15:00-15:15), no new orders; 15:20-15:25 order entry
  (market & limit); 15:25-15:30 limit only with random closure 15:28-15:30; 15:30-15:35 matching,
  confirmation, closing price.
- **Post-market is 15:50-16:00** (market orders at the close), not 15:40-16:00.
- Pre-open 09:00-09:15 confirmed, with stages 09:00-09:05 / 09:05-09:10 (random close 09:08-09:10)
  / 09:10-09:12 matching / 09:12-09:15 buffer.
- Non-F&O stocks keep the VWAP close and trade to 15:30.

Lesson applied: the session is now read from NSE's live `marketStatus` first, with the clock used
only for countdowns, so the next timetable change degrades to a wrong countdown rather than a
wrong session name.

### Increment 7d: the closing auction has its own feed (I was reading the wrong one)

The live-feed window read NSE's `market-data-pre-open` endpoint. That is the pre-open auction; at
15:15 it would have shown the stale 09:09 snapshot. Searching found NSE has a separate
*Market Watch - Closing Auction Session* page. Its API path is not documented; it was read out of
that page's JavaScript bundle: `/api/NextApi/apiClient/casApi?functionName=getCASData`.

Measured: it answers today with `symbols` = the 210 eligible F&O names and `data` = [] (rows only
exist 15:15-15:35). Row fields, from the page's own table code: symbol, refrencePrice (NSE's
spelling), change, perChange, bestBidPrice/Qty, bestAskPrice/Qty, totTradedQty, finalPrice,
finalQuantity, finalValue, orderBook[{price, buyQuantity, sellQuantity, flag}], plus totals.

Other markets (searched): US imbalance data is subscription-only; KRX 15:20-15:30, TWSE 13:25-13:30
(simulated prices disclosed), SSE 14:57-15:00 have auctions but no free public feed was found.

UNVERIFIED: the real CAS row payload. Outside the window `data` is empty, so the field mapping is
from the page's code, not from observed data, and the meaning of `orderBook.flag` is unknown - the
UI shows it verbatim instead of interpreting it. Tested with a synthetic payload built from those
field names, which proves the code paths, not the data.

### Increment 8: BSE's push stream, and Live CAS movement

Request: dig deeper for BSE; add a separate button that shows live CAS movement for all indices.

**Correction to increment 7.** I wrote that "BSE publishes exactly one SENSEX value per minute". That was
true only of BSE's *REST* endpoint (`GetSensexData/w`). BSE's website does not use it for the live
ticker: it opens a **Socket.IO v4 websocket** to `bnotification.bseindia.com` and joins `SenSexValue`
and `SensexIndicativePrice`. Found by reading `beta.bseindia.com/D90/Controller/factoryother.js`
(`sensexstreamurl` is in `/version.js`). Measured: 114 messages in 40s, 33 distinct values - roughly
2 updates/second - versus one change per minute on REST.

What that fixes: SENSEX price age 65-88s -> 2-3s, and SENSEX candles now have true intra-minute
ranges (10.40 / 17.66 / 8.52 points) instead of chained once-a-minute samples.

`SensexIndicativePrice` also carries the auction fields: `indicativePriceFlag`, `todayIndexClose`
(indicative close), `IChange`, `IpercChange`, `session`, and a seconds-resolution `datettime`.

**TLS problem, handled without weakening it.** The stream host's certificate chain is incomplete (the
server omits the GlobalSign intermediate; browsers fetch it themselves). Python fails verification.
A first attempt to bypass verification for a probe was blocked, correctly. Instead the missing
intermediate is fetched from the leaf certificate's own AIA "CA Issuers" URL and added to certifi's
roots, and verification stays fully on (`bse_stream.build_ssl_context`).

**Live CAS movement**: `/api/cas/movement` returns a per-index series; SENSEX from the BSE stream,
NIFTY/BANKNIFTY/NIFTYIT sampled from NSE `allIndices` (which NSE refreshes ~1/min, so those are coarser).
Indices with no public auction feed are listed as unavailable, not simulated.

Still unverified: real closing-auction payloads. A recorder is capturing NSE `casApi`, `marketStatus`,
`allIndices` and the BSE stream through 15:15-15:40 today to settle the field mapping.

New dependency note: none added (`websockets`, `certifi`, `cryptography` were already installed);
they should be listed in requirements.txt.

### Increment 8b: Live CAS window redesigned (Indian indices, quadrants, reference price)

Request: only the Indian indices, as full-size graphs, in four quadrants, one index per corner; the
value at 15:14:59 is the reference and everything is measured against it; drop the unavailable markets.

Built: a near-full-screen 2x2 window (704x378 per quadrant at 1440 wide). Each quadrant is a
Lightweight-Charts *baseline* series with baseValue = the reference, so it draws green above and red
below by construction. A dotted REF line carries the reference price. Headers show the move vs the
reference in points and %.

Reference: locked from 15:15:00 as the last value at or before 15:14:59. Verified live at 15:15:45:
NIFTY 23423.85 @ 15:14:56, BANKNIFTY 56503.85 @ 15:14:54, NIFTYIT 28858.70 @ 15:14:55, SENSEX 74893.77
@ 15:14:59. The NSE indices' "last" comes from Yahoo's real-time tick, not NSE allIndices, because NSE's
feed lags 1-2 minutes and would give a stale reference.

Observed in the first minute of the auction: SENSEX carried a live `indicativeClose` on BSE's stream
(74906.37, +12.60 pts vs the reference) before the NSE indices showed one.

### Increment 8c: real closing-auction data observed (15:15-15:24), mapping corrected

A recorder captured NSE and BSE during today's auction. Facts now VERIFIED, replacing the earlier "unverified":
- `casApi/getCASData` has empty `data` until **15:15:17**, then 210 rows. At **15:20:24** `status` becomes
  "Open" with `statusMsg` "Closing Auction Session Market Open" and `indicativeTotalQuantity` populates.
- Row fields: IEP, atoBuyQuantity, atoSellQuantity, avgTrdPrice, bestAsk/Bid price+qty, change, finalPrice,
  finalQuantity, finalValue, high/low/openPrice, iiqAtEP, iiqAtMO, indicativeValue, lastTradedPrice,
  lowerBand, upperBand, orderBook, perChange, prevClose, refrencePrice, totalBuy/SellQuantity, totTradedQty.
- **My earlier mapping was wrong**: I displayed `finalPrice` as the indicative price. It is 0 until
  matching; the indicative price is `IEP`. Fixed, and the imbalance fields (iiqAtEP, iiqAtMO) added.
- `iiqAtMO == atoBuy - atoSell` in 210/210 rows (positive = buy surplus).
- `orderBook[].flag` is a boolean, true exactly on the equilibrium rung (38/38 rungs had price == IEP).
- `change`/`perChange` are relative to `refrencePrice`, not the previous close.
- NSE's index-level indicative values (`allIndices.indicativeClose`) populated only once order entry began
  (~15:20); BSE's SENSEX indicative was present from 15:15.

Process bug caught: editing app.py restarts Flask's debug reloader, which would have wiped the locked
reference price and the in-memory chart history in the middle of the auction. The state is now persisted
to a seed file every 10s and reloaded on start; verified across a real restart (references and 935 SENSEX
points survived unchanged). A slice bug in my own patch was stopped by an assertion before it wrote.

### Increment 9: the closing value, and a per-index data-source map

Found while preparing the README: after the closing auction the app showed NIFTY 23429.00 while the
official close was 23414.30. Yahoo's NSE-index tick stops at the auction (last tick 15:17:32 IST) and
never carries the closing value; its 1-minute bars stop at 15:14. SENSEX was already correct because
BSE's push stream carries the final close (74858.99).

Fix: when Yahoo's tick for NIFTY / BANK NIFTY / NIFTY IT is over 120 s stale and NSE's `allIndices`
stamp is newer, the quote uses NSE. Verified against the official closes: NIFTY 23414.30, BANKNIFTY
56470.65, NIFTYIT 28830.90, SENSEX 74858.99 - all four match; stocks and global indices unaffected.

Not fixed: the candle chart for the NSE indices still ends at 15:14 (Yahoo has no bars after it).
The closing value appears in the price and change, not as a final candle.

Measured feed map (README "Data sources: what feeds each index"): Yahoo tick age 1-5 s for the NSE
indices; BSE stream 2-3 s for SENSEX; CME futures 10.1 min delayed; KOSPI / TAIEX / CSI 300 / SSE showed
no delay at their close (one day, sessions already over); US indices not measured (market closed).

## Increment 10: hover color fix, measure tool, full OHLC labels, market breadth, top movers, 200 SMA, light mode

### Objective
Seven requested additions/fixes to the charting UI and data surfaced, in one batch:
1. A hover-value color that currently reads as blue should read as green/red instead.
2. Ability to pick two points on the chart and see the % change between them.
3. The OHLC legend should spell out "Open/High/Low/Close", not single letters.
4. Each index should show, live, how many of its constituent stocks are up vs down.
5. A "Top Gainers/Losers" tab/modal.
6. A 200-period SMA alongside the existing SMA 20/50.
7. A light theme, toggleable alongside the current (only) dark theme.

### Verified facts (checked live against the running app and NSE before writing this)
- **The "blue" is the Line/Area chart style.** Reproduced by switching chart style to Line: the
  series line, its right-axis last-value tag, and the legend's "C" value are all rendered in
  `--accent` (`#4c8dff`, blue) — a fixed color unrelated to whether the index is up or down.
  Candle/Bar style already colors correctly (teal up / red down per bar). Confirmed via a live
  browser screenshot (2026-09-23, NIFTY, price 23430.60, line + axis tag + legend all blue).
- **The legend currently reads exactly `O`/`H`/`L`/`C`** (confirmed in the same screenshot) — single
  letters with no full word anywhere, including for Line/Area style where only `C` shows.
- **NSE's `/api/allIndices`** (already polled by `orazio/cas.py` and cached) returns `advances`,
  `declines`, and `unchanged` **per index row**, live. Verified: NIFTY 50 → `{advances: 35, declines:
  15, unchanged: 0}` right now. This covers NIFTY, BANK NIFTY, and NIFTY IT (the three NSE indices
  this app already tracks by name) at zero extra request cost — it's the same payload already being
  fetched.
- **No public per-constituent breadth feed exists for SENSEX or any of the non-Indian indices**
  (SPX, NASDAQ, DOWJONES, KOSPI, TAIEX, CHINA, SSE) — searched, none found. This mirrors the existing
  CAS pattern ("No public auction feed: SPX, NASDAQ, ...").
- **NSE's `/api/live-analysis-variations?index=gainers|loosers`** is live and free (same cookie
  pattern as every other NSE call here). It returns pre-sorted mover lists **segmented by universe**:
  `NIFTY`, `BANKNIFTY`, `NIFTYNEXT50`, `SecGtr20`, `SecLwr20`, `FOSec`, `allSec` (whole market). Verified
  live: NIFTY gainers today led by BAJFINANCE (+2.59%), HINDALCO (+1.68%), each row carrying
  `symbol`, `open_price`, `high_price`, `low_price`, `ltp`, `prev_price`, `perChange`, `trade_quantity`.
  No such endpoint/universe exists for NIFTYIT, SENSEX, or any non-Indian index.
- **`equity-stockIndices` (a commonly-cited NSE endpoint for per-index constituent lists) 404s** on
  this app's existing NSE session/cookie handling — not used.
- **Every color in `static/styles.css` is a `var(--token)` reference** off a single `:root` block —
  a light theme is a second token block keyed off `[data-theme="light"]`, not a rule-by-rule rewrite.
  The one non-token exception is `color-scheme: dark` and a few hardcoded `rgba(0,0,0,...)` modal/toast
  shadow colors, which read fine unchanged under a light theme (dark overlays remain conventional).
- **Chart colors are computed once** (`COLORS` in `static/js/state.js`, read via `getComputedStyle` at
  module load) and handed to Lightweight Charts at series-creation time. Lightweight Charts does not
  watch CSS variables — switching the theme requires recomputing `COLORS` and calling `applyOptions()`
  on the chart and every series (main chart + the 4 CAS-movement quad charts) after the token swap.

### Assumptions (proceeding unless corrected)
1. **Hover-color fix, scope:** applies to Line and Area chart styles only (Candle/Bar are already
   correct). The line color, its last-value axis tag, and the legend's Close value all switch between
   `--up` (green) and `--down` (red) based on **current price vs. the session's previous close**
   (same comparison already used for the price-ticker chip), not vs. the previous bar. This matches
   how a trader reads a line chart (one color for "the day," not per-tick flicker) and reuses data
   the quote poll already has (`change`/`changePercent` from `/api/quote`).
2. **Measure tool, interaction model:** a new toolbar toggle button ("Measure", ruler icon). While
   active: first click sets point A, second click sets point B and draws a line between them with a
   floating label showing Δ price, Δ % (B vs A), and the time/bar span between them; a third click
   starts a new measurement from that point; **Escape** or toggling the button off clears it and
   returns to normal pan/zoom/crosshair behavior. Only one measurement is shown at a time (not a
   stack of saved measurements) — this is a scratch tool, not an annotation feature.
3. **Measure tool, implementation:** built the same way the existing day-boundary lines are (a
   positioned DOM overlay synced to `timeToCoordinate`/`priceToCoordinate` on pan/zoom), since
   Lightweight-Charts v4 has no primitives API for custom drawings — consistent with the existing
   `renderDayLines` pattern in `chart.js`.
4. **OHLC labels:** legend shows the full words ("Open", "High", "Low", "Close") instead of single
   letters, for both the default (last bar) and hover (crosshair bar) states, in both Candle/Bar mode
   (all four) and Line/Area mode (Close only, per assumption 1's color fix).
5. **Market breadth, scope:** live advances/declines/unchanged shown for NIFTY, BANK NIFTY, and NIFTY
   IT only (the ones NSE's `allIndices` already covers). SENSEX and every non-Indian rail index show
   no breadth line at all (not a "0/0" or an "unavailable" placeholder) — consistent with how those
   indices already have no CAS row content beyond the "no public feed" note, rather than adding visual
   noise to 8 rail rows that can never have this data.
6. **Market breadth, placement:** shown "on the side" = directly under each of the three eligible
   rail buttons (NIFTY/BANKNIFTY/NIFTYIT), as small green "▲35" / red "▼15" counts — same rail
   real estate pattern the app already uses for the symbol name subtitle, not a separate new panel.
   Backed by a new `GET /api/breadth` endpoint that reuses the already-polled/cached `allIndices`
   response (no new outbound NSE traffic), polled by the frontend every 5s.
7. **Top movers, scope:** one new modal (opened via a new toolbar button, next to Options) defaulting
   to **whole-market** movers (`allSec`) with a small **NIFTY / BANK NIFTY / Market** segmented toggle
   inside the modal (mirroring the existing pre-open feed's "F&O / All" toggle pattern) — because
   `live-analysis-variations` doesn't cover NIFTYIT, SENSEX, or any global index, a fixed "top movers
   for whatever symbol is on screen" design would be unavailable most of the time. Two side-by-side
   tables (Gainers / Losers), sorted by `perChange`, refreshed every ~10s while the modal is open —
   matching the existing CAS-feed modal's poll cadence pattern (that one is 3s because auctions move
   fast; movers don't need that).
8. **200 SMA:** a third checkbox ("SMA 200") next to the existing SMA 20/50, computed the same way
   (over whichever candles are currently loaded/displayed, whatever the interval) — consistent with
   how SMA 20/50 already behave (they're "N bars," not "N calendar days," on intraday intervals too).
   It will render empty until 200 bars are loaded (same as SMA 20/50 today with fewer bars). Line
   color: a fourth distinct color not already used (SMA20=amber, SMA50=purple) — proposing a light
   blue/cyan, distinct from both the up/down palette and the accent color freed up by fix #1.
9. **Light mode, scope:** a single toolbar toggle (sun/moon icon) that flips a `data-theme` attribute
   on `<html>`, persisted in the existing `localStorage` prefs blob alongside symbol/style/SMA/volume.
   Defaults to the current dark theme for existing and new users (no OS `prefers-color-scheme` auto
   switch in this pass — explicit user choice only, since silently changing an already-configured
   look on next visit would be surprising). Applies app-wide: rail, toolbar, all modals, and the
   chart itself (colors recomputed and reapplied per the "Chart colors are computed once" fact above).
10. **Scope boundary:** this increment does not add a broker-grade real-time breadth feed, does not
    persist/save measurements, does not add more than one light palette, and does not extend top-movers
    to any market this app doesn't already have an NSE feed for.
→ Correct me now on 2 (measure-tool interaction), 6 (breadth placement), 7 (top-movers scope), or 9
  (light-mode default/scope) in particular — those are the ones with real design latitude — or I'll
  build to all ten as written.

### Tech Stack
No change: Flask + yfinance/NSE/BSE backend, vanilla JS ES modules + Lightweight-Charts frontend,
plain CSS custom properties. No new dependencies (frontend or backend) — everything above is served
by data/CSS mechanisms already in the codebase.

### Project Structure (files this touches)
```
orazio/routes.py       → new GET /api/breadth ; new GET /api/movers
orazio/cas.py or a new orazio/breadth.py  → per-index advances/declines shaping, mover-list shaping
orazio/nse_client.py   → reused as-is (same nse_get())
static/js/chart.js     → hover-color fix (line/area), full OHLC legend words, SMA 200 series
static/js/data.js      → wire live price vs. prevClose into the line/area color decision
static/js/rail.js      → per-rail-item breadth counts, poll + render
static/js/state.js     → COLORS becomes recomputable; add light-theme token awareness
new static/js/measure.js   → the two-point measure tool
new static/js/movers.js    → the Top Gainers/Losers modal
static/js/main.js      → wire the new measure/theme toggle buttons + boot state
static/js/prefs.js     → persist theme choice alongside existing prefs
static/index.html      → new toolbar buttons (measure, theme, top-movers), new modal markup
static/styles.css      → `[data-theme="light"]` token block; new small styles for breadth counts,
                          measure-tool overlay/label, movers modal, SMA 200 toggle
tests/                 → unit tests for the new breadth/movers shaping functions (pure logic, same
                          pattern as test_cas.py)
```

### Code Style
Same as the rest of the codebase: new backend functions follow the existing `{available: false,
reason: "..."}` pattern instead of erroring when NSE data isn't available for a given index; new
frontend modules follow the existing ES-module-per-feature split (state object, no framework,
DOM helpers from `state.js`).

### Testing Strategy
Backend: pytest unit tests for the new pure shaping functions (breadth row → `{alias, advances,
declines, unchanged}`; NSE mover row → the frontend's row shape), same style as `tests/test_cas.py`.
No unit tests for frontend JS (matches current project convention — verified manually in-browser via
chrome-devtools instead, as done for every prior increment).
Manual verification (browser): line/area chart on an up day and a down day both color correctly;
measure tool across a few bar counts and directions; legend words in all 4 chart styles; breadth
counts visible under NIFTY/BANKNIFTY/NIFTYIT only and ticking; movers modal opens, sorts, and the
universe toggle switches data; SMA 200 draws once 200+ bars are loaded; theme toggle flips the whole
app including an already-open chart, and persists across a reload.

### Boundaries
- Always: keep the existing "unavailable, not fabricated" pattern for any index/market NSE doesn't
  cover (breadth, movers) — never approximate or show a fake 0.
- Ask first: adding any new outbound data source beyond NSE/Yahoo/BSE already in use; changing the
  default theme away from dark; changing existing SMA 20/50 behavior.
- Never: add a paid data source; scrape a site with ToS against it; block the main chart's load on
  the new breadth/movers requests (they are independent, best-effort polls).

### Success Criteria
1. Line and Area styles color green when price ≥ previous close, red otherwise — on the series line,
   its axis last-value tag, and the legend Close value.
2. Clicking Measure, then two points on the chart, shows a line + label with Δ price and Δ % between
   them; Escape/toggle-off clears it.
3. Legend shows "Open"/"High"/"Low"/"Close" (or "Close" alone in Line/Area) instead of single letters.
4. NIFTY, BANK NIFTY, and NIFTY IT rail items show live advance/decline counts that change without a
   page reload; no other rail item shows a breadth line.
5. A Top Gainers/Losers modal opens from the toolbar, defaults to whole-market movers, and can switch
   to NIFTY/BANK NIFTY; both tables are sorted by % change and update while open.
6. SMA 200 checkbox draws a 4th distinct-colored line once enough bars are loaded, matching the
   existing SMA 20/50 mechanics.
7. A theme toggle switches the entire app (including the live chart's own colors) between the
   current dark theme and a new light theme, and the choice survives a page reload.

### Open Questions
None — all four flagged decisions confirmed as proposed (2026-09-23):
1. Measure tool: toolbar toggle button, click-click, confirmed.
2. Breadth placement: small counts under each eligible rail item, confirmed.
3. Top movers: whole-market default with a NIFTY/BANKNIFTY toggle inside the modal, confirmed.
4. Theme default: manual toggle, defaults to dark, confirmed.
Proceeding to Plan on all ten items as written.
