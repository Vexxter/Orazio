"""Delivery and large deals for NSE cash equities.

* Delivery: NSE's daily sec_bhavdata_full_<DDMMYYYY>.csv has every EQ stock's traded and delivered quantity.
  A big delivered quantity on a move says positions changed hands (not just intraday churn). Each day's EQ rows
  are parsed once and cached under ~/.orazio/delivery/; the tab compares the latest day against the stock's
  own 20-session average.
* Deals: NSE's /api/snapshot-capital-market-largedeal (latest bulk and block deals; ~6 pm IST).
"""
import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from pathlib import Path

from .cache import cached
from .constants import IST
from .http_clients import nse_http
from .nse_client import nse_get

DIR = Path.home() / ".orazio" / "delivery"
URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"
SESSIONS = 20
MIN_TURNOVER_CR = 5
_pool = ThreadPoolExecutor(max_workers=6)


def parse_bhav(text):
    """CSV -> {symbol: [close, prev_close, traded_qty, deliv_qty, turnover_cr]} for the EQ series."""
    reader = csv.reader(io.StringIO(text))
    header = [h.strip() for h in next(reader, [])]
    if "DELIV_QTY" not in header:
        return None
    ix = {h: i for i, h in enumerate(header)}
    out = {}
    for row in reader:
        row = [c.strip() for c in row]
        if len(row) < len(header) or row[ix["SERIES"]] != "EQ":
            continue
        try:
            out[row[ix["SYMBOL"]]] = [float(row[ix["CLOSE_PRICE"]]), float(row[ix["PREV_CLOSE"]]), int(row[ix["TTL_TRD_QNTY"]]),
                                      int(row[ix["DELIV_QTY"]]) if row[ix["DELIV_QTY"]] not in ("", "-") else 0,
                                      round(float(row[ix["TURNOVER_LACS"]]) / 100, 2)]
        except ValueError:
            continue
    return out


def _day(d):
    path = DIR / f"{d:%Y%m%d}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        r = nse_http.get(URL.format(d=d), timeout=20)
    except Exception:
        return None
    if r.status_code == 404:
        if d < datetime.now(IST).date() - timedelta(days=3):
            DIR.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
            return {}
        return None
    rows = parse_bhav(r.text) if r.status_code == 200 else None
    if rows:
        DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def rank(days):
    """days: [(iso date, {symbol: row})] oldest first -> one row per liquid stock on the latest day."""
    if not days:
        return []
    latest_date, latest = days[-1]
    history = [rows for _, rows in days[:-1]]
    out = []
    for sym, (close, prev, qty, dq, turnover) in latest.items():
        if turnover < MIN_TURNOVER_CR or not qty:
            continue
        past = [h[sym] for h in history if sym in h and h[sym][2]]
        avg_dq = sum(p[3] for p in past) / len(past) if past else None
        avg_pct = sum(p[3] / p[2] for p in past) / len(past) * 100 if past else None
        out.append({
            "symbol": sym, "chartSymbol": f"{sym}.NS", "close": close,
            "pChange": round((close / prev - 1) * 100, 2) if prev else None,
            "turnoverCr": turnover, "delivPct": round(dq / qty * 100, 1),
            "avgDelivPct": round(avg_pct, 1) if avg_pct is not None else None,
            "delivX": round(dq / avg_dq, 2) if avg_dq else None,
        })
    return out


def delivery():
    def fetch():
        today = datetime.now(IST).date()
        cal = [today - timedelta(days=i) for i in range(SESSIONS * 2)]
        jobs = {d: _pool.submit(_day, d) for d in cal if d.weekday() < 5}
        wait(jobs.values(), timeout=20)
        days = sorted((d.isoformat(), j.result()) for d, j in jobs.items() if j.done() and j.result())
        days = days[-(SESSIONS + 1):]
        return {"date": days[-1][0] if days else None, "sessions": len(days) - 1 if days else 0, "rows": rank(days)}
    return cached(("delivery",), 600, fetch)


def _deal_rows(rows, kind):
    return [{"kind": kind, "date": r.get("date"), "symbol": r.get("symbol"), "name": r.get("name"),
             "client": r.get("clientName"), "side": r.get("buySell"),
             "qty": int(float(r.get("qty") or 0)), "price": float(r["watp"]) if r.get("watp") else None}
            for r in rows or []]


def deals():
    def fetch():
        d = nse_get("/api/snapshot-capital-market-largedeal") or {}
        return {"asOf": d.get("as_on_date"), "rows": _deal_rows(d.get("BLOCK_DEALS_DATA"), "Block") + _deal_rows(d.get("BULK_DEALS_DATA"), "Bulk")}
    return cached(("large-deals",), 300, fetch)
