"""Implied-volatility history, recorded locally, so IV rank and IV percentile can say whether options are cheap or dear.

NSE publishes no IV history, so Orazio keeps its own: IV30 (ATM IV interpolated to 30 calendar days from the term
structure options_analytics already builds) per underlying per day, in ~/.orazio/iv_history.json. A day is written
whenever the Options tab is open, and every 30 minutes in market hours for the index underlyings while the app runs.
The newest reading of a day replaces earlier ones, so each day ends on its last reading.

ponytail: history starts the day you first run this; rank needs MIN_DAYS of it. NIFTY gets India VIX's year of
history in the page meanwhile. A backfill would need an archive of past option chains (NSE bhavcopy has prices, not IV).
"""
import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from .constants import IST

FILE = Path.home() / ".orazio" / "iv_history.json"
KEEP_DAYS = 400
MIN_DAYS = 20
LOOKBACK = 252
TARGET_DAYS = 30
INDICES = ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY")
RECORD_EVERY_SEC = 1800
_lock = threading.Lock()
_started = False
log = logging.getLogger(__name__)


def iv30(term):
    """ATM IV at 30 days, linear in days between the expiries either side; the nearest expiry's IV outside them."""
    pts = sorted((t["days"], t["atmIv"]) for t in term or [] if t.get("atmIv"))
    if not pts:
        return None
    if TARGET_DAYS <= pts[0][0]:
        return pts[0][1]
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        if d0 <= TARGET_DAYS <= d1:
            return round(v0 + (v1 - v0) * (TARGET_DAYS - d0) / (d1 - d0), 2) if d1 > d0 else v0
    return pts[-1][1]


def _load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def record(underlying, value, day):
    """Stores today's reading for one underlying (replacing an earlier one from the same day)."""
    if not value or value <= 0:
        return
    with _lock:
        d = _load()
        days = d.setdefault(underlying, {})
        if days.get(day) == value:
            return
        days[day] = value
        for old in sorted(days)[:-KEEP_DAYS]:
            del days[old]
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, FILE)


def stats(values, current):
    """IV rank (where today sits between the period's low and high, 0–100) and IV percentile (share of days below
    today), over the last LOOKBACK readings. None until there are MIN_DAYS of them."""
    vals = [v for v in values[-LOOKBACK:] if v]
    if current is None or len(vals) < MIN_DAYS:
        return {"days": len(vals), "rank": None, "percentile": None, "low": None, "high": None}
    lo, hi = min(vals), max(vals)
    return {"days": len(vals), "rank": round((current - lo) / (hi - lo) * 100, 1) if hi > lo else 50.0,
            "percentile": round(sum(v < current for v in vals) / len(vals) * 100, 1), "low": lo, "high": hi}


def summary(underlying, term, now=None):
    """Records today's IV30 and returns it with its history and rank."""
    now = now or datetime.now(IST)
    cur = iv30(term)
    if cur:
        try:
            record(underlying, cur, now.date().isoformat())
        except OSError:
            log.warning("could not write %s", FILE)
    days = _load().get(underlying, {})
    hist = [{"date": k, "iv": days[k]} for k in sorted(days)]
    return {"iv30": cur, "history": hist[-LOOKBACK:], **stats([h["iv"] for h in hist], cur)}


def market_open(now):
    return now.weekday() < 5 and (9, 20) <= (now.hour, now.minute) <= (15, 30)


def start():
    """Records the index underlyings every 30 minutes in market hours, so their history builds without the tab open."""
    global _started
    if _started:
        return
    _started = True
    from . import options_analytics   # local: it imports this module

    def loop():
        while True:
            if market_open(datetime.now(IST)):
                for u in INDICES:
                    try:
                        options_analytics.analytics(u)
                    except Exception:   # noqa: BLE001 — one bad chain must not stop the recorder
                        log.exception("IV record failed for %s", u)
            time.sleep(RECORD_EVERY_SEC)

    threading.Thread(target=loop, daemon=True, name="iv-recorder").start()
