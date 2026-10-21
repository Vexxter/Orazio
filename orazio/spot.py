"""Spot prices for WTI crude, gold and silver: the default commodity feed. Measured 21 Oct 2026.

Gold, silver — live from Swissquote (a Swiss bank/broker), whose public JSON feed backs its website ticker
(`public-quotes/bboquotes/instrument/XAU/USD`): ticks every ~4 s, seconds old. History from Dukascopy (another
Swiss bank, `freeserv.dukascopy.com` chart/json3, up to 5000 bars a call, newest first); the two agree to cents.

WTI crude — both live and history from Dukascopy (LIGHT.CMD/USD; live = its 1-second bars, 5-8 s old). It is
what trading screens call WTI/USOIL spot: matched TradingView's FX:USOIL to a cent (99.29) and sits on the
CME front month. NOT Swissquote: its OIL/USD ran a steady +$1.4 above every other WTI quote (carry built in).
The official spot (EIA Cushing, daily, eia.gov RWTCd.xls) lags a week, so it can't serve a live chart.

Brent — Dukascopy too (BRENT.CMD/USD, 1-second bars ~3 s old): 110.44 against TradingView's FX:UKOIL 110.41
and the ICE front month 110.48. Binance's Brent perpetual tracks ICE's *second* month (~$4 lower that day), and
Swissquote's BRN/USD never moved in 12 minutes.

Natural gas, copper — Dukascopy's GAS.CMD/USD (2.975 vs NYMEX Nov 2.981; Binance's perp sat on Dec at 3.31,
11% off) and COPPER.CMD/USD (6.6045 vs COMEX Dec 6.603). Gas ticks slower (last trade ~60 s old at times).

The oil, gas and copper CFDs are rolling front-month contracts — what trading screens call "spot" for these;
Dukascopy labels only gold and silver as true spot ("Spot gold", "Spot silver"). It has no dated futures.
"""
import calendar
import json
import re
import time

import requests

from .cache import cached
from .constants import USER_AGENT
from .symbols import resolve_interval_range

SQ_URL = "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/{}"
DUKA_URL = "https://freeserv.dukascopy.com/2.0/index.php"
_UA = {"User-Agent": USER_AGENT}
_DUKA_HEADERS = {**_UA, "Referer": "https://freeserv.dukascopy.com/2.0/?path=chart/index"}

# Yahoo chart symbol -> (live source, live instrument, Dukascopy history instrument)
SPOT = {
    "CL=F": ("dukascopy", "LIGHT.CMD/USD", "LIGHT.CMD/USD"),
    "BZ=F": ("dukascopy", "BRENT.CMD/USD", "BRENT.CMD/USD"),
    "NG=F": ("dukascopy", "GAS.CMD/USD", "GAS.CMD/USD"),
    "HG=F": ("dukascopy", "COPPER.CMD/USD", "COPPER.CMD/USD"),
    "GC=F": ("swissquote", "XAU/USD", "XAU/USD"),
    "SI=F": ("swissquote", "XAG/USD", "XAG/USD"),
}
QUOTE_TTL = 1
BAR_TTL = {"1m": 20, "5m": 30, "15m": 60, "1h": 120, "1d": 600, "1wk": 3600}
DUKA_INTERVAL = {"1s": "1SEC", "1m": "1MIN", "5m": "5MIN", "15m": "15MIN", "1h": "1HOUR", "1d": "1DAY", "1wk": "1WEEK"}
STEP = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400, "1wk": 7 * 86400}
RANGE_SECONDS = {"1D": 86400, "1W": 7 * 86400, "1M": 31 * 86400, "3M": 92 * 86400, "6M": 183 * 86400,
                 "1Y": 366 * 86400, "5Y": 1827 * 86400, "ALL": 20 * 366 * 86400}
MAX_BARS = 5000          # one Dukascopy call
MAX_PAGES = 3
# Bar sizes past which a range would need too many calls; resolve_interval_range escalates to a coarser one.
MAX_RANGE = {"1m": "1W", "5m": "1M", "15m": "3M", "1h": "1Y", "1d": "ALL", "1wk": "ALL"}


def has_spot(symbol):
    return symbol in SPOT


def parse_sq(d):
    """Swissquote bboquotes -> (mid, epoch seconds). The first platform's first spread profile is the standard one."""
    p = d[0]["spreadProfilePrices"][0]
    return (float(p["bid"]) + float(p["ask"])) / 2, d[0]["ts"] / 1000


def parse_duka(text):
    """Dukascopy's JSONP `_cb([[ms, o, h, l, c, v], ...])` (newest first) -> chart rows, oldest first."""
    m = re.search(r"_cb\((.*)\)\s*;?\s*$", text, re.S)
    rows = json.loads(m.group(1)) if m else []
    return sorted(({"time": int(r[0] // 1000), "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": 0}
                   for r in rows if isinstance(r, list) and len(r) >= 5), key=lambda r: r["time"])


def _duka(inst, interval, limit, before_ms):
    r = requests.get(DUKA_URL, params={"path": "chart/json3", "instrument": inst, "offer_side": "B",
                                       "interval": DUKA_INTERVAL[interval], "splits": "true", "stocks": "true",
                                       "limit": str(limit), "time_direction": "P", "timestamp": str(before_ms),
                                       "jsonp": "_cb"}, headers=_DUKA_HEADERS, timeout=20)
    return parse_duka(r.text)


def history(symbol, interval, seconds, now=None):
    """Dukascopy bars covering the last `seconds`, paging back up to MAX_PAGES calls."""
    inst = SPOT[symbol][2]
    now = now or time.time()
    need = min(int(seconds / STEP[interval]) + 2, MAX_BARS * MAX_PAGES)
    rows, before = [], int(now * 1000)
    for _ in range(MAX_PAGES):
        page = _duka(inst, interval, min(need - len(rows), MAX_BARS), before)
        if not page:
            break
        rows = page + [r for r in rows if r["time"] > page[-1]["time"]]
        if len(rows) >= need or len(page) < MAX_BARS:
            break
        before = page[0]["time"] * 1000 - 1
    return [r for r in rows if r["time"] >= now - seconds]


def _live(symbol):
    source, inst, _ = SPOT[symbol]
    if source == "swissquote":
        return parse_sq(requests.get(SQ_URL.format(inst), headers=_UA, timeout=8).json())
    bars = _duka(inst, "1s", 1, int(time.time() * 1000))
    return bars[-1]["close"], bars[-1]["time"]


def _prev_close(symbol):
    """The last daily close before today on Dukascopy's daily bars (the reference for the day's change)."""
    days = cached(("spot-days", symbol), 300, lambda: _duka(SPOT[symbol][2], "1d", 3, int(time.time() * 1000)))
    return days[-2]["close"] if len(days) >= 2 else None


def quote(symbol):
    """The live spot price, with the change against yesterday's Dukascopy daily close."""
    if symbol not in SPOT:
        return None
    try:
        price, ts = cached(("spot-q", symbol), QUOTE_TTL, lambda: _live(symbol))
    except Exception:
        return None
    try:
        prev = _prev_close(symbol)
    except Exception:
        prev = None
    return {"price": price, "prevClose": prev or price, "marketTime": int(ts), "currency": "USD"}


def older(symbol, interval, before):
    """One page of Dukascopy bars strictly before `before` (epoch s), for dragging the chart back."""
    if interval not in DUKA_INTERVAL:
        return []
    try:
        return [r for r in _duka(SPOT[symbol][2], interval, 500, before * 1000 - 1) if r["time"] < before]
    except Exception:
        return []


def candles(symbol, interval, rng):
    """The /api/candles payload from Dukascopy, or None when it can't be served (the caller falls back)."""
    interval, rng = resolve_interval_range(interval, rng, MAX_RANGE)
    seconds = RANGE_SECONDS.get(rng)
    if rng == "YTD":
        seconds = time.time() - calendar.timegm((time.gmtime().tm_year, 1, 1, 0, 0, 0))
    try:
        rows = cached(("spot-bars", symbol, interval, rng), BAR_TTL[interval],
                      lambda: history(symbol, interval, seconds or 86400))
    except Exception:
        return None
    if not rows:
        return None
    return {"symbol": symbol, "interval": interval, "range": rng, "candles": rows, "liveBars": 0,
            "source": "dukascopy", "feedChoice": True, "feed": "spot"}
