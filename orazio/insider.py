"""Insider trades under SEBI's PIT regulations: promoters, directors and staff reporting their own buys and sells.

Source: NSE /api/corporates-pit (shape as measured on 13 Nov 2026). One row per disclosure; secVal is rupees.
Only open-market trades (Market Purchase / Market Sale) count as a signal: ESOP allotments, gifts, pledges and
off-market transfers are bookkeeping, not someone choosing to put money in or take it out.
"""
from datetime import date, datetime, timedelta

from .cache import cached
from .nse_client import nse_get

TTL = 1800
SIGNAL_MODES = {"Market Purchase": "buy", "Market Sale": "sell"}
WINDOWS = (30, 120, 365)   # days: the market-wide view widens while NSE has nothing recent (its feed paused in May 2026)


def _iso(s):
    try:
        return datetime.strptime((s or "").strip().title(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def senior(category):
    c = (category or "").lower()
    return "promoter" in c or "director" in c or "key managerial" in c


def shape(r):
    """One disclosure -> a row, or None if it isn't an open-market trade in the company's shares."""
    side = SIGNAL_MODES.get((r.get("acqMode") or "").strip())
    day = _iso(r.get("acqtoDt")) or _iso(r.get("acqfromDt"))
    if not side or not day or (r.get("secType") or "").strip() != "Equity Shares":
        return None
    sym = (r.get("symbol") or "").strip().upper()
    return {"symbol": sym, "chartSymbol": f"{sym}.NS", "company": (r.get("company") or "").strip(), "name": (r.get("acqName") or "").strip(),
            "category": (r.get("personCategory") or "").strip(), "senior": senior(r.get("personCategory")), "side": side,
            "qty": _num(r.get("secAcq")), "valueCr": round(_num(r.get("secVal")) / 1e7, 4), "date": day, "filed": _iso(r.get("intimDt"))}


def _fetch(params):
    d = nse_get("/api/corporates-pit", {"index": "equities", **params})
    rows = d.get("data") if isinstance(d, dict) else None
    return None if rows is None else [x for x in map(shape, rows) if x]


def _range(days, today):
    return {"from_date": (today - timedelta(days=days)).strftime("%d-%m-%Y"), "to_date": today.strftime("%d-%m-%Y")}


def for_symbol(sym, today=None):
    """Open-market insider trades in one NSE stock over three years (for chart markers)."""
    today = today or date.today()
    return cached(("insider", sym), TTL, lambda: _fetch({"symbol": sym, **_range(365 * 3, today)}) or [])


def by_company(rows):
    """Net open-market insider money per company, biggest net buyers first."""
    agg = {}
    for r in rows:
        a = agg.setdefault(r["symbol"], {"symbol": r["symbol"], "chartSymbol": r["chartSymbol"], "company": r["company"],
                                         "buyCr": 0.0, "sellCr": 0.0, "buyers": set(), "sellers": set(), "last": r["date"]})
        a["buyCr" if r["side"] == "buy" else "sellCr"] += r["valueCr"]
        a["buyers" if r["side"] == "buy" else "sellers"].add(r["name"])
        a["last"] = max(a["last"], r["date"])
    out = [{**a, "buyCr": round(a["buyCr"], 2), "sellCr": round(a["sellCr"], 2), "netCr": round(a["buyCr"] - a["sellCr"], 2),
            "buyers": len(a["buyers"]), "sellers": len(a["sellers"])} for a in agg.values()]
    return sorted(out, key=lambda a: -a["netCr"])


def recent(senior_only=True, today=None):
    """Market-wide open-market insider trades: the last 30 days, widened to 120 then 365 while NSE has none that recent."""
    today = today or date.today()
    got = window_rows(today)
    if got is None:
        return {"available": False, "rows": [], "companies": []}
    rows = [r for r in got["rows"] if r["senior"]] if senior_only else got["rows"]
    rows = sorted(rows, key=lambda r: (r["date"], r["valueCr"]), reverse=True)
    return {"available": True, "days": got["days"], "latest": rows[0]["date"] if rows else None,
            "companies": by_company(rows), "rows": rows[:300]}


def window_rows(today=None, days=None):
    """{days, rows}: every open-market trade in the window (all of them, unlike recent()'s 300), or None if NSE is down.
    days=None widens 30 -> 120 -> 365 while NSE has nothing that recent."""
    today = today or date.today()
    if days:
        return cached(("insider-window", days, today.isoformat()), TTL,
                      lambda: (lambda rows: None if rows is None else {"days": days, "rows": rows})(_fetch(_range(days, today))))

    def fetch():
        for days in WINDOWS:
            rows = _fetch(_range(days, today))
            if rows is None:
                return None
            if rows:
                return {"days": days, "rows": rows}
        return {"days": WINDOWS[-1], "rows": []}
    return cached(("insider-recent", today.isoformat()), TTL, fetch)
