"""End-of-day option strategy backtest from NSE's daily F&O bhavcopy.

Enter each expiry N sessions before it at the day's close, hold to expiry, settle at intrinsic value against the
underlying's close that day (the file's SttlmPric on an option row is the underlying's price, so it isn't used). Strikes
are picked by distance from the at-the-money strike on entry day. Lot size comes from that day's own file, so a change
in lot size can't misstate old trades, and expiries come from the data, so the move from Thursday to Tuesday is handled.

Costs are on by default and every rate is editable. The defaults are the rates reported from 1 April 2026; older
trades are charged at the same rates, so they read a little worse than they were.

Limits, shown with every result: closing prices only, so no intraday entries or stops; a contract that didn't trade on
entry day has no real price, so that expiry is skipped and counted rather than filled at a made-up number. History
starts when NSE's current file format does (July 2024). ponytail: holds to expiry only; add exits once wanted.
"""
import gzip
import io
import json
import zipfile
from concurrent.futures import wait
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from . import fno
from .constants import IST
from .http_clients import nse_http

CACHE_DIR = Path.home() / ".orazio" / "opt_cache"
COLS = ["FinInstrmTp", "TckrSymb", "XpryDt", "StrkPric", "OptnTp", "ClsPric", "UndrlygPric", "NewBrdLotQty", "TtlTradgVol"]
FIRST_DAY = date(2024, 7, 8)
BUDGET_SEC = 25
MAX_LEGS = 6
DEFAULT_COSTS = {
    "brokeragePerOrder": 20.0,     # ₹ per leg, each way
    "sttSellPct": 0.15,            # on premium sold
    "sttExercisePct": 0.15,        # on intrinsic value of a long option that finishes in the money
    "exchangePct": 0.0355,         # exchange transaction charge, on premium
    "sebiPct": 0.0001,             # SEBI fee, on premium
    "stampBuyPct": 0.003,          # stamp duty, on premium bought
    "gstPct": 18.0,                # on brokerage + exchange + SEBI
    "slippagePct": 0.5,            # assumed cost of crossing the spread, % of premium each trade
}


# ---------- data ----------
def parse(content, underlying):
    """A bhavcopy zip -> [[type, expiry, strike, close, spot, lot, volume], ...] for one underlying's options."""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]), usecols=COLS)
    df = df[df["FinInstrmTp"].isin(["IDO", "STO"]) & (df["TckrSymb"] == underlying)]
    return [[r.OptnTp, r.XpryDt, float(r.StrkPric), float(r.ClsPric), float(r.UndrlygPric), int(r.NewBrdLotQty), int(r.TtlTradgVol)]
            for r in df.itertuples()]


def _path(underlying, d):
    return CACHE_DIR / underlying / f"{d:%Y%m%d}.json.gz"


def _read(underlying, d):
    try:
        with gzip.open(_path(underlying, d), "rt", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, EOFError):
        return None


def _write(underlying, d, rows):
    p = _path(underlying, d)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump(rows, f)


def _fetch(underlying, d):
    """One day's rows; [] for a day that long ago turned out to be a holiday; None if not available yet."""
    rows = _read(underlying, d)
    if rows is not None:
        return rows
    try:
        r = nse_http.get(fno.ARCHIVE_URL.format(day=f"{d:%Y%m%d}"), timeout=40)
    except OSError:
        return None
    if r.status_code == 404:
        if d < datetime.now(IST).date() - timedelta(days=3):
            _write(underlying, d, [])
            return []
        return None
    if r.status_code != 200 or r.content[:2] != b"PK":
        return None
    try:
        rows = parse(r.content, underlying)
    except (ValueError, KeyError, zipfile.BadZipFile):
        return None
    _write(underlying, d, rows)
    return rows


def load_days(underlying, days):
    """{day: rows}, and how many are still downloading. Those keep going in the background and are ready next time."""
    got, pending = {}, {}
    for d in days:
        rows = _read(underlying, d)
        if rows is not None:
            got[d] = rows
        else:
            pending[d] = fno._pool.submit(_fetch, underlying, d)
    if pending:
        wait(pending.values(), timeout=BUDGET_SEC)
    missing = 0
    for d, job in pending.items():
        rows = job.result() if job.done() else None
        if rows is None:
            missing += 1 if not job.done() else 0
        else:
            got[d] = rows
    return {d: r for d, r in got.items() if r}, missing


# ---------- pure ----------
def parse_legs(text):
    """'SELL CE 0, BUY PE -2' -> legs. Offsets count strikes from the at-the-money one, up being positive."""
    legs = []
    for part in (text or "").split(","):
        bits = part.split()
        if not bits:
            continue
        if len(bits) != 3 or bits[0].upper() not in ("BUY", "SELL") or bits[1].upper() not in ("CE", "PE"):
            raise ValueError(f"Can't read leg “{part.strip()}”. Write it like: SELL CE 0")
        try:
            offset = int(bits[2])
        except ValueError:
            raise ValueError(f"Strike offset must be a whole number in “{part.strip()}”") from None
        legs.append({"side": bits[0].upper(), "type": bits[1].upper(), "offset": offset})
    if not 1 <= len(legs) <= MAX_LEGS:
        raise ValueError(f"Give 1 to {MAX_LEGS} legs")
    return legs


def expiries_in(days, kind):
    """The expiries that both trade in `days` and were reached in them. Monthly = the last expiry of each calendar month."""
    seen = sorted({r[1] for rows in days.values() for r in rows})
    have = {d.isoformat() for d in days}
    reached = [e for e in seen if e in have]
    if kind != "monthly":
        return reached
    # The last expiry listed for a month can be later than any session we've loaded, so decide from all that are listed.
    last = {}
    for e in seen:
        last[e[:7]] = e
    return [e for e in reached if last[e[:7]] == e]


def leg_costs(side, premium_value, intrinsic_value, c):
    """₹ cost of one leg held to expiry: on the premium going in, plus STT if a long leg finishes in the money."""
    brokerage = c["brokeragePerOrder"]
    exchange = premium_value * c["exchangePct"] / 100
    sebi = premium_value * c["sebiPct"] / 100
    gst = (brokerage + exchange + sebi) * c["gstPct"] / 100
    tax = premium_value * c["sttSellPct"] / 100 if side == "SELL" else premium_value * c["stampBuyPct"] / 100 + intrinsic_value * c["sttExercisePct"] / 100
    slip = premium_value * c["slippagePct"] / 100
    return brokerage + exchange + sebi + gst + tax + slip


def run_trade(entry_rows, expiry_rows, expiry, legs, lots, costs):
    """One expiry -> a trade dict, or {"skip": reason}."""
    book = [r for r in entry_rows if r[1] == expiry]
    if not book:
        return {"skip": "no contracts on entry day"}
    spot = book[0][4]
    strikes = sorted({r[2] for r in book})
    if len(strikes) < 2 or not spot:
        return {"skip": "no strike ladder"}
    atm = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
    final_spot = next((r[4] for r in expiry_rows if r[1] == expiry), None)
    if final_spot is None:
        return {"skip": "no settlement data"}
    quotes = {(r[0], r[2]): r for r in book}
    gross = cost = 0.0
    shown = []
    for leg in legs:
        i = atm + leg["offset"]
        if not 0 <= i < len(strikes):
            return {"skip": "strike not listed"}
        q = quotes.get((leg["type"], strikes[i]))
        if q is None or q[6] <= 0 or q[3] <= 0:
            return {"skip": "a leg didn't trade on entry day"}
        qty = q[5] * lots
        intrinsic = max(final_spot - strikes[i], 0) if leg["type"] == "CE" else max(strikes[i] - final_spot, 0)
        sign = 1 if leg["side"] == "BUY" else -1
        gross += sign * (intrinsic - q[3]) * qty
        cost += leg_costs(leg["side"], q[3] * qty, intrinsic * qty, costs)
        shown.append({**leg, "strike": strikes[i], "entry": q[3], "settle": round(intrinsic, 2), "qty": qty})
    return {"expiry": expiry, "spot": spot, "finalSpot": final_spot, "legs": shown, "gross": round(gross, 2), "costs": round(cost, 2), "net": round(gross - cost, 2)}


def summarize(trades):
    nets = [t["net"] for t in trades]
    if not nets:
        return {"trades": 0}
    equity = peak = worst_dd = 0.0
    for n in nets:
        equity += n
        peak = max(peak, equity)
        worst_dd = min(worst_dd, equity - peak)
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n <= 0]
    return {"trades": len(nets), "netPnl": round(sum(nets), 2), "grossPnl": round(sum(t["gross"] for t in trades), 2), "costs": round(sum(t["costs"] for t in trades), 2),
            "winRate": round(len(wins) / len(nets) * 100, 1), "avgWin": round(sum(wins) / len(wins), 2) if wins else None, "avgLoss": round(sum(losses) / len(losses), 2) if losses else None,
            "worstTrade": min(nets), "bestTrade": max(nets), "maxDrawdown": round(worst_dd, 2)}


def backtest(days, legs, kind="weekly", entry=1, lots=1, costs=None):
    """days: {date: rows}. `entry` is how many sessions before expiry to enter; 0 means the expiry day's own close is
    both entry and exit, so it's refused."""
    costs = {**DEFAULT_COSTS, **(costs or {})}
    order = sorted(days)
    index = {d.isoformat(): i for i, d in enumerate(order)}
    trades, skipped = [], []
    for e in expiries_in(days, kind):
        i = index[e] - entry
        if i < 0:
            skipped.append({"expiry": e, "reason": "entry day is before the data starts"})
            continue
        t = run_trade(days[order[i]], days[order[index[e]]], e, legs, lots, costs)
        if "skip" in t:
            skipped.append({"expiry": e, "reason": t["skip"]})
        else:
            trades.append({**t, "entered": order[i].isoformat()})
    return {"summary": summarize(trades), "trades": trades, "skipped": skipped, "costs": costs}


# ---------- entry point ----------
def _int(raw, default, low, high, name):
    if raw in (None, ""):
        return default
    try:
        v = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a whole number") from None
    if not low <= v <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return v


def run(args):
    underlying = (args.get("underlying") or "").upper().split(".")[0]
    if not underlying.replace("-", "").replace("&", "").isalnum():
        raise ValueError("Enter an NSE F&O underlying, like NIFTY")
    legs = parse_legs(args.get("legs"))
    kind = args.get("expiry") or "weekly"
    if kind not in ("weekly", "monthly"):
        raise ValueError("Expiry must be weekly or monthly")
    entry = _int(args.get("entry"), 1, 1, 15, "Sessions before expiry")
    months = _int(args.get("months"), 3, 1, 24, "Months")
    lots = _int(args.get("lots"), 1, 1, 1000, "Lots")
    costs = {}
    for k in DEFAULT_COSTS:
        if args.get(k) not in (None, ""):
            try:
                costs[k] = float(args.get(k))
            except (TypeError, ValueError):
                raise ValueError(f"{k} must be a number") from None
            if not 0 <= costs[k] < 100000:
                raise ValueError(f"{k} is out of range")
    today = datetime.now(IST).date()
    start = max(FIRST_DAY, today - timedelta(days=months * 31))
    cal = [start + timedelta(days=i) for i in range((today - start).days + 1)]
    days, downloading = load_days(underlying, [d for d in cal if d.weekday() < 5])
    if not days:
        return {"available": downloading > 0, "underlying": underlying, "downloading": downloading, "summary": {"trades": 0}, "trades": [], "skipped": [],
                "note": "Still downloading NSE's daily files. Run it again in a minute." if downloading else f"No option data found for {underlying}."}
    result = backtest(days, legs, kind, entry, lots, costs)
    return {"available": True, "underlying": underlying, "asOf": max(days).isoformat(), "from": min(days).isoformat(), "downloading": downloading,
            "request": {"legs": legs, "expiry": kind, "entry": entry, "lots": lots}, **result,
            "limits": "End-of-day closes only, held to expiry: no intraday entries or stops. An expiry is skipped when a leg didn't trade on entry day. Past results, not a forecast."}
