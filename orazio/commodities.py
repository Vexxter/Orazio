"""Real-time commodity prices from Binance's public futures API.

Yahoo serves the CME commodity futures (CL=F, GC=F, ...) on the exchange's delayed feed: every
ticker measured 1 Oct 2026 was ~600 s old. Binance lists perpetual contracts on the same
commodities — gold, silver, WTI, Brent, natural gas, copper — and its public market-data API is free,
needs no key, and was 16 s old on the same measurement.

They are a different instrument, which decides how they are used:
  * A perpetual tracks the spot price; a CME future carries a roll/carry premium. Daily closes
    differed from Yahoo's front month by 0.7-2.4% on average (gold: spot was ~0.5% under the future).
  * They only started trading between Dec 2025 and Apr 2026, so history is 6-10 months.
So Binance serves what speed matters for — the live price and intraday charts (a 1500-bar kline
limit caps those at roughly 1M of 1h bars) — and everything longer, or anything Binance can't
serve, stays on Yahoo's CME history. The change shown is Binance's rolling 24 h change (a 24/7
market has no "yesterday's close"). If Binance is unreachable everything falls back to Yahoo.
"""
import requests

from . import binance_stream
from .cache import cached
from .constants import INTERVAL_SECONDS

API = "https://fapi.binance.com/fapi/v1"
# Yahoo chart symbol -> Binance perpetual
SYMBOLS = {"CL=F": "CLUSDT", "BZ=F": "BZUSDT", "GC=F": "XAUUSDT", "SI=F": "XAGUSDT", "NG=F": "NATGASUSDT", "HG=F": "COPPERUSDT"}
KLINE_LIMIT = 1500
INTRADAY_LADDER = ("1m", "5m", "15m", "1h")
RANGE_SECONDS = {"1D": 86400, "5D": 5 * 86400, "1M": 31 * 86400}   # a 24/7 market: "1D" is the last 24 hours
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


def is_commodity(symbol):
    return symbol in SYMBOLS


def pick_interval(requested, rng):
    """The finest bar size at or above `requested` that fits one kline request for this range, or
    None when Binance should not serve it (a long range, a daily request, an unknown interval)."""
    if rng not in RANGE_SECONDS or requested not in INTRADAY_LADDER:
        return None
    for interval in INTRADAY_LADDER[INTRADAY_LADDER.index(requested):]:
        if RANGE_SECONDS[rng] / INTERVAL_SECONDS[interval] <= KLINE_LIMIT:
            return interval
    return None


def parse_klines(raw):
    """Binance kline arrays -> chart rows. Open time is epoch ms; the value fields are strings."""
    return [{"time": int(k[0] // 1000), "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
             "close": float(k[4]), "volume": float(k[5])} for k in raw]


def parse_ticker(d):
    """24 h ticker -> the quote shape market_data's other sources use. prevClose is the rolling
    24-hour-ago price, so change/changePercent are 24 h figures."""
    price = float(d["lastPrice"])
    return {"price": price, "prevClose": price - float(d["priceChange"]),
            "marketTime": int(d["closeTime"] // 1000), "currency": "USD"}


def _get(path, params):
    try:
        r = requests.get(f"{API}/{path}", params=params, headers=_HEADERS, timeout=8)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def quote(symbol):
    """Binance quote. The REST ticker supplies the 24 h reference (prevClose) and is the fallback;
    when the websocket has a fresh price its price and time replace REST's, which is up to 2 s stale."""
    if symbol not in SYMBOLS:
        return None

    def fetch():
        d = _get("ticker/24hr", {"symbol": SYMBOLS[symbol]})
        try:
            return parse_ticker(d)
        except (KeyError, TypeError, ValueError):
            return None
    q = cached(("binance-quote", symbol), 2, fetch)
    if q is None:
        return None
    return with_live_trade(q, binance_stream.latest(symbol))


def with_live_trade(rest_quote, tick):
    """Overlay a websocket price onto the REST quote when it is newer. prevClose stays REST's."""
    if tick is None or tick["time"] // 1000 < rest_quote["marketTime"]:
        return rest_quote
    return {**rest_quote, "price": tick["price"], "marketTime": tick["time"] // 1000}


def _klines(symbol, interval, **window):
    raw = _get("klines", {"symbol": SYMBOLS[symbol], "interval": interval, "limit": KLINE_LIMIT, **window})
    try:
        return parse_klines(raw)
    except (TypeError, ValueError, IndexError):
        return None


def candles(symbol, requested_interval, rng):
    """(interval used, bars) when Binance should serve this chart request, else None."""
    interval = pick_interval(requested_interval, rng)
    if interval is None or symbol not in SYMBOLS:
        return None
    rows = cached(("binance-klines", symbol, interval, rng), 5, lambda: _klines(symbol, interval))
    if not rows:
        return None
    horizon = rows[-1]["time"] - RANGE_SECONDS[rng]
    return interval, [r for r in rows if r["time"] > horizon]


def history(symbol, interval, before):
    """Up to one request's worth of bars strictly older than `before` (epoch s), for scroll-back."""
    if symbol not in SYMBOLS or interval not in INTRADAY_LADDER:
        return []
    rows = _klines(symbol, interval, endTime=int(before) * 1000 - 1) or []
    return [r for r in rows if r["time"] < before]
