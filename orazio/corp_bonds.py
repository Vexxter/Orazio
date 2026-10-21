"""Corporate bonds listed on NSE's capital-market segment (NCDs, PSU and bank bonds; ~570 issues), from NSE's
own `liveBonds-traded-on-cm?type=bonds` — the call nseindia.com's "Bonds traded in CM" page makes. Each row:
symbol, ISIN, series, coupon, maturity, credit rating + agency, OHLC, % change, quantity and traded value (₹).

NSE's yield field (`bYield`) is 0 for most issues, so an approximate yield to maturity is worked out here
from the last price, coupon, face value and maturity.
ponytail: annual coupons on the maturity date's anniversary, simple accrued interest, no call dates — good to
~10-30 bp for ordinary NCDs; wrong for zero-coupon/step-up/callable issues. Upgrade: per-issue coupon dates and
frequency from NSE's bond master (`nxtip_date` is usually "-") if the yield needs to be exact.
"""
from datetime import date, datetime

from .cache import cached
from .nse_client import nse_get

TTL = 15


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def approx_ytm(price, coupon_pct, face, maturity, today):
    """Yield (%) that prices annual coupons + face at maturity to `price`, by bisection. None if it can't."""
    if not price or price <= 0 or not face or not maturity or maturity <= today or coupon_pct is None:
        return None
    years = (maturity - today).days / 365.25
    coupon = face * coupon_pct / 100
    times = [years - k for k in range(int(years) + 1) if years - k > 0]
    # NSE quotes the clean price; the cash flows are worth the dirty one = clean + interest accrued since the
    # last coupon (a year's coupon times the part of the year already gone).
    dirty = price + coupon * (1 - min(times))

    def pv(y):
        return sum(coupon / (1 + y) ** t for t in times) + face / (1 + y) ** years

    price = dirty
    lo, hi = -0.5, 2.0
    if not pv(hi) <= price <= pv(lo):
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if pv(mid) > price else (lo, mid)
    return round((lo + hi) / 2 * 100, 2)


def _maturity(s):
    try:
        return datetime.strptime(s, "%d-%b-%Y").date()
    except (TypeError, ValueError):
        return None


def corp_row(r, today):
    ltp = _num(r.get("ltP"))
    face = _num(r.get("face_value"))
    coupon = _num(r.get("coupr"))
    mat = _maturity(r.get("maturity_date"))
    nse_yield = _num(r.get("bYield"))
    rating = (r.get("credit_rating") or "").split(",")[0].strip().rstrip("/") or None
    traded = _num(r.get("trdVal")) or 0.0
    return {
        "symbol": r.get("symbol"),
        "isin": r.get("isin"),
        "series": r.get("series"),
        "rating": rating,
        "agency": r.get("rating_agency"),
        "coupon": coupon,
        "maturity": mat.isoformat() if mat else None,
        "ltPrice": ltp if traded else None,
        "pChange": _num(r.get("per")) if traded else None,
        "face": face,
        "ytm": nse_yield if nse_yield else (approx_ytm(ltp, coupon, face, mat, today) if traded else None),
        "ytmApprox": not nse_yield,
        "tradedLakh": round(traded / 1e5, 2),
    }


def _fetch():
    today = date.today()
    rows = [corp_row(r, today) for r in (nse_get("/api/liveBonds-traded-on-cm", {"type": "bonds"}) or {}).get("data") or []
            if isinstance(r, dict) and r.get("symbol")]
    rows.sort(key=lambda x: -x["tradedLakh"])
    return {"available": bool(rows), "open": None, "rows": rows}


def corporate():
    try:
        return {"segment": "corp", **cached(("bonds", "corp"), TTL, _fetch)}
    except Exception:
        return {"segment": "corp", "available": False, "open": None, "rows": []}
