"""Options analytics on top of NSE's option chain (fno.chain): dealer gamma exposure (GEX) by strike and the
zero-gamma "flip" level, the IV smile for one expiry, the ATM IV term structure across expiries, and the day's
OI change by strike.

GEX convention (the common SpotGamma one): dealers are assumed long the calls and short the puts the public
holds, so call gamma counts positive and put gamma negative. Per strike:
    gamma(S, K, iv, T) x OI (contracts) x lot size x S^2 x 1%      -> rupees per 1% move in the underlying
Positive total GEX = dealers hedge against the move (dampens it); negative = they chase it (amplifies it).
ponytail: rate r = 0 and NSE's own per-strike IV; good enough for the shape and the flip level, not for pricing.
"""
import math
from datetime import datetime

from . import fno
from .cache import cached
from .constants import IST

EXPIRY_HOUR = (15, 30)
TERM_EXPIRIES = 6


def years_to(expiry, now):
    """'03-Nov-2026' -> years until 15:30 IST that day (floored at one hour, so expiry day stays finite)."""
    d = datetime.strptime(expiry, "%d-%b-%Y").replace(hour=EXPIRY_HOUR[0], minute=EXPIRY_HOUR[1], tzinfo=IST)
    return max((d - now).total_seconds(), 3600) / (365 * 86400)


def bs_gamma(s, k, iv, t):
    if not (s and k and iv and t) or iv <= 0:
        return 0.0
    vol = iv / 100
    d1 = (math.log(s / k) + 0.5 * vol * vol * t) / (vol * math.sqrt(t))
    return math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi) / (s * vol * math.sqrt(t))


def _iv(side):
    return (side or {}).get("iv") or None


def strike_gex(row, spot, t, lot):
    """(call GEX, put GEX) at this strike in ₹ per 1% move; put GEX is negative."""
    unit = lot * spot * spot * 0.01
    ce, pe = row.get("ce") or {}, row.get("pe") or {}
    c = bs_gamma(spot, row["strike"], _iv(ce), t) * (ce.get("oi") or 0) * unit
    p = -bs_gamma(spot, row["strike"], _iv(pe), t) * (pe.get("oi") or 0) * unit
    return c, p


def total_gex(rows, spot, t, lot):
    return sum(sum(strike_gex(r, spot, t, lot)) for r in rows)


def flip_level(rows, spot, t, lot, width=0.06, steps=60):
    """Spot at which total GEX changes sign, searched within ±width of spot (IVs held fixed); None if no flip."""
    grid = [spot * (1 - width + 2 * width * i / steps) for i in range(steps + 1)]
    vals = [total_gex(rows, s, t, lot) for s in grid]
    best = None
    for (s0, v0), (s1, v1) in zip(zip(grid, vals), zip(grid[1:], vals[1:])):
        if v0 == 0 or (v0 < 0) != (v1 < 0):
            x = s0 if v0 == 0 else s0 + (s1 - s0) * (-v0) / (v1 - v0)
            if best is None or abs(x - spot) < abs(best - spot):
                best = x
    return round(best, 2) if best is not None else None


def smile(rows, spot):
    """OTM IV by strike: puts below spot, calls at/above (the side that trades)."""
    out = []
    for r in rows:
        iv = _iv(r.get("ce")) if r["strike"] >= spot else _iv(r.get("pe"))
        if iv:
            out.append({"strike": r["strike"], "iv": iv})
    return out


def atm_iv(rows, spot):
    near = sorted((r for r in rows if _iv(r.get("ce")) or _iv(r.get("pe"))), key=lambda r: abs(r["strike"] - spot))[:2]
    ivs = [v for r in near for v in (_iv(r.get("ce")), _iv(r.get("pe"))) if v]
    return round(sum(ivs) / len(ivs), 2) if ivs else None


def analytics(symbol, expiry=None, now=None):
    now = now or datetime.now(IST)
    res = fno.resolve(symbol)
    if not res or res["underlying"] in fno.BSE_UNDERLYINGS:
        return {"available": False, "symbol": symbol, "reason": "No NSE option chain for this symbol."}
    ch = fno.chain(res, expiry)
    if not ch or not ch.get("rows") or not ch.get("spot"):
        return {"available": False, "symbol": symbol, "reason": "NSE's option chain is unavailable right now."}
    lot = fno.lot_size(res["underlying"]) or 1
    spot, rows, t = ch["spot"], ch["rows"], years_to(ch["expiry"], now)
    # Strikes within ±12% of spot: the far wings carry no gamma and only squash the chart.
    rows = [r for r in rows if abs(r["strike"] / spot - 1) <= 0.12]
    per = []
    for r in rows:
        c, p = strike_gex(r, spot, t, lot)
        per.append({"strike": r["strike"], "callGex": c / 1e7, "putGex": p / 1e7,
                    "ceDoi": (r.get("ce") or {}).get("dOi"), "peDoi": (r.get("pe") or {}).get("dOi"),
                    "ceOi": (r.get("ce") or {}).get("oi"), "peOi": (r.get("pe") or {}).get("oi")})
    net = sum(x["callGex"] + x["putGex"] for x in per)
    call_wall = max(per, key=lambda x: x["callGex"])["strike"] if per else None
    put_wall = min(per, key=lambda x: x["putGex"])["strike"] if per else None
    return {
        "available": True, "symbol": symbol, "underlying": res["underlying"], "expiry": ch["expiry"],
        "expiries": ch["expiries"], "asOf": ch.get("asOf"), "spot": spot, "lotSize": lot,
        "daysToExpiry": round(t * 365, 2), "netGexCr": round(net, 2), "flip": flip_level(rows, spot, t, lot),
        "callWall": call_wall, "putWall": put_wall, "maxPain": ch.get("maxPain"), "pcr": ch.get("pcr"),
        "atmIv": atm_iv(rows, spot), "strikes": per, "smile": smile(rows, spot),
        "term": term_structure(res, ch["expiries"], now),
    }


def term_structure(res, expiries, now):
    def fetch():
        out = []
        for e in expiries[:TERM_EXPIRIES]:
            ch = fno.chain(res, e)
            if ch and ch.get("rows") and ch.get("spot"):
                out.append({"expiry": e, "days": round(years_to(e, now) * 365, 1), "atmIv": atm_iv(ch["rows"], ch["spot"])})
        return out
    return cached(("iv-term", res["underlying"]), 120, fetch)
