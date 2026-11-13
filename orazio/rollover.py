"""Futures rollover from NSE's daily F&O bhavcopy (the same per-day cache fno.py keeps for futures charts).

Rollover % on a day = open interest in the later expiries / total futures OI for that underlying. It climbs
through expiry week as positions move to the next month; desks compare it with the previous series at the same
number of sessions before expiry, so this lines both series up that way. Roll spread = next-month close /
near-month close - 1 (the cost of carrying a long position one more month).
"""
from datetime import datetime, timedelta

from . import fno
from .cache import cached
from .constants import IST

CALENDAR_DAYS = 75
SERIES_SYMBOLS = ("NIFTY", "BANKNIFTY")


def day_stats(rows, day):
    """One bhavcopy day -> {symbol: {near, rollPct, spreadPct}} (near = earliest expiry not before `day`)."""
    by = {}
    for sym, exp, _o, _h, _l, close, oi, _v in rows:
        if exp >= day:
            by.setdefault(sym, []).append((exp, close, oi))
    out = {}
    for sym, cs in by.items():
        cs.sort()
        total = sum(c[2] for c in cs)
        if not total or len(cs) < 2:
            continue
        near, nxt = cs[0], cs[1]
        out[sym] = {"near": near[0], "rollPct": round((1 - near[2] / total) * 100, 2),
                    "spreadPct": round((nxt[1] / near[1] - 1) * 100, 3) if near[1] else None}
    return out


def build(days):
    """days: {iso date: rows} -> {symbol: {near expiry: [day stats, oldest first]}}."""
    per = {}
    for day in sorted(days):
        for sym, s in day_stats(days[day], day).items():
            per.setdefault(sym, {}).setdefault(s["near"], []).append({"date": day, **s})
    return per


def sessions_left(day, expiry):
    """Weekdays after `day` up to and including `expiry` (ponytail: ignores exchange holidays, off by one in a holiday week)."""
    d, e = datetime.fromisoformat(day).date(), datetime.fromisoformat(expiry).date()
    return sum(1 for i in range(1, (e - d).days + 1) if (d + timedelta(days=i)).weekday() < 5)


def same_point(prev_pts, left):
    """The previous series' value `left` sessions before its expiry (its last point is expiry day itself)."""
    i = len(prev_pts) - 1 - left
    return prev_pts[i] if 0 <= i < len(prev_pts) else None


def rollover():
    def fetch():
        today = datetime.now(IST).date()
        cal = [today - timedelta(days=i) for i in range(CALENDAR_DAYS) if (today - timedelta(days=i)).weekday() < 5]
        got = fno._ensure_days(cal)
        days = {d.isoformat(): rows for d, rows in got.items() if rows}
        if not days:
            return {"available": False}
        latest = max(days)
        per = build(days)
        out_rows, series = [], {}
        for sym, by_exp in per.items():
            exps = sorted(by_exp)
            cur = next((e for e in exps if by_exp[e][-1]["date"] == latest), None)
            if not cur:
                continue
            prev = [e for e in exps if e < cur]
            now_pts = by_exp[cur]
            left = sessions_left(latest, cur)
            prev_pts = by_exp[prev[-1]] if prev else []
            then = same_point(prev_pts, left)
            row = {"symbol": sym, "expiry": cur, "sessionsLeft": left, **{k: now_pts[-1][k] for k in ("rollPct", "spreadPct")},
                   "prevRollPct": then["rollPct"] if then else None,
                   "prevFinalPct": prev_pts[-1]["rollPct"] if prev_pts else None}
            out_rows.append(row)
            if sym in SERIES_SYMBOLS:
                series[sym] = {"current": [p["rollPct"] for p in now_pts], "previous": [p["rollPct"] for p in prev_pts],
                               "currentExpiry": cur, "previousExpiry": prev[-1] if prev else None, "sessionsLeft": left}
        return {"available": True, "date": latest, "rows": out_rows, "series": series}
    return cached(("rollover",), 600, fetch)
