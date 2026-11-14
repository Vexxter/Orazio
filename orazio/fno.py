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

SENSEX futures trade on BSE, not NSE, so SENSEX-FUT comes from BSE's own public site calls (verified 22 Oct 2026):
  * Marketwatchindxderi: every index derivative with last trade, OHLC, OI, volume (contracts), lot size.
  * StockReachGraph?scripcode=1&seriesid=<contract>: today's one-minute closes, with volume.
  * The daily derivatives bhavcopy (same UDiFF columns as NSE's, but plain CSV; a missing day answers 200
    with BSE's HTML home page). No option chain is wired for BSE, so the panel shows futures only.
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
import requests

from .cache import cached
from .constants import IST, INTERVAL_SECONDS
from .http_clients import bse_http, nse_http
from .nse_client import nse_get

QUOTE_API = "/api/NextApi/apiClient/GetQuoteApi"
CACHE_DIR = Path.home() / ".orazio" / "fut_cache"
ARCHIVE_URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{day}_F_0000.csv.zip"
LOTS_URL = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"
BSE_ARCHIVE_URL = "https://www.bseindia.com/download/Bhavcopy/Derivative/BhavCopy_BSE_FO_0_0_0_{day}_F_0000.CSV"
BSE_UNDERLYINGS = {"SENSEX": 1}   # underlying -> BSE scrip code of the index
DAILY_FETCH_BUDGET_SEC = 25
MAX_DAILY_CALENDAR_DAYS = 730
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="fut-archive")
_last_ticks = {}   # (contract, IST date) -> the last non-empty tick series NSE served for it
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
    if s in ("SENSEX", "^BSESN"):
        return {"underlying": "SENSEX", "kind": "index", "spot": "SENSEX", "fut": "SENSEX-FUT", "chainType": "Indices", "name": "BSE SENSEX"}
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
    return {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK", "SENSEX": "^BSESN"}.get(res["underlying"], res["spot"]) if res else symbol


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
        "lotSize": r.get("lotSize"),
    }


def bse_watch():
    """BSE's index-derivatives market watch rows ([] when BSE is unreachable)."""
    def fetch():
        try:
            return bse_http.get(BSE_API + "/Marketwatchindxderi/w", timeout=6).json().get("Table") or []
        except (requests.RequestException, ValueError, AttributeError):
            return []
    return cached(("bse-deriv",), 2, fetch)


def bse_row(r):
    """A BSE market-watch future in the shape of an NSE getSymbolDerivativesData row. BSE counts volume in
    contracts and value in lakhs; the bhavcopy (and so the daily chart) counts quantity, contracts x lot."""
    lot = r.get("Market_Lot") or 1
    vol = r.get("VOLUME")
    return {"expiryDate": datetime.strptime(r["EXPIRYDATE"], "%d %b %y").strftime("%d-%b-%Y"),
            "identifier": r.get("SCRIPCODE"), "lastPrice": r.get("LASTTRADERATE"), "prevClose": r.get("PREVIOUSCLOSERATE"),
            "change": r.get("CHANGE"), "pChange": r.get("CHANGEPERC"), "openPrice": r.get("OPENRATE"),
            "highPrice": r.get("HIGHRATE"), "lowPrice": r.get("LOWRATE"), "openInterest": r.get("OI"),
            "totalTradedVolume": vol * lot if vol is not None else None,
            "totalTurnover": r["VALUE"] * 1e5 if r.get("VALUE") is not None else None, "lotSize": lot}


def _bse_futures(underlying):
    """(NSE-shaped rows, spot, timestamp) for a BSE underlying."""
    from .market_data import bse_live_quote   # deferred: market_data starts the BSE stream on import
    raw = [r for r in bse_watch() if r.get("ProductType") == "IF" and r.get("UNDERLYINGNAME") == underlying and r.get("EXPIRYDATE")]
    if not raw:
        return [], None, None
    q = bse_live_quote()
    ts = max(r.get("TRADETIME") or "" for r in raw)
    ts = datetime.fromisoformat(ts).strftime("%d-%b-%Y %H:%M:%S") if ts else None
    return [bse_row(r) for r in raw], q and q["price"], ts


def futures(underlying):
    """(list of futures rows sorted by expiry, spot, data timestamp) — or (None, None, None)."""
    if underlying in BSE_UNDERLYINGS:
        rows, spot, ts = _bse_futures(underlying)
        if not rows:
            return None, None, None
    else:
        d = derivatives(underlying)
        if not d:
            return None, None, None
        rows = [r for r in d.get("data", []) if r.get("instrumentType") in ("FUTIDX", "FUTSTK") and r.get("expiryDate")]
        spot = next((r.get("underlyingValue") for r in rows if r.get("underlyingValue")), None)
        ts = d.get("timestamp")
    rows.sort(key=lambda r: _expiry(r["expiryDate"]))
    today = datetime.now(IST).date()
    rows = [r for r in rows if _expiry(r["expiryDate"]) >= today]
    return [_future_row(r, spot) for r in rows], spot, ts


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
    key = (identifier, datetime.now(IST).date())

    def fetch():
        # NSE intermittently answers this with an empty series (seen 29 Oct 2026: the same URL empty,
        # then full, then empty again within seconds), so retry with a cache-buster, and when every try
        # comes back empty keep the last full series rather than collapsing the chart to one bar.
        for n in range(4):
            params = {"index": identifier, "_": f"{time.time_ns() // 1_000_000 + n}"}
            if n % 2 == 0:
                params["indices"] = "false"
            pts = (nse_get("/api/chart-databyindex", params) or {}).get("grapthData")  # NSE's own spelling
            if pts:
                _last_ticks[key] = pts
                return pts
        return _last_ticks.get(key, [])
    return cached(("fno-ticks", identifier), 5, fetch)


def _bse_minutes(underlying, contract):
    """Today's one-minute closes of a BSE contract as [(epoch, price, volume)], oldest first."""
    def fetch():
        try:
            d = bse_http.get(BSE_API + "/StockReachGraph/w", timeout=8, params={
                "scripcode": BSE_UNDERLYINGS[underlying], "flag": 0, "fromdate": "", "todate": "", "seriesid": contract}).json()
            pts = json.loads(d.get("Data") or "[]")
        except (requests.RequestException, ValueError, AttributeError):
            return []
        out = []
        for p in pts:   # "Thu Oct 22 2026 11:03:40", IST
            try:
                t = int(datetime.strptime(p["dttm"], "%a %b %d %Y %H:%M:%S").replace(tzinfo=IST).timestamp())
                out.append((t, float(p["vale1"]), float(p.get("vole") or 0)))
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(out)
    return cached(("bse-ticks", contract), 5, fetch)


def front_ticks(underlying):
    """Today's ticks of the front-month future as [(epoch, price)], oldest first, with the quote API's
    latest price appended when it is newer than the tick chart's last point."""
    rows, _spot, ts = futures(underlying)
    if not rows:
        return []
    # NSE stamps these in "IST as if it were UTC" — shift back to a real epoch.
    ticks = [(int(ms / 1000) - 19800, float(price)) for ms, price in _ticks(rows[0]["identifier"])]
    stamp = _stamp(ts)
    last = rows[0].get("last")
    if last is not None and (not ticks or stamp > ticks[-1][0]):
        ticks.append((stamp, float(last)))
    return ticks


def intraday_bars(underlying, step):
    if underlying in BSE_UNDERLYINGS:
        rows, _spot, _ts = futures(underlying)
        ticks = _bse_minutes(underlying, rows[0]["identifier"]) if rows else []
    else:
        ticks = [(t, p, 0) for t, p in front_ticks(underlying)]
    buckets = {}
    for t, price, vol in ticks:
        slot = t // step * step
        b = buckets.get(slot)
        if b is None:
            buckets[slot] = [price, price, price, price, vol]
        else:
            b[1], b[2], b[3], b[4] = max(b[1], price), min(b[2], price), price, b[4] + vol
    return [{"time": t, "open": o, "high": h, "low": l, "close": c, "volume": v} for t, (o, h, l, c, v) in sorted(buckets.items())]


# ---------------------------------------------------------------------------
# Daily history from the F&O bhavcopy archive
# ---------------------------------------------------------------------------
def _day_path(d, bse=False):
    return CACHE_DIR / f"{'bse_' if bse else ''}{d:%Y%m%d}.json"


def _read_day(d, bse=False):
    try:
        return json.loads(_day_path(d, bse).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fetch_day(d, bse=False):
    """Futures rows for date d: [[symbol, expiry, open, high, low, close, oi, volume], ...];
    [] for a non-trading day; None if the archive doesn't have it (yet)."""
    cached_rows = _read_day(d, bse)
    if cached_rows is not None:
        return cached_rows
    try:
        r = (bse_http if bse else nse_http).get((BSE_ARCHIVE_URL if bse else ARCHIVE_URL).format(day=f"{d:%Y%m%d}"), timeout=40)
    except Exception:
        return None
    # BSE answers a missing day with 200 and its HTML home page instead of a 404.
    if r.status_code == 404 or (bse and r.status_code == 200 and not r.content.startswith(b"TradDt")):
        rows = []
        if d < datetime.now(IST).date() - timedelta(days=3):  # long past: really a holiday
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _day_path(d, bse).write_text("[]", encoding="utf-8")
            return rows
        return None
    if r.status_code != 200 or (not bse and r.content[:2] != b"PK"):
        return None
    cols = ["FinInstrmTp", "TckrSymb", "XpryDt", "OpnPric", "HghPric", "LwPric", "ClsPric", "OpnIntrst", "TtlTradgVol"]
    try:
        if bse:
            df = pd.read_csv(io.BytesIO(r.content), usecols=cols)
        else:
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                df = pd.read_csv(z.open(z.namelist()[0]), usecols=cols)
    except Exception:
        return None
    df = df[df["FinInstrmTp"].isin(["IDF", "STF"])]
    rows = [[x.TckrSymb, x.XpryDt, x.OpnPric, x.HghPric, x.LwPric, x.ClsPric, int(x.OpnIntrst), int(x.TtlTradgVol)] for x in df.itertuples()]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _day_path(d, bse).write_text(json.dumps(rows), encoding="utf-8")
    return rows


def _ensure_days(days, bse=False):
    """Fetch every missing day in parallel; wait at most the budget. Days still downloading
    keep going in the background and are ready on the next request."""
    got = {}
    pending = {}
    for d in days:
        rows = _read_day(d, bse)
        if rows is not None:
            got[d] = rows
        else:
            pending[d] = _pool.submit(_fetch_day, d, bse)
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
    got = _ensure_days(days, underlying in BSE_UNDERLYINGS)
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


RANGE_DAYS = {"1D": 1, "1W": 7, "1M": 31, "3M": 92, "6M": 183, "1Y": 366, "5Y": MAX_DAILY_CALENDAR_DAYS, "ALL": MAX_DAILY_CALENDAR_DAYS}


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
    # A 1D/1W view at daily resolution would be one or two bars; show a couple of weeks instead.
    days = max(days or 31, 14)
    return {"symbol": res["fut"], "interval": "1d", "range": rng, "candles": daily_bars(res["underlying"], days), "liveBars": 0}


# ---------------------------------------------------------------------------
# Lot sizes (for the payoff calculator)
# ---------------------------------------------------------------------------
def parse_lots(text):
    """NSE's fo_mktlots.csv -> {symbol: lot size of the nearest month}. Columns are space-padded;
    a month an underlying doesn't trade is blank."""
    lots = {}
    for line in text.splitlines()[1:]:
        cols = [c.strip() for c in line.split(",")]
        if len(cols) < 3 or not cols[1]:
            continue
        size = next((c for c in cols[2:] if c.isdigit()), None)
        if size:
            lots[cols[1].upper()] = int(size)
    return lots


def lot_size(underlying):
    def fetch():
        try:
            r = nse_http.get(LOTS_URL, timeout=10)
            return parse_lots(r.text) if r.status_code == 200 else {}
        except requests.RequestException:
            return {}
    return cached(("fno-lots", ""), 12 * 3600, fetch).get(underlying)


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
    bse = res["underlying"] in BSE_UNDERLYINGS
    return {
        "available": True, "symbol": symbol, "underlying": res["underlying"], "name": res["name"], "kind": res["kind"],
        "spotSymbol": res["spot"], "futureSymbol": res["fut"], "spot": spot, "asOf": ts,
        "lotSize": (rows[0]["lotSize"] if rows else None) if bse else lot_size(res["underlying"]),
        "futures": rows or [], "chain": None if bse else chain(res, expiry),
    }
