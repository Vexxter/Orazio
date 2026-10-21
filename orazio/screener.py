"""Stock screener rows: one NSE market-watch call per universe (the same `getIndicesData` stats.py
uses — every constituent's LTP, % change, volume, value, 52-week range, 30-day and 1-year change),
merged with the daily technicals from technicals.py (RSI, distance from SMA50/200, 50/200 crosses).

Filtering and sorting happen in the page (screener-policy.js); this only shapes the rows.
"""
from . import technicals
from .cache import cached
from .stats import _rows

UNIVERSES = {"nifty50": "NIFTY 50", "bank": "NIFTY BANK", "nifty500": "NIFTY 500", "total": "NIFTY TOTAL MKT"}
DEFAULT_UNIVERSE = "nifty500"
TTL = 10   # seconds


def _pct(a, b):
    return round((a - b) / b * 100, 2) if a is not None and b else None


def shape(r):
    """One NSE market-watch row -> one screener row (technicals still empty)."""
    ltp = r.get("lastPrice")
    value = r.get("totalTradedValue")
    symbol = r["symbol"]
    return {
        "symbol": symbol,
        "chartSymbol": f"{symbol}.NS",
        "name": r.get("companyName"),
        "ltp": ltp,
        "pChange": r.get("pChange"),
        "volume": r.get("totalTradedVolume"),
        "valueCr": round(value / 1e7, 2) if value is not None else None,
        "fromHigh": _pct(ltp, r.get("yearHigh")),
        "fromLow": _pct(ltp, r.get("yearLow")),
        "ch30": r.get("perChange30d"),
        "ch365": r.get("perChange365d"),
        "rsi": None, "vsSma50": None, "vsSma200": None, "cross": None,
    }


def _trade_date(r):
    return (r.get("lastUpdateTime") or "")[:10]   # "2026-10-19 10:43:02" -> "2026-10-19"


def _build(name):
    rows = [r for r in _rows(name) if r.get("priority") != 1 and r.get("symbol")]
    out = []
    for r in rows:
        row = shape(r)
        t = technicals.for_symbol(row["symbol"], row["ltp"], _trade_date(r) or "9999-12-31")
        if t:
            row.update(rsi=t["rsi"], vsSma50=_round(t["vsSma50"]), vsSma200=_round(t["vsSma200"]), cross=t["cross"])
        out.append(row)
    return {"rows": out, "asOf": rows[0].get("lastUpdateTime") if rows else None}


def _round(v):
    return round(v, 2) if v is not None else None


def screen(universe):
    key = universe if universe in UNIVERSES else DEFAULT_UNIVERSE
    status = technicals.ensure_fresh()
    built = cached(("screener", key, technicals.fetched_at()), TTL, lambda: _build(UNIVERSES[key]))
    return {
        "available": bool(built["rows"]),
        "universe": key,
        "asOf": built["asOf"],
        "technicals": status,
        "technicalsAsOf": technicals.fetched_at(),
        "rows": built["rows"],
    }
