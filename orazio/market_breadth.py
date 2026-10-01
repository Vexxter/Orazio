"""Advances/declines for indices whose exchange publishes them directly.

NASDAQ: the Nasdaq-100 list from Nasdaq's own quote API (the endpoint nasdaq.com's site
  calls) — 101 rows, each already flagged up/down/unch, refreshed live. This is the
  Nasdaq-100, NOT the ~3000-stock Composite the rail charts, so the rail says so.
SSE: every Shanghai A-share, counted from Sina's market-centre list (see global_movers.py).
TAIEX: the Taiwan Stock Exchange's own whole-market count (MI_INDEX, "Net Change of Price
  (Number of Listed Securities)", Stocks column). Official and complete, but TWSE only
  publishes it after the session, so it shows the latest finished day.
"""
import re
import threading
import time

import requests

from .global_movers import sse_breadth

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}
NASDAQ_POLL_SEC = 60
TWSE_POLL_SEC = 600
SSE_POLL_SEC = 120

_lock = threading.Lock()
_rows = {}  # alias -> {"advances","declines","unchanged", ...}


def parse_nasdaq100(payload):
    rows = payload["data"]["data"]["rows"]
    counts = {"up": 0, "down": 0, "unch": 0}
    for r in rows:
        counts[r.get("deltaIndicator") if r.get("deltaIndicator") in counts else "unch"] += 1
    if not sum(counts.values()):
        return None
    return {"advances": counts["up"], "declines": counts["down"], "unchanged": counts["unch"]}


def parse_twse(payload):
    """The 'Stocks' column of the price-change table, e.g. '374(24)' -> 374 (24 limit-up)."""
    for table in payload.get("tables", []):
        fields = table.get("fields") or []
        if "Stocks" not in fields or "Type" not in fields:
            continue
        col = fields.index("Stocks")
        counts = {}
        for row in table.get("data", []):
            label = str(row[0]).lower()
            m = re.match(r"\s*([\d,]+)", str(row[col]))
            if not m:
                continue
            value = int(m.group(1).replace(",", ""))
            if label.startswith("up"):
                counts["advances"] = value
            elif label.startswith("down"):
                counts["declines"] = value
            elif label.startswith("unchanged"):
                counts["unchanged"] = value
        if {"advances", "declines", "unchanged"} <= counts.keys():
            return counts
    return None


def _poll_nasdaq():
    while True:
        try:
            r = requests.get("https://api.nasdaq.com/api/quote/list-type/nasdaq100",
                             headers={**_HEADERS, "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"},
                             timeout=15)
            r.raise_for_status()
            counts = parse_nasdaq100(r.json())
            if counts:
                with _lock:
                    _rows["NASDAQ"] = counts
        except Exception:
            pass  # keep the last good count; the next cycle retries
        time.sleep(NASDAQ_POLL_SEC)


def _poll_twse():
    while True:
        try:
            r = requests.get("https://www.twse.com.tw/rwd/en/afterTrading/MI_INDEX",
                             params={"type": "MS", "response": "json"}, headers=_HEADERS, timeout=20)
            r.raise_for_status()
            d = r.json()
            counts = parse_twse(d)
            if counts:
                with _lock:
                    _rows["TAIEX"] = {**counts, "asOf": d.get("date")}
        except Exception:
            pass
        time.sleep(TWSE_POLL_SEC)


def _poll_sse():
    while True:
        try:
            counts = sse_breadth()
            if counts:
                with _lock:
                    _rows["SSE"] = counts
        except Exception:
            pass
        time.sleep(SSE_POLL_SEC)


def start():
    threading.Thread(target=_poll_nasdaq, daemon=True, name="breadth-nasdaq").start()
    threading.Thread(target=_poll_twse, daemon=True, name="breadth-twse").start()
    threading.Thread(target=_poll_sse, daemon=True, name="breadth-sse").start()


def breadth_rows():
    with _lock:
        return [{"alias": alias, **data} for alias, data in _rows.items()]
