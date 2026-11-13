"""Live volume/value, 52-week range and 30-day change for the chart legend.

Source: NSE's own market-watch backend (the one nseindia.com/market-data/live-equity-market
calls), `marketWatchApi?functionName=getIndicesData&symbol=<index short name>`. One call
returns the index row (priority 1) plus every constituent, each with totalTradedVolume
(shares), totalTradedValue (rupees), yearHigh/yearLow and perChange30d/perChange365d.

Stocks are looked up in the NIFTY TOTAL MKT universe (~750 names) rather than one call per
stock. Index names must be the SHORT form from getIndexList ("NIFTY TOTAL MKT", not
"NIFTY TOTAL MARKET") or NSE answers with an empty object.

NSE has nothing for SENSEX or for futures, so those are computed from daily bars instead: SENSEX
from Yahoo's ^BSESN history plus BSE's live price, a future (NIFTY-FUT, SENSEX-FUT, ...) from its
stitched front-month history (fno.daily_bars) plus the live front-month row for the day's volume/value.
"""
import yfinance as yf

from . import fno
from .cache import cached
from .candles import df_to_rows
from .nse_client import nse_get

STATS_TTL = 3  # seconds — the page itself refreshes about this often
HISTORY_TTL = 600  # the daily history behind the computed stats

INDEX_QUERY = {"^NSEI": "NIFTY 50", "^NSEBANK": "NIFTY BANK", "^CNXIT": "NIFTY IT"}
STOCK_UNIVERSE = "NIFTY TOTAL MKT"


def _rows(index_name):
    d = nse_get("/api/NextApi/apiClient/marketWatchApi",
                {"functionName": "getIndicesData", "symbol": index_name})
    try:
        return d["data"]["data"] or []
    except (KeyError, TypeError):
        return []


def _shape(r):
    return {
        "volume": r.get("totalTradedVolume"),
        "value": r.get("totalTradedValue"),
        "yearHigh": r.get("yearHigh"),
        "yearLow": r.get("yearLow"),
        "change30d": r.get("perChange30d"),
        "change365d": r.get("perChange365d"),
        "asOf": r.get("lastUpdateTime"),
    }


def _index_stats(index_name):
    def fetch():
        for r in _rows(index_name):
            if r.get("priority") == 1:
                return _shape(r)
        return None
    return cached(("stats-index", index_name), STATS_TTL, fetch)


def _stock_map():
    def fetch():
        return {r["symbol"]: _shape(r) for r in _rows(STOCK_UNIVERSE)
                if r.get("priority") != 1 and r.get("symbol")}
    return cached(("stats-stocks", STOCK_UNIVERSE), STATS_TTL, fetch)


def constituent_symbols(index_name):
    """Yahoo tickers (SYMBOL.NS) of an NSE index's current constituents."""
    return [f"{r['symbol']}.NS" for r in _rows(index_name)
            if r.get("priority") != 1 and r.get("symbol") and r.get("series") == "EQ"]


def from_daily(bars, price=None):
    """52-week range and 30/365-day change from daily OHLC bars (oldest first), with `price` as the
    latest value when given. Changes compare against the last close on or before 30/365 days ago."""
    if not bars:
        return None
    price = price if price is not None else bars[-1]["close"]
    now = bars[-1]["time"]
    year = [b for b in bars if b["time"] > now - 365 * 86400]

    def change(days):
        base = next((b["close"] for b in reversed(bars) if b["time"] <= now - days * 86400), None)
        return round((price / base - 1) * 100, 2) if base else None
    return {"yearHigh": max([b["high"] for b in year] + [price]), "yearLow": min([b["low"] for b in year] + [price]),
            "change30d": change(30), "change365d": change(365), "volume": None, "value": None, "asOf": None}


def _sensex_stats():
    from .market_data import bse_live_quote   # deferred: market_data starts the BSE stream on import
    bars = cached(("stats-hist", "^BSESN"), HISTORY_TTL,
                  lambda: df_to_rows(yf.download("^BSESN", period="2y", interval="1d", progress=False)))
    q = bse_live_quote()
    return from_daily(bars, q and q["price"])


def _future_stats(symbol):
    res = fno.resolve(symbol)
    if not res:
        return None
    bars = cached(("stats-hist", res["fut"]), HISTORY_TTL, lambda: fno.daily_bars(res["underlying"], 400))
    rows, _spot, ts = fno.futures(res["underlying"])
    front = rows[0] if rows else {}
    s = from_daily(bars, front.get("last"))
    if s:
        s.update(volume=front.get("volume"), value=front.get("turnover"), asOf=ts)
    return s


def stats_for(yahoo_symbol):
    """Stats dict for a chart symbol, or None when there is nothing for it (US/Asian indices,
    BSE-only names, ...)."""
    if yahoo_symbol == "^BSESN":
        return _sensex_stats()
    if yahoo_symbol.endswith("-FUT"):
        return _future_stats(yahoo_symbol)
    if yahoo_symbol in INDEX_QUERY:
        return _index_stats(INDEX_QUERY[yahoo_symbol])
    if yahoo_symbol.endswith(".NS"):
        return _stock_map().get(yahoo_symbol[:-3])
    return None
