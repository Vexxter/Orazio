"""Live volume/value, 52-week range and 30-day change for the chart legend.

Source: NSE's own market-watch backend (the one nseindia.com/market-data/live-equity-market
calls), `marketWatchApi?functionName=getIndicesData&symbol=<index short name>`. One call
returns the index row (priority 1) plus every constituent, each with totalTradedVolume
(shares), totalTradedValue (rupees), yearHigh/yearLow and perChange30d/perChange365d.

Stocks are looked up in the NIFTY TOTAL MKT universe (~750 names) rather than one call per
stock. Index names must be the SHORT form from getIndexList ("NIFTY TOTAL MKT", not
"NIFTY TOTAL MARKET") or NSE answers with an empty object.
"""
from .cache import cached
from .nse_client import nse_get

STATS_TTL = 3  # seconds — the page itself refreshes about this often

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


def stats_for(yahoo_symbol):
    """Stats dict for a chart symbol, or None when NSE has nothing for it (US/Asian
    indices, BSE-only names, ...)."""
    if yahoo_symbol in INDEX_QUERY:
        return _index_stats(INDEX_QUERY[yahoo_symbol])
    if yahoo_symbol.endswith(".NS"):
        return _stock_map().get(yahoo_symbol[:-3])
    return None
