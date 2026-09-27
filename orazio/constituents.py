"""Self-computed market breadth AND top movers for indices that don't publish either.

NIFTY/BANKNIFTY/NIFTYIT get breadth for free from NSE's own `allIndices` payload (see
cas.breadth_from_all_indices), and gainers/losers for NIFTY/BANKNIFTY/whole-market from
NSE's live-analysis-variations endpoint (see movers.py) — no work needed there. Nobody
publishes either for SENSEX or any of the global indices, so wherever a real constituent
list can be gotten without fabricating one, we compute both ourselves from the same
single batched fetch: pull each constituent's OHLCV via yfinance once per poll cycle,
then derive breadth (count up/down/flat) and movers (top gainers/losers by % change)
from that one dataset — not two separate fetches for two features.

Two tiers:
  - Small, hardcoded lists (SENSEX, Dow Jones — 30 stocks each). Stable enough to keep
    in code; polled every CONSTITUENT_POLL_SEC.
  - Large lists scraped live from Wikipedia's own constituent tables (S&P 500 — 503
    rows; CSI 300 — 300 rows) — fetched once and cached for a day, not hand-typed. Each
    is a real, verifiable batch download (measured live: 503/503 and 298/300 resolved
    via yfinance), so accuracy isn't the limiting factor for these two; request volume
    is. Polled on the slower LARGE_INDEX_POLL_SEC so the periodic 500+800-request burst
    doesn't stack on top of the small indices' own traffic every minute.

Still excluded: Nasdaq Composite (~3000 constituents — no clean free list, and the
count alone makes a single poll cycle impractical on an unauthenticated source),
KOSPI, TAIEX, Shanghai Composite (no clean full-constituent table found on Wikipedia
or elsewhere free — a fabricated subset would misrepresent the index, so these stay
without a breadth or movers line rather than guess).
"""
import threading
import time
from io import StringIO

import pandas as pd
import requests
import yfinance as yf

CONSTITUENT_POLL_SEC = 60
LARGE_INDEX_POLL_SEC = 300
CONSTITUENT_LIST_REFRESH_SEC = 86400  # index membership changes a handful of times a year
TOP_N_MOVERS = 15

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

# SENSEX's 30 constituents — fetched as .NS (NSE), not .BO. Verified live: Yahoo's .BO
# tickers only ever return a single day of history no matter the requested period, so
# the 2-day comparison this module needs never has a previous close to compare against.
# The same companies' .NS tickers carry full history, since nearly every BSE-listed
# large-cap is dual-listed on NSE — same stock, same closing price, better data source.
# TATAMOTORS.NS 404s: Tata Motors demerged in 2025; TMPV.NS (Tata Motors Passenger
# Vehicles) is the constituent that replaced it in the index.
SENSEX_CONSTITUENTS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "HINDUNILVR.NS",
    "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "BAJFINANCE.NS", "KOTAKBANK.NS", "LT.NS",
    "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS",
    "NESTLEIND.NS", "NTPC.NS", "POWERGRID.NS", "M&M.NS", "TATASTEEL.NS", "TMPV.NS",
    "WIPRO.NS", "HCLTECH.NS", "JSWSTEEL.NS", "INDUSINDBK.NS", "TECHM.NS", "BAJAJFINSV.NS",
]

# Dow Jones Industrial Average (30), as of Sep 2026.
DOWJONES_CONSTITUENTS = [
    "MMM", "AXP", "AMGN", "AMZN", "AAPL", "BA", "CAT", "CVX", "CSCO", "KO",
    "DIS", "GS", "HD", "HON", "IBM", "JNJ", "JPM", "MCD", "MRK", "MSFT",
    "NKE", "NVDA", "PG", "CRM", "SHW", "TRV", "UNH", "VZ", "V", "WMT",
]

SMALL_INDEX_CONSTITUENTS = {"SENSEX": SENSEX_CONSTITUENTS, "DOWJONES": DOWJONES_CONSTITUENTS}

# Each entry describes how to turn that Wikipedia page's constituent table into
# yfinance-ready tickers. Fetched live, not hand-typed — see module docstring.
LARGE_INDEX_SOURCES = {
    "SPX": {
        "wiki_page": "List_of_S%26P_500_companies",
        "table_index": 0,
        "ticker_col": "Symbol",
        "to_yf": lambda sym: sym.replace(".", "-"),  # yfinance wants BRK-B, Wikipedia has BRK.B
    },
    "CHINA": {
        "wiki_page": "CSI_300_Index",
        "table_index": 3,
        "ticker_col": "Ticker",
        # Cell looks like "SSE: 600519" or "SZSE: 300750".
        "to_yf": lambda cell: cell.split(":")[1].strip() + (".SS" if "SSE" in cell.split(":")[0] else ".SZ"),
    },
}

# Every alias this module can serve breadth/movers for.
CONSTITUENT_ALIASES = set(SMALL_INDEX_CONSTITUENTS) | set(LARGE_INDEX_SOURCES)

_lock = threading.Lock()
_breadth_cache = {}  # alias -> {"advances", "declines", "unchanged"}
_movers_cache = {}   # alias -> {"gainers": [...], "losers": [...]}
_list_cache = {}     # alias -> (tickers, fetched_at) — for the Wikipedia-sourced indices


def summarize(ohlcv_by_ticker):
    """Pure counting: {ticker: {"prevClose","last",...} | None} -> breadth counts.
    A ticker with missing/unusable data is skipped, not counted as unchanged."""
    advances = declines = unchanged = 0
    for row in ohlcv_by_ticker.values():
        if row is None:
            continue
        prev, last = row["prevClose"], row["last"]
        if last > prev:
            advances += 1
        elif last < prev:
            declines += 1
        else:
            unchanged += 1
    return {"advances": advances, "declines": declines, "unchanged": unchanged}


def total_volume(ohlcv_by_ticker):
    """Combined shares traded across today's available constituents. Not an official
    'index volume' — indices don't have one (see the ^NSEI/^BSESN Volume=0 columns
    yfinance itself returns) — just the sum of what yfinance already gives us per
    constituent while computing breadth/movers, so it costs nothing extra to expose.
    None (not 0) when no constituent had usable volume, so callers can tell "no data"
    apart from "genuinely zero volume"."""
    total = 0
    counted = 0
    for row in ohlcv_by_ticker.values():
        if row is None or row["volume"] is None:
            continue
        total += row["volume"]
        counted += 1
    return total if counted else None


def top_movers(ohlcv_by_ticker, n=TOP_N_MOVERS):
    """Pure ranking: same input as summarize() -> top N gainers/losers by % change,
    shaped like movers.py's NSE-sourced rows so the frontend renders both identically."""
    rows = []
    for ticker, row in ohlcv_by_ticker.items():
        if row is None or not row["prevClose"]:
            continue
        pct = (row["last"] - row["prevClose"]) / row["prevClose"] * 100
        rows.append({
            "symbol": ticker.split(".")[0],
            "ltp": row["last"],
            "perChange": pct,
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "volume": row["volume"],
        })
    gainers = sorted(rows, key=lambda r: r["perChange"], reverse=True)[:n]
    losers = sorted(rows, key=lambda r: r["perChange"])[:n]
    return {"gainers": gainers, "losers": losers}


def _fetch_ohlcv(tickers):
    """One batched yfinance call for all of `tickers` — not one call per stock. Serves
    both breadth and movers from the same fetch."""
    df = yf.download(tickers, period="5d", interval="1d", progress=False, group_by="ticker", threads=True)
    out = {}
    for t in tickers:
        try:
            sub = df[t].dropna(subset=["Close"])
            if len(sub) < 2:
                out[t] = None
                continue
            prev_close = float(sub["Close"].iloc[-2])
            today = sub.iloc[-1]
            out[t] = {
                "prevClose": prev_close, "last": float(today["Close"]),
                "open": float(today["Open"]), "high": float(today["High"]), "low": float(today["Low"]),
                "volume": int(today["Volume"]) if today["Volume"] == today["Volume"] else None,
            }
        except (KeyError, IndexError, ValueError, TypeError):
            out[t] = None
    return out


def _fetch_constituent_list(alias):
    cfg = LARGE_INDEX_SOURCES[alias]
    r = requests.get(f"https://en.wikipedia.org/wiki/{cfg['wiki_page']}", headers=_UA, timeout=15)
    r.raise_for_status()
    table = pd.read_html(StringIO(r.text))[cfg["table_index"]]
    return [cfg["to_yf"](v) for v in table[cfg["ticker_col"]].astype(str)]


def _get_constituent_list(alias):
    """Cached for a day — index membership doesn't change often enough to re-scrape
    Wikipedia every poll cycle. Falls back to the last good list on a fetch failure."""
    cached = _list_cache.get(alias)
    now = time.time()
    if cached and now - cached[1] < CONSTITUENT_LIST_REFRESH_SEC:
        return cached[0]
    try:
        tickers = _fetch_constituent_list(alias)
        _list_cache[alias] = (tickers, now)
        return tickers
    except Exception:
        return cached[0] if cached else []


def _update_index(alias, tickers):
    if not tickers:
        return
    try:
        ohlcv = _fetch_ohlcv(tickers)
        breadth = summarize(ohlcv)
        breadth["volume"] = total_volume(ohlcv)
        movers = top_movers(ohlcv)
    except Exception:
        return  # a bad poll must not kill the thread; the caches just keep their last value
    if breadth["advances"] + breadth["declines"] + breadth["unchanged"] > 0:
        with _lock:
            _breadth_cache[alias] = breadth
            _movers_cache[alias] = movers


def _poll_small():
    while True:
        for alias, tickers in SMALL_INDEX_CONSTITUENTS.items():
            _update_index(alias, tickers)
        time.sleep(CONSTITUENT_POLL_SEC)


def _poll_large():
    while True:
        for alias in LARGE_INDEX_SOURCES:
            _update_index(alias, _get_constituent_list(alias))
        time.sleep(LARGE_INDEX_POLL_SEC)


def start_constituent_poller():
    threading.Thread(target=_poll_small, daemon=True, name="constituent-breadth-small").start()
    threading.Thread(target=_poll_large, daemon=True, name="constituent-breadth-large").start()


def breadth_rows():
    with _lock:
        return [{"alias": alias, **data} for alias, data in _breadth_cache.items()]


def movers_for(alias):
    """Cached {gainers, losers} for one of CONSTITUENT_ALIASES, or None if not (yet)
    available — the poller hasn't completed a cycle, or the alias isn't covered here."""
    with _lock:
        return _movers_cache.get(alias)
