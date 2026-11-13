"""Market-implied policy-rate path (Bloomberg's WIRP, on public data), for the Fed and RBI.

Bloomberg reads fed funds futures and OIS. Neither is free, so this reads the bill curve instead: the forward rate
between two bill maturities is what the market expects the short rate to average over that window, plus a small
term/liquidity premium. Compared with today's overnight anchor, the gap is the move priced in.

* US: 1M/3M/6M/1Y Treasury bill yields (CNBC, via bonds.py); anchor = the fed funds target midpoint (FRED
  DFEDTARL/DFEDTARU, public CSV, no key).
* India: T-bill yields by days to maturity (CCIL NDS-OM, via gsec.py), interpolated to 1/3/6/12 months; anchor =
  the latest TREPS weighted rate (RBI money-market release, via macro.py), the overnight rate RBI steers. Moves are
  measured from the shortest bill, since bills sit a structural spread off TREPS.
ponytail: horizons, not meeting-by-meeting probabilities (that needs a meeting calendar per bank and futures data).
Bills price a little away from OIS (US bills usually a few bp above/below; Indian bills carry supply effects), so read
moves under ~10 bp as "nothing priced".
"""
import csv
import io
from datetime import date, datetime, timedelta

import requests

from . import bonds, gsec, macro
from .cache import cached

TTL = 300
HORIZONS = ((1, "1M"), (3, "3M"), (6, "6M"), (12, "12M"))   # months
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
STEP_BP = 25
BASIS_MAX_YEARS = 45 / 365
MIN_BILLS = 3
RECORDED_DAYS = 7
US_BILLS = {"US1M": 1 / 12, "US3M": 0.25, "US6M": 0.5, "US1Y": 1.0}


def interpolate(points, t):
    """Linear yield at time t (years) from [(t, y)] sorted by t; flat beyond the ends."""
    if not points:
        return None
    if t <= points[0][0]:
        return points[0][1]
    for (t0, y0), (t1, y1) in zip(points, points[1:]):
        if t0 <= t <= t1:
            return y0 + (y1 - y0) * (t - t0) / (t1 - t0) if t1 > t0 else y0
    return points[-1][1]


def path(points, anchor, always_basis=False):
    """Bill curve [(t years, yield %)] + overnight anchor % -> forward windows and the move each prices in."""
    pts = sorted((t, y) for t, y in points if y is not None and t > 0)
    if not pts or anchor is None:
        return None
    # Bills sit a steady few bp off the policy rate (supply, tax, bill-OIS basis). When the curve reaches down to about
    # a month, that gap is measured there (assuming no move inside a month) and taken out of every window.
    basis = pts[0][1] - anchor if always_basis or pts[0][0] <= BASIS_MAX_YEARS else 0.0
    out, prev_t, prev_y, prev_label = [], 0.0, anchor, "now"
    for months, label in HORIZONS:
        t = months / 12
        y = interpolate(pts, t)
        fwd = (y * t - prev_y * prev_t) / (t - prev_t)
        out.append({"label": f"{prev_label}–{label}", "months": months, "billYield": round(y, 3),
                    "forward": round(fwd, 3), "vsAnchorBp": round((fwd - anchor - basis) * 100, 1)})
        prev_t, prev_y, prev_label = t, y, label
    last = out[-1]["vsAnchorBp"]
    return {"anchor": anchor, "basisBp": round(basis * 100, 1), "windows": out, "steps12m": round(last / STEP_BP, 1),
            "verdict": "no change priced" if abs(last) < 10 else f"{abs(last):.0f} bp of {'hikes' if last > 0 else 'cuts'} priced over 12 months"}


def _fred_last(series):
    r = requests.get(FRED.format(series), timeout=15)
    rows = [row for row in csv.reader(io.StringIO(r.text)) if len(row) == 2]
    for d, v in reversed(rows[1:]):
        try:
            return d, float(v)
        except ValueError:
            continue
    return None, None


def us():
    def fetch():
        day, lo = _fred_last("DFEDTARL")
        _, hi = _fred_last("DFEDTARU")
        q = {r["tenor"]: r["yield"] for r in bonds._quotes(list(US_BILLS))}
        anchor = (lo + hi) / 2 if lo is not None and hi is not None else None
        p = path([(t, q.get(tenor)) for tenor, t in ((k[2:], v) for k, v in US_BILLS.items())], anchor)
        return {"available": bool(p), "bank": "Fed", "anchorName": f"Fed funds target midpoint ({lo:.2f}–{hi:.2f}%, {day})" if anchor else None, **(p or {})}
    try:
        return cached(("rate-path", "us"), TTL, fetch)
    except Exception:   # noqa: BLE001 — a dead source shows as unavailable, not a 500
        return {"available": False, "bank": "Fed"}


def tbill_points(rows, today):
    """CCIL T-bill rows -> [(years to maturity, yield %)]: last traded yield, else the bid/offer middle. One-sided quotes
    are skipped: before the day's first trades only offers are up, and they sit well above fair."""
    out = []
    for r in rows:
        bid, ask = r.get("bidYield"), r.get("askYield")
        y = r.get("ltYield") or ((bid + ask) / 2 if bid and ask else None)
        if not y or not r.get("maturity"):
            continue
        days = (date.fromisoformat(r["maturity"]) - today).days
        if days > 0:
            out.append((days / 365, y))
    return sorted(out)


def recorded_bills(today, days_back=RECORDED_DAYS):
    """Last traded yield per T-bill from gsec.py's own trade recorder (~/.orazio/gsec_ticks), newest day first, as
    rows tbill_points() reads. Bills trade thinly in the morning; yesterday's last trade beats no point at all."""
    out = {}
    for back in range(days_back + 1):
        day = (today - timedelta(days=back)).isoformat()
        for cid, ticks in gsec._load_day(day).items():
            if "_DTB_" not in cid or cid in out or not ticks:
                continue
            try:
                mat = datetime.strptime(cid.rsplit("_", 1)[1], "%d%m%Y").date().isoformat()
            except ValueError:
                continue
            out[cid] = {"id": cid, "maturity": mat, "ltYield": ticks[-1][1], "day": day}
    return out


def india(today=None):
    today = today or date.today()

    def fetch():
        live = [r for r in gsec.segment("tbill").get("rows") or [] if tbill_points([r], today)]
        priced = {r["id"] for r in live}
        older = [r for cid, r in recorded_bills(today).items() if cid not in priced]   # incl. today's earlier trades
        rows = live + older
        liq = macro.liquidity() or []
        last = next((x for x in reversed(liq) if x.get("treps")), None)
        anchor = last["treps"] if last else None
        pts = tbill_points(rows, today)
        if len(pts) < MIN_BILLS:
            return {"available": False, "bank": "RBI", "reason": f"Waiting for T-bill trades on CCIL ({len(pts)} of {MIN_BILLS} bills priced). Bills trade from about 9:30 IST."}
        # Indian bills sit tens of bp off TREPS for structural reasons and the shortest bill is often ~2-3 months out,
        # so moves are read relative to the shortest bill: what the curve prices beyond it.
        p = path(pts, anchor, always_basis=True)
        return {"available": bool(p), "bank": "RBI", "anchorName": f"TREPS weighted rate ({last['date']}); moves measured from the shortest bill" if last else None,
                "olderBills": len(older), **(p or {})}
    try:
        return cached(("rate-path", "in", today.isoformat()), TTL, fetch)
    except Exception:   # noqa: BLE001
        return {"available": False, "bank": "RBI"}


def payload():
    return {"banks": [india(), us()]}
