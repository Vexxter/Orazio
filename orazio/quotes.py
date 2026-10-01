"""The live quote for a chart symbol: which source to ask, and the JSON the page receives.

Shared by GET /api/quote and the push stream (GET /api/stream/quote) so the two can never disagree.
Sources are tried best-first and the winner is named in `source`, which the status bar shows.
"""
import time

from . import binance_stream, commodities, fno as fno_service, gift_nifty, market_data
from .constants import NSE_INDEX_BY_YAHOO, YAHOO_STALE_SEC


FEEDS = ("binance", "yahoo")


def clean_feed(raw):
    """The `feed` query parameter: which source the user chose for a commodity. Anything else = default."""
    return raw if raw in FEEDS else None


def pick_quote(symbol, feed=None):
    """(source name, quote dict or None) for a chart symbol, trying the best source first.
    `feed="yahoo"` makes a commodity use Yahoo's delayed CME futures instead of the Binance perpetual."""
    if symbol.endswith("-FUT"):
        return "nse-fno", fno_service.quote(symbol)
    if symbol == gift_nifty.SYMBOL:
        return "nse-gift", gift_nifty.quote()

    if commodities.is_commodity(symbol):
        if feed == "yahoo":
            q = market_data.yahoo_live_quote(symbol)
            if q is not None:
                return "yahoo-cme", q                    # the user asked for the CME futures feed, ~10 min old
        else:
            q = commodities.quote(symbol)
            if q is not None:
                return "binance", q                      # real-time; Yahoo's CME feed is ~10 min old

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
    return (binance_stream.is_streaming(symbol) and feed != "yahoo") or symbol == "^BSESN"
