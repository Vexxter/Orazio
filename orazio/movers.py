"""Top gainers/losers, from NSE's own live-analysis endpoint.

`/api/live-analysis-variations` is the same one nseindia.com's own "Top Gainers/Losers"
widget calls. It returns both directions (gainers, loosers — NSE's spelling) already
segmented by universe (NIFTY, BANKNIFTY, NIFTYNEXT50, SecGtr20, SecLwr20, FOSec, allSec).
Verified live: NIFTY gainers led by BAJFINANCE (+2.59%), each row carrying symbol,
open/high/low, ltp, prev_price, perChange, trade_quantity.

No universe exists here for NIFTYIT, SENSEX, or any non-Indian index — callers get an
empty result for those rather than a fabricated one.
"""
from .cache import cached
from .constants import QUOTE_CACHE_TTL
from .nse_client import nse_get

UNIVERSES = ("allSec", "NIFTY", "BANKNIFTY")


def _mover_row(r):
    return {
        "symbol": r.get("symbol"),
        "ltp": r.get("ltp"),
        "perChange": r.get("perChange"),
        "open": r.get("open_price"),
        "high": r.get("high_price"),
        "low": r.get("low_price"),
        "volume": r.get("trade_quantity"),
    }


def _variation_rows(direction, universe):
    payload = cached(("movers", direction), QUOTE_CACHE_TTL, lambda: nse_get(
        "/api/live-analysis-variations", {"index": direction}))
    section = (payload or {}).get(universe) or {}
    rows = section.get("data") or []
    return [_mover_row(r) for r in rows if isinstance(r, dict) and r.get("symbol")]


def movers(universe):
    if universe not in UNIVERSES:
        universe = "allSec"
    gainers = _variation_rows("gainers", universe)
    losers = _variation_rows("loosers", universe)
    return {
        "available": bool(gainers or losers),
        "universe": universe,
        "gainers": sorted(gainers, key=lambda r: r["perChange"] if r["perChange"] is not None else 0, reverse=True),
        "losers": sorted(losers, key=lambda r: r["perChange"] if r["perChange"] is not None else 0),
    }
