"""Earnings centre (Bloomberg's EE / ERN, on public data): which companies report results in the coming days.

Source: NSE /api/event-calendar (upcoming board meetings, about 200 rows; shape as measured on 13 Nov 2026). Only
meetings whose purpose mentions results are kept. Past results dates per stock come from chart_events (NSE board
meeting history) and the reported numbers from fundamentals.py; the page measures each stock's reaction itself.
"""
from datetime import date, datetime

from .cache import cached
from .nse_client import nse_get

TTL = 1800


def _iso(s):
    try:
        return datetime.strptime((s or "").strip().title(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def shape(r):
    if "result" not in f"{r.get('purpose', '')} {r.get('bm_desc', '')}".lower():
        return None
    d, sym = _iso(r.get("date")), (r.get("symbol") or "").strip().upper()
    if not d or not sym:
        return None
    return {"date": d, "symbol": sym, "chartSymbol": f"{sym}.NS", "company": (r.get("company") or "").strip(),
            "purpose": (r.get("bm_desc") or r.get("purpose") or "").strip()}


def calendar(symbols=None, today=None):
    """Upcoming results meetings, soonest first; `symbols` (bare NSE tickers) narrows it to a watchlist."""
    today = (today or date.today()).isoformat()
    raw = cached(("event-calendar",), TTL, lambda: nse_get("/api/event-calendar"))
    if not isinstance(raw, list):
        return {"available": False, "rows": []}
    rows = [x for x in map(shape, raw) if x and x["date"] >= today]
    if symbols:
        want = {s.upper().removesuffix(".NS") for s in symbols}
        rows = [r for r in rows if r["symbol"] in want]
    rows.sort(key=lambda r: (r["date"], r["symbol"]))
    return {"available": True, "rows": rows}
