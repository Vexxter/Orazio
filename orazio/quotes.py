"""The live quote for a chart symbol: which source to ask, and the JSON the page receives.

Shared by GET /api/quote and the push stream (GET /api/stream/quote) so the two can never disagree.
Sources are tried best-first and the winner is named in `source`, which the status bar shows.
"""
import time

from . import binance_stream, bonds, commodities, fno as fno_service, futures, gift_nifty, gsec, market_data, spot
from .constants import NSE_INDEX_BY_YAHOO, YAHOO_STALE_SEC


FEEDS = ("spot", "futures")
FEED_ALIASES = {"binance": "futures"}   # the futures feed was Binance-only before it became a mix


def clean_feed(raw):
    """The `feed` query parameter: which source the user chose for a commodity. Anything else = default."""
    raw = FEED_ALIASES.get(raw, raw)
    return raw if raw in FEEDS else None


def effective_feed(symbol, feed):
    """The source a commodity is actually served from: the user's choice, else spot — and futures wherever
    there is no spot feed."""
    f = feed or "spot"
    return "futures" if f == "spot" and not spot.has_spot(symbol) else f


def _futures_quote(symbol):
    """Hyperliquid's oracle for oil, gas and copper; Binance for gold and silver (see futures.py)."""
    if futures.is_hl(symbol):
        q = futures.quote(symbol)
        if q is not None:
            return "hyperliquid", q
    q = commodities.quote(symbol)
    return ("binance", q) if q is not None else (None, None)


def pick_quote(symbol, feed=None):
    """(source name, quote dict or None) for a chart symbol, trying the best source first.
    Commodities: `feed` is "spot" (the default) or "futures"; spot falls back to futures, and futures finally to
    Yahoo's delayed CME futures, if a source is unreachable."""
    if symbol.endswith("-FUT"):
        return "nse-fno", fno_service.quote(symbol)
    if symbol == gift_nifty.SYMBOL:
        return "nse-gift", gift_nifty.quote()
    if bonds.is_bond(symbol):
        return "cnbc", bonds.quote(symbol)
    if gsec.is_gsec(symbol):
        return "ccil", gsec.quote(symbol)

    if commodities.is_commodity(symbol):
        feed = effective_feed(symbol, feed)
        if feed == "spot":
            q = spot.quote(symbol)
            if q is not None:
                return spot.SPOT[symbol][0], q           # spot, real-time: "swissquote" or "dukascopy"
        source, q = _futures_quote(symbol)               # futures chosen, or spot unreachable
        if q is not None:
            return source, q                             # real-time; Yahoo's CME feed below is ~10 min old

    special = market_data.SPECIAL_QUOTE_SOURCES.get(symbol)  # BSE for SENSEX, Sina/Naver/TWSE for Asia
    if special:
        source, fetch = special
        q = fetch(symbol)
        if q is not None:
            return source, q

    q = market_data.yahoo_live_quote(symbol)
    if q is not None:
        # Yahoo's NSE-index tick goes stale after the auction; NSE's own feed then carries the close.
        if symbol in NSE_INDEX_BY_YAHOO and time.time() - q["marketTime"] > YAHOO_STALE_SEC:
            nse_q = market_data.nse_index_quote(symbol)
            if nse_q and nse_q["marketTime"] > q["marketTime"]:
                return "nse", nse_q
        return "yahoo", q
    return "yfinance", market_data.yfinance_quote(symbol)


def quote_payload(symbol, now=None, feed=None):
    """The JSON the page receives for a quote, or None when no source has one."""
    source, q = pick_quote(symbol, feed)
    if q is None:
        return None
    now = int(now or time.time())
    price, prev_close = q["price"], q["prevClose"]
    change = price - prev_close
    return {
        "symbol": symbol,
        "price": price,
        "time": now,
        "marketTime": q["marketTime"],
        "delaySec": max(0, now - q["marketTime"]) if q["marketTime"] else None,
        "change": change,
        "changePercent": (change / prev_close) * 100 if prev_close else 0,
        "currency": q["currency"],
        "source": source,
    }


def is_pushed(symbol, feed=None):
    """True when the quote for this symbol comes from an in-memory push feed (so it is free to
    re-read several times a second); everything else sits behind a network round trip and cache."""
    return ((binance_stream.is_streaming(symbol) and not futures.is_hl(symbol)
             and effective_feed(symbol, clean_feed(feed)) == "futures") or symbol == "^BSESN")
