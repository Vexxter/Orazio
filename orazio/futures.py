"""The "Futures" commodity feed: real-time prices that track the CME/ICE futures, mixed by measured accuracy.

Free real-time CME/ICE data doesn't exist (the exchanges license it; CNBC, TradingView, Yahoo all run ~10 min
late), so futures come from perpetuals, which track a chosen contract month. Measured 21 Oct 2026 against real
CME/ICE trades at the same moment (CNBC stamps its delayed quotes with the true trade time), 26-42 trades each:

               Binance perp      Hyperliquid mark   Hyperliquid oracle   contract tracked
  WTI          +5.2c (sd 1.0c)   -3.2c (0.9c)       +0.4c (0.8c)         Dec (front)
  Brent        +4.4c (1.0c)      -5.6c (0.6c)       -0.6c (0.5c)         Jan (ICE 2nd month)
  Natural gas  +0.5c (0.1c)      -0.1c (0.0c)        0.0c (0.0c)         Dec (2nd month)
  Copper       +1.3c             +0.15c              +0.25c              Dec (front)
  Gold         -$10.5 vs COMEX   -$16.4             -$18.1 (= spot)
  Silver       -2c vs COMEX      -11c               -13c (= spot)

So oil, gas and copper use Hyperliquid's trade.xyz markets — the live price is the ORACLE (the underlying
futures price, no perp premium); the chart is its trade candles (the oracle has no history), a few cents off.
Gold and silver use Binance (commodities.py), which is closest to COMEX — Hyperliquid's metals track spot.
Hyperliquid's daily history only starts in early 2026, so 5Y/ALL charts fall back to Yahoo's CME history.
"""
import calendar
import time

import requests

from .cache import cached
from .constants import USER_AGENT
from .symbols import resolve_interval_range

API = "https://api.hyperliquid.xyz/info"
# Yahoo chart symbol -> Hyperliquid trade.xyz market
HL = {"CL=F": "xyz:CL", "BZ=F": "xyz:BRENTOIL", "NG=F": "xyz:NATGAS", "HG=F": "xyz:COPPER"}
CTX_TTL = 1
BAR_TTL = {"1m": 15, "5m": 30, "15m": 60, "1h": 120, "1d": 600, "1wk": 3600}
HL_INTERVAL = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "1d": "1d", "1wk": "1w"}
STEP = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400, "1wk": 7 * 86400}
RANGE_SECONDS = {"1D": 86400, "1W": 7 * 86400, "1M": 31 * 86400, "3M": 92 * 86400, "6M": 183 * 86400, "1Y": 366 * 86400}
PAGE = 5000              # candles per candleSnapshot reply
MAX_PAGES = 3
# Longer ranges escalate to a coarser bar; 5Y/ALL aren't served at all (history starts 2026).
MAX_RANGE = {"1m": "1W", "5m": "1M", "15m": "3M", "1h": "1Y", "1d": "1Y", "1wk": "1Y"}
_HEADERS = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}


def is_hl(symbol):
    return symbol in HL


def _post(body):
    r = requests.post(API, json=body, headers=_HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def _contexts():
    meta, ctxs = _post({"type": "metaAndAssetCtxs", "dex": "xyz"})
    return {a["name"]: c for a, c in zip(meta["universe"], ctxs)}


def parse_ctx(ctx, now):
    """trade.xyz asset context -> quote. Price is the oracle; the reference is the price 24 h ago (prevDayPx)."""
    price = float(ctx["oraclePx"])
    prev = float(ctx.get("prevDayPx") or price)
    return {"price": price, "prevClose": prev, "marketTime": int(now), "currency": "USD"}


def quote(symbol):
    if symbol not in HL:
        return None
    try:
        ctx = cached(("hl-ctx",), CTX_TTL, _contexts).get(HL[symbol])
        return parse_ctx(ctx, time.time()) if ctx else None
    except Exception:
        return None


def parse_candles(raw):
    return [{"time": int(c["t"] // 1000), "open": float(c["o"]), "high": float(c["h"]), "low": float(c["l"]),
             "close": float(c["c"]), "volume": float(c.get("v") or 0)} for c in raw]


def history(symbol, interval, start, end):
    """Trade candles from `start` to `end` (epoch s), paging forward PAGE candles at a time."""
    rows, t = [], start
    for _ in range(MAX_PAGES):
        page = parse_candles(_post({"type": "candleSnapshot", "req": {"coin": HL[symbol], "interval": HL_INTERVAL[interval],
                                                                       "startTime": int(t * 1000), "endTime": int(end * 1000)}}))
        page = [r for r in page if not rows or r["time"] > rows[-1]["time"]]
        if not page:
            break
        rows += page
        if len(page) < PAGE - 1:
            break
        t = rows[-1]["time"] + STEP[interval]
    return rows


def candles(symbol, interval, rng):
    """The /api/candles payload, or None when Hyperliquid can't serve it (5Y/ALL, or unreachable)."""
    if symbol not in HL or rng in ("5Y", "ALL"):
        return None
    interval, rng = resolve_interval_range(interval, rng, MAX_RANGE)
    now = time.time()
    seconds = RANGE_SECONDS.get(rng) or (now - calendar.timegm((time.gmtime().tm_year, 1, 1, 0, 0, 0)))   # YTD
    try:
        rows = cached(("hl-bars", symbol, interval, rng), BAR_TTL[interval], lambda: history(symbol, interval, now - seconds, now))
    except Exception:
        return None
    if not rows:
        return None
    return {"symbol": symbol, "interval": interval, "range": rng, "candles": rows, "liveBars": 0,
            "source": "hyperliquid", "feedChoice": True, "feed": "futures"}


def older(symbol, interval, before):
    """One page of candles before `before` (epoch s), for dragging the chart back."""
    if symbol not in HL or interval not in HL_INTERVAL:
        return []
    try:
        return history(symbol, interval, before - 500 * STEP[interval], before - 1)
    except Exception:
        return []
