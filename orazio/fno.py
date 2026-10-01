"""NSE Futures & Options: the F&O panel, and the futures price series behind the spot/futures toggle.

All of it is free and public — the same calls nseindia.com's own pages make (verified 30 Sep 2026):
  * getSymbolDerivativesData (GetQuoteApi): every contract for an underlying, futures with last
    price, OI, change in OI, volume, turnover, open/high/low.
  * option-chain-v3 + option-chain-contract-info: the option chain per expiry (OI, change in OI,
    volume, IV, LTP per strike).
  * chart-databyindex: today's tick chart of one contract, which we bucket into intraday bars.
  * The daily F&O bhavcopy archive (nsearchives.nseindia.com): full OHLC/settlement/OI/volume for
    every contract on a past date. Each day is parsed once and cached under ~/.orazio/fut_cache.

A futures chart symbol is "<UNDERLYING>-FUT" (NIFTY-FUT, RELIANCE-FUT) and always means the
front-month contract: the nearest expiry that hasn't passed. Daily history stitches each day's
front month together, rolling on expiry day, so it shows the roll gap like any continuous contract.
Intraday history exists for today only (NSE serves no older ticks); volume isn't in the tick feed.
"""
import io
import json
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .cache import cached
from .constants import IST, INTERVAL_SECONDS
from .http_clients import nse_http
from .nse_client import nse_get

QUOTE_API = "/api/NextApi/apiClient/GetQuoteApi"
CACHE_DIR = Path.home() / ".orazio" / "fut_cache"
ARCHIVE_URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{day}_F_0000.csv.zip"
DAILY_FETCH_BUDGET_SEC = 25
MAX_DAILY_CALENDAR_DAYS = 730
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="fut-archive")
_stock_cache = {"at": 0, "stocks": {}}
_stock_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Which symbols have F&O
# ---------------------------------------------------------------------------
def fno_stocks():
    """{NSE symbol: company name} for every stock with F&O contracts (~213). Kept for 6 h;
    a failed refresh keeps the last good list."""
    with _stock_lock:
        if time.time() - _stock_cache["at"] < 6 * 3600 and _stock_cache["stocks"]:
            return _stock_cache["stocks"]
    d = nse_get(QUOTE_API, {"functionName": "getSymbolDerivativesFilter", "isSymbolIndex": "S", "symbol": "RELIANCE"})
    try:
        stocks = {x["symbol"]: x.get("companyName") for x in d["symbol"]}
    except (KeyError, TypeError):
        return _stock_cache["stocks"]
    with _stock_lock:
        _stock_cache.update(at=time.time(), stocks=stocks)
    return stocks


def resolve(symbol):
    """Chart symbol (NIFTY, ^NSEI, RELIANCE.NS, RELIANCE-FUT ...) -> the F&O underlying, or None."""
    s = (symbol or "").upper()
    if s.endswith("-FUT"):
        s = s[:-4]
        as_future = True
    else:
        as_future = False
    if s in ("NIFTY", "^NSEI"):
        return {"underlying": "NIFTY", "kind": "index", "spot": "NIFTY", "fut": "NIFTY-FUT", "chainType": "Indices", "name": "NIFTY 50"}
    if s in ("BANKNIFTY", "^NSEBANK"):
        return {"underlying": "BANKNIFTY", "kind": "index", "spot": "BANKNIFTY", "fut": "BANKNIFTY-FUT", "chainType": "Indices", "name": "NIFTY BANK"}
    base = s[:-3] if s.endswith(".NS") else (s if as_future else None)
    stocks = fno_stocks()
    if base and base in stocks:
        return {"underlying": base, "kind": "stock", "spot": base + ".NS", "fut": base + "-FUT", "chainType": "Equity",
                "name": stocks[base] or base}
    return None


def spot_symbol(symbol):
    """The spot ticker behind a futures chart symbol, for spot-only features (news, names)."""
    res = resolve(symbol)
    return {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK"}.get(res["underlying"], res["spot"]) if res else symbol


# ---------------------------------------------------------------------------
# Live futures rows
# ---------------------------------------------------------------------------
def _expiry(s):
    return datetime.strptime(s, "%d-%b-%Y").date()


def _stamp(s):
    try:
        return int(datetime.strptime(s, "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST).timestamp())
    except (TypeError, ValueError):
        return int(time.time())


def derivatives(underlying):
    return cached(("fno-deriv", underlying), 2, lambda: nse_get(QUOTE_API, {"functionName": "getSymbolDerivativesData", "symbol": underlying}))


def _future_row(r, spot):
    last = r.get("lastPrice")
    prev = r.get("prevClose")
    change = r.get("change")
    return {
        "expiry": r.get("expiryDate"), "identifier": r.get("identifier"), "last": last, "change": change,
        "pChange": r.get("pchange", r.get("pChange")), "prevClose": prev, "open": r.get("openPrice"),
        "high": r.get("highPrice"), "low": r.get("lowPrice"), "oi": r.get("openInterest"),
        "dOi": r.get("changeinOpenInterest"), "dOiPct": r.get("pchangeinOpenInterest"),
        "volume": r.get("totalTradedVolume", r.get("volume")), "turnover": r.get("totalTurnover"),
        "basis": (last - spot) if (last is not None and spot) else None,
        "basisPct": ((last - spot) / spot * 100) if (last is not None and spot) else None,
    }


def futures(underlying):
    """(list of futures rows sorted by expiry, spot, data timestamp) — or (None, None, None)."""
    d = derivatives(underlying)
    if not d:
        return None, None, None
    rows = [r for r in d.get("data", []) if r.get("instrumentType") in ("FUTIDX", "FUTSTK") and r.get("expiryDate")]
    spot = next((r.get("underlyingValue") for r in rows if r.get("underlyingValue")), None)
    rows.sort(key=lambda r: _expiry(r["expiryDate"]))
    today = datetime.now(IST).date()
    rows = [r for r in rows if _expiry(r["expiryDate"]) >= today]
    return [_future_row(r, spot) for r in rows], spot, d.get("timestamp")


def quote(symbol):
    """Front-month futures quote in the shape market_data's other sources use."""
    res = resolve(symbol)
    if not res:
        return None
    rows, _spot, ts = futures(res["underlying"])
    if not rows or rows[0]["last"] is None:
        return None
    front = rows[0]
    prev = front["prevClose"] if front["prevClose"] else front["last"] - (front["change"] or 0)
    return {"price": float(front["last"]), "prevClose": float(prev), "marketTime": _stamp(ts), "currency": "INR"}


# ---------------------------------------------------------------------------
# Intraday bars (today) from the contract's tick chart
# ---------------------------------------------------------------------------
def _ticks(identifier):
    def fetch():
        d = nse_get("/api/chart-databyindex", {"index": identifier, "indices": "false"})
        return (d or {}).get("grapthData") or []  # NSE's own spelling
    return cached(("fno-ticks", identifier), 5, fetch)


def intraday_bars(underlying, step):
    rows, _spot, _ts = futures(underlying)
    if not rows:
        return []
    buckets = {}
    for ms, price in _ticks(rows[0]["identifier"]):
        # NSE stamps these in "IST as if it were UTC" — shift back to a real epoch.
        t = int(ms / 1000) - 19800
        slot = t // step * step
        b = buckets.get(slot)
        if b is None:
            buckets[slot] = [price, price, price, price]
        else:
            b[1], b[2], b[3] = max(b[1], price), min(b[2], price), price
    return [{"time": t, "open": o, "high": h, "low": l, "close": c, "volume": 0} for t, (o, h, l, c) in sorted(buckets.items())]


# ---------------------------------------------------------------------------
# Daily history from the F&O bhavcopy archive
# ---------------------------------------------------------------------------
def _day_path(d):
    return CACHE_DIR / f"{d:%Y%m%d}.json"


def _read_day(d):
    try:
        return json.loads(_day_path(d).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fetch_day(d):
    """Futures rows for date d: [[symbol, expiry, open, high, low, close, oi, volume], ...];
    [] for a non-trading day; None if the archive doesn't have it (yet)."""
    cached_rows = _read_day(d)
    if cached_rows is not None:
        return cached_rows
    try:
        r = nse_http.get(ARCHIVE_URL.format(day=f"{d:%Y%m%d}"), timeout=40)
    except Exception:
        return None
    if r.status_code == 404:
        rows = []
        if d < datetime.now(IST).date() - timedelta(days=3):  # long past: really a holiday
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _day_path(d).write_text("[]", encoding="utf-8")
            return rows
        return None
    if r.status_code != 200 or r.content[:2] != b"PK":
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            df = pd.read_csv(z.open(z.namelist()[0]), usecols=["FinInstrmTp", "TckrSymb", "XpryDt", "OpnPric", "HghPric", "LwPric", "ClsPric", "OpnIntrst", "TtlTradgVol"])
    except Exception:
        return None
    df = df[df["FinInstrmTp"].isin(["IDF", "STF"])]
    rows = [[x.TckrSymb, x.XpryDt, x.OpnPric, x.HghPric, x.LwPric, x.ClsPric, int(x.OpnIntrst), int(x.TtlTradgVol)] for x in df.itertuples()]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _day_path(d).write_text(json.dumps(rows), encoding="utf-8")
    return rows


def _ensure_days(days):
    """Fetch every missing day in parallel; wait at most the budget. Days still downloading
    keep going in the background and are ready on the next request."""
    got = {}
    pending = {}
    for d in days:
        rows = _read_day(d)
        if rows is not None:
            got[d] = rows
        else:
            pending[d] = _pool.submit(_fetch_day, d)
    if pending:
        wait(pending.values(), timeout=DAILY_FETCH_BUDGET_SEC)
        for d, fut in pending.items():
            if fut.done() and fut.result() is not None:
                got[d] = fut.result()
    return got


def _utc_midnight(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def daily_bars(underlying, calendar_days):
    today = datetime.now(IST).date()
    days = [today - timedelta(n) for n in range(min(calendar_days, MAX_DAILY_CALENDAR_DAYS), 0, -1)]
    days = [d for d in days if d.weekday() < 5]
    got = _ensure_days(days)
    bars = []
    for d in days:
        contracts = [r for r in got.get(d) or [] if r[0] == underlying and _iso(r[1]) >= d]
        if not contracts:
            continue
        r = min(contracts, key=lambda x: _iso(x[1]))
        bars.append({"time": _utc_midnight(d), "open": r[2], "high": r[3], "low": r[4], "close": r[5], "volume": r[7]})
    # The archive publishes after the close, so today's bar comes from the live front month.
    rows, _spot, _ts = futures(underlying)
    if rows and today.weekday() < 5 and rows[0]["open"] and rows[0]["last"] is not None:
        f = rows[0]
        bars.append({"time": _utc_midnight(today), "open": f["open"], "high": f["high"], "low": f["low"],
                     "close": f["last"], "volume": f["volume"] or 0})
    return bars


def _iso(s):
    return date.fromisoformat(s)


RANGE_DAYS = {"1D": 1, "5D": 7, "1M": 31, "3M": 92, "6M": 183, "1Y": 366, "5Y": MAX_DAILY_CALENDAR_DAYS, "ALL": MAX_DAILY_CALENDAR_DAYS}


def candles(symbol, interval, rng):
    """Chart payload for a futures symbol: intraday bars for a 1D view, else daily history."""
    res = resolve(symbol)
    if not res:
        raise ValueError("not an F&O symbol")
    step = INTERVAL_SECONDS.get(interval)
    if rng == "1D" and step:
        bars = intraday_bars(res["underlying"], step)
        if bars:
            return {"symbol": res["fut"], "interval": interval, "range": rng, "candles": bars, "liveBars": 0}
    today = datetime.now(IST).date()
    days = RANGE_DAYS.get(rng) if rng != "YTD" else (today - date(today.year, 1, 1)).days + 1
    # A 1D/5D view at daily resolution would be one or two bars; show a couple of weeks instead.
    days = max(days or 31, 14)
    return {"symbol": res["fut"], "interval": "1d", "range": rng, "candles": daily_bars(res["underlying"], days), "liveBars": 0}


# ---------------------------------------------------------------------------
# The F&O panel
# ---------------------------------------------------------------------------
def _side(x):
    if not x:
        return None
    return {"oi": x.get("openInterest"), "dOi": x.get("changeinOpenInterest"), "volume": x.get("totalTradedVolume"),
            "iv": x.get("impliedVolatility"), "ltp": x.get("lastPrice"), "change": x.get("change")}


def max_pain(rows):
    """Strike at which option writers pay out least: minimise the summed intrinsic value of all
    open CE/PE contracts if the underlying expired there."""
    def pain(k):
        return sum(((r["ce"] or {}).get("oi") or 0) * max(k - r["strike"], 0) +
                   ((r["pe"] or {}).get("oi") or 0) * max(r["strike"] - k, 0) for r in rows)
    return min((r["strike"] for r in rows), key=pain)


def chain(res, expiry):
    info = cached(("fno-info", res["underlying"]), 300, lambda: nse_get("/api/option-chain-contract-info", {"symbol": res["underlying"]}))
    expiries = (info or {}).get("expiryDates") or []
    if not expiries:
        return None
    exp = expiry if expiry in expiries else expiries[0]
    d = cached(("fno-chain", res["underlying"], exp), 3, lambda: nse_get(
        "/api/option-chain-v3", {"type": res["chainType"], "symbol": res["underlying"], "expiry": exp}))
    rec = (d or {}).get("records")
    if not rec:
        return {"expiries": expiries, "expiry": exp, "rows": []}
    rows = [{"strike": r["strikePrice"], "ce": _side(r.get("CE")), "pe": _side(r.get("PE"))}
            for r in rec.get("data", []) if r.get("strikePrice") is not None]
    rows.sort(key=lambda r: r["strike"])
    spot = rec.get("underlyingValue")
    ce_oi = sum((r["ce"] or {}).get("oi") or 0 for r in rows)
    pe_oi = sum((r["pe"] or {}).get("oi") or 0 for r in rows)
    atm = min(rows, key=lambda r: abs(r["strike"] - spot)) if rows and spot else None
    straddle = None
    if atm and atm["ce"] and atm["pe"] and atm["ce"]["ltp"] is not None and atm["pe"]["ltp"] is not None:
        straddle = atm["ce"]["ltp"] + atm["pe"]["ltp"]
    return {
        "expiries": expiries, "expiry": exp, "asOf": rec.get("timestamp"), "spot": spot, "rows": rows,
        "atm": atm["strike"] if atm else None, "straddle": straddle,
        "totalCeOi": ce_oi, "totalPeOi": pe_oi, "pcr": (pe_oi / ce_oi) if ce_oi else None,
        "maxPain": max_pain(rows) if rows else None,
    }


def panel(symbol, expiry=None):
    res = resolve(symbol)
    if not res:
        return {"available": False, "symbol": symbol, "reason": "No futures or options are listed on NSE for this symbol."}
    rows, spot, ts = futures(res["underlying"])
    return {
        "available": True, "symbol": symbol, "underlying": res["underlying"], "name": res["name"], "kind": res["kind"],
        "spotSymbol": res["spot"], "futureSymbol": res["fut"], "spot": spot, "asOf": ts,
        "futures": rows or [], "chain": chain(res, expiry),
    }
