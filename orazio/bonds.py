"""Government bond yields for 37 countries, real time from CNBC's quote service, each one chartable.

Quotes — CNBC's quote service (the one cnbc.com/quotes pages call) returns real-time yields with the time of
the last tick (measured: 15–40 s old while each market trades). CATALOG lists every symbol it answered for
when probed on 19 Oct 2026 (country x maturity, 161 in all); markets it doesn't carry (Taiwan, Malaysia,
Poland, Israel, ...) aren't here. Indian G-secs, SDLs and T-bills come from CCIL instead (gsec.py).

Charts — CNBC's bars API serves 1-min (~7 days), 5-min (~40 days), 1-hour (~98 days), daily and weekly bars
(no 15-min: built from 5-min here). For the India 10Y it has NO daily/weekly history, so those come from
worldgovernmentbonds.com's chart endpoint: one value a day since March 2015, checked against CNBC's closes
(7.363 vs 7.366, 7.399 vs 7.403, 7.389 vs 7.392). It also lists weekends, repeating or shifting Friday's
value, so weekend points are dropped.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from .cache import cached
from .http_clients import cnbc_http
from .symbols import resolve_interval_range

CNBC_URL = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
GLOBAL_TTL, QUOTE_TTL = 15, 3
BATCH = 50
# (country code, name, region, CNBC prefix, CNBC suffix, maturities CNBC carries)
CATALOG = [
    ("US", "United States", "Americas", "US", None, ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]),
    ("CA", "Canada", "Americas", "CA", "CA", ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "10Y", "20Y", "30Y"]),
    ("MX", "Mexico", "Americas", "MX", "MX", ["1Y", "3Y", "10Y"]),
    ("BR", "Brazil", "Americas", "BR", "BR", ["1Y", "2Y", "10Y"]),
    ("CL", "Chile", "Americas", "CL", "CL", ["10Y"]),
    ("AR", "Argentina", "Americas", "AR", "AR", ["20Y"]),
    ("GB", "United Kingdom", "Europe", "UK", "GB", ["2Y", "5Y", "10Y", "30Y"]),
    ("DE", "Germany", "Europe", "DE", "DE", ["6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]),
    ("FR", "France", "Europe", "FR", "FR", ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]),
    ("IT", "Italy", "Europe", "IT", "IT", ["6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]),
    ("ES", "Spain", "Europe", "ES", "ES", ["6M", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]),
    ("PT", "Portugal", "Europe", "PT", "PT", ["2Y", "3Y", "5Y", "10Y"]),
    ("NL", "Netherlands", "Europe", "NL", "NL", ["2Y", "10Y"]),
    ("BE", "Belgium", "Europe", "BE", "BE", ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "30Y"]),
    ("AT", "Austria", "Europe", "AT", "AT", ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]),
    ("IE", "Ireland", "Europe", "IE", "IE", ["2Y", "5Y", "10Y"]),
    ("GR", "Greece", "Europe", "GR", "GR", ["2Y", "3Y", "10Y"]),
    ("FI", "Finland", "Europe", "FI", "FI", ["2Y", "3Y", "5Y", "10Y"]),
    ("CH", "Switzerland", "Europe", "CH", "CH", ["2Y", "10Y"]),
    ("SE", "Sweden", "Europe", "SE", "SE", ["2Y", "10Y"]),
    ("DK", "Denmark", "Europe", "DK", "DK", ["2Y"]),
    ("HU", "Hungary", "Europe", "HU", "HU", ["1Y", "3Y", "5Y", "10Y", "15Y"]),
    ("TR", "Turkey", "Europe", "TR", "TR", ["2Y", "10Y"]),
    ("IN", "India", "Asia-Pacific", "IN", "IN", ["10Y", "30Y"]),
    ("CN", "China", "Asia-Pacific", "CN", "CN", ["2Y", "10Y"]),
    ("JP", "Japan", "Asia-Pacific", "JP", "JP", ["3M", "6M", "2Y", "3Y", "5Y", "10Y", "15Y", "20Y", "30Y"]),
    ("KR", "South Korea", "Asia-Pacific", "KR", "KR", ["5Y", "10Y"]),
    ("HK", "Hong Kong", "Asia-Pacific", "HK", "HK", ["10Y"]),
    ("SG", "Singapore", "Asia-Pacific", "SG", "SG", ["10Y", "15Y", "20Y"]),
    ("ID", "Indonesia", "Asia-Pacific", "ID", "ID", ["10Y", "15Y"]),
    ("TH", "Thailand", "Asia-Pacific", "TH", "TH", ["10Y"]),
    ("AU", "Australia", "Asia-Pacific", "AU", "AU", ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y"]),
    ("NZ", "New Zealand", "Asia-Pacific", "NZ", "NZ", ["1M", "3M", "6M", "1Y", "2Y", "5Y", "10Y"]),
    ("ZA", "South Africa", "Middle East & Africa", "ZA", "ZA", ["3M", "5Y", "10Y", "20Y", "30Y"]),
    ("EG", "Egypt", "Middle East & Africa", "EG", "EG", ["3M", "1Y"]),
    ("NG", "Nigeria", "Middle East & Africa", "NG", "NG", ["10Y"]),
    ("KE", "Kenya", "Middle East & Africa", "KE", "KE", ["15Y"]),
]


def cnbc_symbol(prefix, suffix, tenor):
    return f"{prefix}{tenor}" + (f"-{suffix}" if suffix else "")


# symbol -> {country, name, region, tenor}
SYMBOLS = {cnbc_symbol(p, s, t): {"country": cc, "name": n, "region": rg, "tenor": t}
           for cc, n, rg, p, s, tenors in CATALOG for t in tenors}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def yield_row(q):
    """One CNBC quote -> one yield row ("5.067%" -> 5.067, change -0.031 -> -3.1 bp)."""
    meta = SYMBOLS.get(q.get("symbol"), {})
    change = _num(q.get("change"))
    return {
        "symbol": q.get("symbol"), **meta,
        "label": f"{meta.get('name', q.get('symbol'))} {meta.get('tenor', '')}".strip(),
        "yield": _num(str(q.get("last", "")).rstrip("%")),
        "changeBp": round(change * 100, 1) if change is not None else None,
        "time": q.get("last_time"),
        "realTime": q.get("realTime") == "true" or q.get("realTime") is True,
    }


def _batch(symbols):
    r = cnbc_http.get(CNBC_URL, params={"symbols": "|".join(symbols), "requestMethod": "itv", "noform": "1",
                                        "partnerId": "2", "fund": "1", "exthrs": "1", "output": "json",
                                        "events": "1"}, timeout=20)
    return r.json()["FormattedQuoteResult"]["FormattedQuote"]


def _quotes(symbols):
    # The batches go out together: one after another, the 161 yields took 17 s (measured).
    chunks = [symbols[i:i + BATCH] for i in range(0, len(symbols), BATCH)]
    with ThreadPoolExecutor(max_workers=len(chunks) or 1) as pool:
        out = [q for part in pool.map(_batch, chunks) for q in part]
    return [yield_row(q) for q in out if q.get("symbol") in SYMBOLS and _num(str(q.get("last", "")).rstrip("%")) is not None]


_global = {"at": 0.0, "rows": [], "busy": False}
_global_lock = threading.Lock()


def _refresh_global():
    try:
        rows = {r["symbol"]: r for r in _quotes(list(SYMBOLS))}
        _global["rows"] = [rows[s] for s in SYMBOLS if s in rows]
        _global["at"] = time.time()
    except Exception:
        pass   # keep the last snapshot; retried on the next request after GLOBAL_TTL
    finally:
        _global["busy"] = False


def global_yields():
    """Every catalogued yield, in CATALOG order. A full refresh takes ~6 s (CNBC is slow), so callers get the
    last snapshot at once and a fresh one is fetched in the background; only the very first call waits."""
    with _global_lock:
        stale = time.time() - _global["at"] > GLOBAL_TTL
        start = stale and not _global["busy"]
        if start:
            _global["busy"] = True
    if start and not _global["rows"]:
        _refresh_global()
    elif start:
        threading.Thread(target=_refresh_global, daemon=True).start()
    return _global["rows"]


# ---------- charting one yield ----------
DECIMALS = 3
CNBC_BARS = "https://ts-api.cnbc.com/harmony/app/bars/{sym}/{iv}/{start}/{end}/adjusted/EST5EDT.json"
WGB_URL = "https://www.worldgovernmentbonds.com/wp-json/common/v1/historical"
# How far back each bar size reaches on CNBC (measured); a longer range escalates to a coarser bar.
MAX_RANGE = {"1m": "1W", "5m": "1M", "15m": "1M", "1h": "3M", "1d": "ALL", "1wk": "ALL"}
CNBC_INTERVAL = {"1m": "1M", "5m": "5M", "15m": "5M", "1h": "1H", "1d": "1D", "1wk": "1W"}
RANGE_DAYS = {"1D": 3, "1W": 7, "1M": 31, "3M": 92, "6M": 183, "1Y": 366, "5Y": 1827, "ALL": 13000}
SESSION_GAP_SEC = 2700        # a pause this long ends a session (India closes overnight; the US breaks 1 h a day)
INTRADAY_TTL, DAILY_TTL = 30, 3600
# worldgovernmentbonds' chart call: the country by its internal id, the maturity in months.
WGB_SERIES = {"IN10Y-IN": ("8", "India", "in", "india", 120, "10 Years")}


def is_bond(symbol):
    return symbol in SYMBOLS


def name(symbol):
    m = SYMBOLS.get(symbol)
    return f"{m['name']} {m['tenor']} government bond yield (%)" if m else None


def _one_quote(symbol):
    rows = _quotes([symbol])
    return rows[0] if rows else None


def quote(symbol):
    """The live yield as a chart quote (price = yield in %)."""
    try:
        row = cached(("bond-q", symbol), QUOTE_TTL, lambda: _one_quote(symbol))
    except Exception:
        return None
    if not row or row["yield"] is None:
        return None
    try:
        market_time = int(datetime.fromisoformat(row["time"].replace(".000", "")).timestamp())
    except (AttributeError, TypeError, ValueError):
        market_time = 0
    return {"price": row["yield"], "prevClose": row["yield"] - (row["changeBp"] or 0) / 100,
            "marketTime": market_time, "currency": "%"}


def _bar(b, daily):
    """CNBC price bar -> chart row. Daily/weekly bars sit on their calendar date (00:00 UTC), like Yahoo's."""
    t = (int(datetime.strptime(b["tradeTime"][:8], "%Y%m%d").replace(tzinfo=timezone.utc).timestamp()) if daily
         else int(b["tradeTimeinMills"]) // 1000)
    return {"time": t, "open": float(b["open"]), "high": float(b["high"]), "low": float(b["low"]),
            "close": float(b["close"]), "volume": 0}


def resample(rows, step):
    """Fixed-size buckets (e.g. 15-min bars from 5-min ones): first open, highest high, lowest low, last close."""
    out = []
    for r in rows:
        t = r["time"] - r["time"] % step
        if out and out[-1]["time"] == t:
            o = out[-1]
            o["high"], o["low"], o["close"] = max(o["high"], r["high"]), min(o["low"], r["low"]), r["close"]
        else:
            out.append({**r, "time": t})
    return out


def last_session(rows, gap=SESSION_GAP_SEC):
    """The bars of the most recent trading session: back from the newest bar to the first long pause."""
    i = len(rows) - 1
    while i > 0 and rows[i]["time"] - rows[i - 1]["time"] < gap:
        i -= 1
    return rows[i:] if rows else rows


def weekly(daily):
    """Daily rows -> weekly (ISO week, stamped on its first day)."""
    out = []
    for r in daily:
        wk = datetime.fromtimestamp(r["time"], timezone.utc).isocalendar()[:2]
        if out and out[-1][0] == wk:
            o = out[-1][1]
            o["high"], o["low"], o["close"] = max(o["high"], r["high"]), min(o["low"], r["low"]), r["close"]
        else:
            out.append((wk, dict(r)))
    return [o for _, o in out]


def _cnbc_bars(symbol, iv, start, end):
    url = CNBC_BARS.format(sym=symbol, iv=iv, start=start.strftime("%Y%m%d%H%M%S"), end=end.strftime("%Y%m%d%H%M%S"))
    bars = cnbc_http.get(url, timeout=20).json().get("barData", {}).get("priceBars") or []
    return [_bar(b, iv in ("1D", "1W")) for b in bars if b.get("close") not in (None, "")]


def wgb_points(payload):
    """worldgovernmentbonds' {"quote": {n: {DATA_VAL, CLOSE_VAL}}} -> daily rows, weekends dropped."""
    rows = []
    for p in (payload.get("result") or {}).get("quote", {}).values():
        try:
            d = date.fromisoformat(p["DATA_VAL"])
            v = float(p["CLOSE_VAL"])
        except (KeyError, TypeError, ValueError):
            continue
        if d.weekday() < 5:
            t = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
            rows.append({"time": t, "open": v, "high": v, "low": v, "close": v, "volume": 0})
    return sorted(rows, key=lambda r: r["time"])


def _wgb_daily(symbol):
    sid, country, flag, page, months, label = WGB_SERIES[symbol]
    body = {"GLOBALVAR": {"FUNCTION": "Bond", "DOMESTIC": True, "DATE_RIF": "2099-12-31",
                          "OBJ": {"UNIT": "%", "DECIMAL": 3, "UNIT_DELTA": "bp", "DECIMAL_DELTA": 1},
                          "COUNTRY1": {"SYMBOL": sid, "PAESE": country, "PAESE_UPPERCASE": country.upper(),
                                       "BANDIERA": flag, "URL_PAGE": page},
                          "COUNTRY2": None, "OBJ1": {"DURATA_STRING": label, "DURATA": months}, "OBJ2": None}}
    r = cnbc_http.post(WGB_URL, json=body, timeout=25,
                       headers={"Origin": "https://www.worldgovernmentbonds.com",
                                "Referer": f"https://www.worldgovernmentbonds.com/bond-historical-data/{page}/10-years/"})
    return wgb_points(r.json())


def _start(rng, now):
    if rng == "YTD":
        return datetime(now.year, 1, 1, tzinfo=timezone.utc)
    return now - timedelta(days=RANGE_DAYS.get(rng, 3))


def _rows(symbol, interval, rng, now):
    start = _start(rng, now)
    if interval in ("1d", "1wk") and symbol in WGB_SERIES:
        daily = cached(("bond-wgb", symbol), DAILY_TTL, lambda: _wgb_daily(symbol))
        rows = [r for r in daily if r["time"] >= start.timestamp()]
        return weekly(rows) if interval == "1wk" else rows
    rows = cached(("bond-bars", symbol, interval, rng), INTRADAY_TTL if interval not in ("1d", "1wk") else DAILY_TTL,
                  lambda: _cnbc_bars(symbol, CNBC_INTERVAL[interval], start, now))
    if interval == "15m":
        rows = resample(rows, 900)
    if rng == "1D" and interval not in ("1d", "1wk"):
        rows = last_session(rows)
    return rows


def with_today(rows, q, interval):
    """CNBC's daily bars stop at the last finished session, so the page would paint today's live yield onto
    yesterday's candle. Open today's daily bar (or this week's weekly bar) from the live quote instead."""
    if not rows or not q or not q.get("marketTime"):
        return rows
    d = datetime.fromtimestamp(q["marketTime"], timezone.utc).date()
    t = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
    last = datetime.fromtimestamp(rows[-1]["time"], timezone.utc).date()
    same = last.isocalendar()[:2] == d.isocalendar()[:2] if interval == "1wk" else last >= d
    if same:
        return rows
    p = q["price"]
    return rows + [{"time": t, "open": p, "high": p, "low": p, "close": p, "volume": 0}]


def candles(symbol, interval, rng, now=None):
    """The /api/candles payload for a benchmark yield."""
    interval, rng = resolve_interval_range(interval, rng, MAX_RANGE)
    now = now or datetime.now(timezone.utc)
    try:
        rows = _rows(symbol, interval, rng, now)
        if interval in ("1d", "1wk"):
            rows = with_today(rows, quote(symbol), interval)
    except Exception:   # CNBC/worldgovernmentbonds down: an empty chart says "no data", not an error page
        rows = []
    # worldgovernmentbonds has one value a day: open = high = low = close, which candles draw as dots.
    close_only = interval == "1d" and symbol in WGB_SERIES
    return {"symbol": symbol, "interval": interval, "range": rng, "candles": rows, "liveBars": 0,
            "source": "cnbc", "decimals": DECIMALS, "closeOnly": close_only}
