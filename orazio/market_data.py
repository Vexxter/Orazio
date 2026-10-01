"""Live quotes and the live bars built from them.

These two concerns share state deliberately: the live-bar aggregator is fed
by the same quote sources defined here (see LIVE_BAR_SOURCES), so splitting
them into separate modules would only relocate the coupling, not remove it.

Measured on 2026-09-21 with the market open:
  * Yahoo's chart endpoint ticks every ~11s for NSE names and is always <=11s old.
    (interval=1d&range=1d keeps the payload ~1 KB and still carries the live tick.)
  * NSE's allIndices feed only refreshes ~once a minute and runs 1-2 min behind the
    wall clock, so it is NOT used for quotes.
  * Yahoo's SENSEX (^BSESN) is delayed a flat ~15 min (licensing); BSE's own feed is
    current to the minute, so SENSEX comes from BSE.
Every source is best-effort and falls through to the next one.
"""
import threading
import time
from datetime import datetime
from urllib.parse import quote as url_quote

import requests
import yfinance as yf

from .bse_stream import BseStream
from .cache import cached
from .constants import (IST, LIVE_BAR_POLL_SEC, NAVER_INDEX_CODE, NSE_INDEX_BY_YAHOO,
                         QUOTE_CACHE_TTL, SINA_INDEX_CODE, TWSE_INDEX_CODE)
from .http_clients import bse_http, naver_http, sina_http, twse_http, yahoo_http
from .nse_client import nse_get


def yahoo_live_quote(symbol):
    def fetch():
        try:
            r = yahoo_http.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/" + url_quote(symbol, safe=""),
                params={"interval": "1d", "range": "1d"}, timeout=4,
            )
            r.raise_for_status()
            meta = r.json()["chart"]["result"][0]["meta"]
            return {
                "price": float(meta["regularMarketPrice"]),
                "prevClose": float(meta["chartPreviousClose"]),
                "marketTime": int(meta["regularMarketTime"]),
                "currency": meta.get("currency", ""),
            }
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            return None
    return cached(("yahoo", symbol), QUOTE_CACHE_TTL, fetch)


def _on_bse_tick(tick):
    record_live_tick("^BSESN", tick["value"], tick["t"], sampled=False)


bse_stream = BseStream(on_tick=_on_bse_tick)


def bse_live_quote(_symbol=None):
    # BSE's push stream ticks ~2x/second; the REST endpoint below refreshes once a
    # minute. Use the stream whenever it is alive and only fall back to REST.
    snap = bse_stream.snapshot() if bse_stream.fresh() else None
    if snap:
        return {"price": snap["value"], "prevClose": snap["prevClose"],
                "marketTime": snap["t"], "currency": "INR"}

    def fetch():
        try:
            r = bse_http.get("https://api.bseindia.com/RealTimeBseIndiaAPI/api/GetSensexData/w", timeout=4)
            r.raise_for_status()
            row = r.json()[0]
            # "dttm" looks like "21 Sep 26 | 12:28" (IST, minute resolution).
            stamp = datetime.strptime(row["dttm"], "%d %b %y | %H:%M").replace(tzinfo=IST)
            return {
                "price": float(row["ltp"].replace(",", "")),
                "prevClose": float(row["Prev_Close"].replace(",", "")),
                "marketTime": int(stamp.timestamp()),
                "currency": "INR",
            }
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            return None
    return cached(("bse", "sensex"), QUOTE_CACHE_TTL, fetch)


def yfinance_quote(symbol):
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        price = float(info["lastPrice"])
        prev = info.get("previousClose") if hasattr(info, "get") else info["previousClose"]
        if prev is None:
            closes = t.history(period="5d", interval="1d")["Close"].dropna()
            prev = float(closes.iloc[-2]) if len(closes) >= 2 else price
        return {"price": price, "prevClose": float(prev), "marketTime": None, "currency": info.get("currency", "")}
    except Exception:
        return None


def nse_index_quote(symbol):
    name = NSE_INDEX_BY_YAHOO.get(symbol)
    if not name:
        return None

    def fetch():
        d = nse_get("/api/allIndices")
        if not d:
            return None
        for row in d.get("data", []):
            if row.get("index") == name and row.get("last") is not None:
                try:
                    stamp = datetime.strptime(d.get("timestamp", ""), "%d-%b-%Y %H:%M").replace(tzinfo=IST)
                    return {"price": float(row["last"]), "prevClose": float(row["previousClose"]),
                            "marketTime": int(stamp.timestamp()), "currency": "INR"}
                except (ValueError, KeyError, TypeError):
                    return None
        return None
    return cached(("nse-index", symbol), QUOTE_CACHE_TTL, fetch)


def sina_index_quote(symbol):
    """China: Sina Finance's own quote widget endpoint — the free source every Chinese
    fintech site's front end uses, not an official/registered API. Its 's_' (simple)
    format is a handful of comma-separated fields, unchanged for over a decade:
    name, current, change, change%, volume, turnover. No timestamp is included, but the
    feed itself refreshes every few seconds, so "now" is close enough.
    """
    code = SINA_INDEX_CODE.get(symbol)
    if not code:
        return None

    def fetch():
        try:
            r = sina_http.get("https://hq.sinajs.cn/list=" + code, timeout=4)
            r.raise_for_status()
            raw = r.content.decode("gbk", errors="ignore").split('"')[1]
            fields = raw.split(",")
            price, change = float(fields[1]), float(fields[2])
            if price <= 0:
                return None
            return {"price": price, "prevClose": price - change, "marketTime": int(time.time()), "currency": "CNY"}
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            return None
    return cached(("sina", symbol), QUOTE_CACHE_TTL, fetch)


def naver_index_quote(symbol):
    """Korea: Naver Finance's own polling endpoint — the backend its live index widget
    calls client-side. Public JSON, no auth. Verified live shape:
    {"datas": [{"closePriceRaw": "6868.02", "compareToPreviousClosePriceRaw": "-2.79",
    "localTradedAt": "2026-09-30T11:55:53+09:00", ...}]} — the "Raw" fields are plain
    decimal strings (the non-Raw ones are comma-formatted for display).
    """
    code = NAVER_INDEX_CODE.get(symbol)
    if not code:
        return None

    def fetch():
        try:
            r = naver_http.get(f"https://polling.finance.naver.com/api/realtime/domestic/index/{code}", timeout=4)
            r.raise_for_status()
            row = r.json()["datas"][0]
            price = float(row["closePriceRaw"])
            change = float(row["compareToPreviousClosePriceRaw"])
            if price <= 0:
                return None
            market_time = int(datetime.fromisoformat(row["localTradedAt"]).timestamp())
            return {"price": price, "prevClose": price - change, "marketTime": market_time, "currency": "KRW"}
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            return None
    return cached(("naver", symbol), QUOTE_CACHE_TTL, fetch)


_twse_warmed_at = 0


def twse_index_quote(symbol):
    """Taiwan: TWSE's own live-quote widget backend (mis.twse.com.tw) — verified live,
    covers the TAIEX aggregate itself (ex_ch=tse_t00.tw), not just individual stocks.
    Needs a warm-up GET on the quote page first (same cookie-before-JSON shape as NSE)
    or it silently answers with an empty msgArray instead of an error.
    """
    code = TWSE_INDEX_CODE.get(symbol)
    if not code:
        return None

    def fetch():
        global _twse_warmed_at
        try:
            now = time.time()
            if now - _twse_warmed_at > 240:
                twse_http.get("https://mis.twse.com.tw/stock/index.jsp", timeout=5)
                _twse_warmed_at = now
            r = twse_http.get("https://mis.twse.com.tw/stock/api/getStockInfo.jsp",
                               params={"ex_ch": code, "json": 1, "delay": 0}, timeout=4)
            r.raise_for_status()
            row = (r.json().get("msgArray") or [{}])[0]
            z = row.get("z")
            price = float(z) if z not in (None, "-", "") else None
            prev = float(row["y"])
            if not price or not prev:
                return None
            stamp = row.get("tlong")
            market_time = int(int(stamp) / 1000) if stamp else int(time.time())
            return {"price": price, "prevClose": prev, "marketTime": market_time, "currency": "TWD"}
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            _twse_warmed_at = 0  # cookie may have gone stale — force a re-warm next call
            return None
    return cached(("twse", symbol), QUOTE_CACHE_TTL, fetch)


# Symbols whose best live source is not Yahoo.
SPECIAL_QUOTE_SOURCES = {
    "^BSESN": ("bse", bse_live_quote),
    "000300.SS": ("sina", sina_index_quote),
    "000001.SS": ("sina", sina_index_quote),
    "^KS11": ("naver", naver_index_quote),
    "^TWII": ("twse", twse_index_quote),
}

# ---------------------------------------------------------------------------
# Live bar aggregation.
# Yahoo delays SENSEX *bars* by ~15 minutes (the quote fix above only covered the
# price). There is no public intraday-bar feed for the index, so we build the recent
# bars ourselves: poll BSE every few seconds and fold each tick into a 1-minute OHLC
# bucket. /api/candles then splices these onto Yahoo's older, authoritative history.
# Coverage is "since this process started", which is why Yahoo still supplies history.
# ---------------------------------------------------------------------------
LIVE_BAR_SOURCES = {
    "^BSESN": bse_live_quote,
    "000300.SS": sina_index_quote, "000001.SS": sina_index_quote,
    "^KS11": naver_index_quote, "^TWII": twse_index_quote,
}
_live_bars = {}          # yahoo symbol -> {minute_epoch: [open, high, low, close]}
_live_bars_lock = threading.Lock()


def record_live_tick(symbol, price, market_time, sampled=True):
    """Fold one sample into its 1-minute bucket.

    Measured: BSE publishes exactly one SENSEX value per minute, so this is a sampled
    series, not a tick stream. A new bar therefore opens at the PREVIOUS sample —
    otherwise every candle would be flat (open == high == low == close). The high/low
    are the range across the samples we saw, not true intra-minute extremes.
    """
    minute = market_time - (market_time % 60)
    with _live_bars_lock:
        bars = _live_bars.setdefault(symbol, {})
        bar = bars.get(minute)
        if bar is None:
            earlier = [m for m in bars if m < minute]
            # `sampled` = once-a-minute REST values: open at the previous sample so bars
            # aren't flat. Real stream ticks open at the minute's first tick instead.
            start = bars[max(earlier)][3] if (sampled and earlier) else price
            bars[minute] = [start, max(start, price), min(start, price), price]
        else:
            bar[1] = max(bar[1], price)
            bar[2] = min(bar[2], price)
            bar[3] = price
        if len(bars) > 1200:  # ~a full session; drop the oldest
            for stale in sorted(bars)[:-900]:
                del bars[stale]


def live_bars_after(symbol, after_ts, step):
    """Our own bars strictly newer than `after_ts`, re-bucketed to `step` seconds."""
    with _live_bars_lock:
        minutes = dict(_live_bars.get(symbol, {}))
    buckets = {}
    for minute in sorted(minutes):
        if minute <= after_ts:
            continue
        o, h, l, c = minutes[minute]
        slot = minute - (minute % step)
        cur = buckets.get(slot)
        if cur is None:
            buckets[slot] = [o, h, l, c]
        else:
            cur[1] = max(cur[1], h)
            cur[2] = min(cur[2], l)
            cur[3] = c
    return [{"time": t, "open": o, "high": h, "low": l, "close": c, "volume": 0}
            for t, (o, h, l, c) in sorted(buckets.items())]


def _live_bar_poller():
    while True:
        for symbol, fetch in LIVE_BAR_SOURCES.items():
            try:
                # The stream records its own ticks; polling REST on top would only add
                # coarse once-a-minute samples to buckets that already hold real ticks.
                if symbol == "^BSESN" and bse_stream.fresh():
                    continue
                q = fetch(symbol)
                # Only record a tick the exchange published just now: a frozen
                # post-close quote must not keep extending flat bars forever.
                if q and q.get("marketTime") and time.time() - q["marketTime"] < 180:
                    record_live_tick(symbol, q["price"], q["marketTime"])
            except Exception:
                pass  # a transient source failure must never kill the poller
        time.sleep(LIVE_BAR_POLL_SEC)


def bse_raw_sensex():
    """SENSEX open + indicative close ('-' means not set). The push stream carries both
    live; the REST feed is the fallback."""
    snap = bse_stream.snapshot() if bse_stream.fresh() else None
    if snap:
        return {"open": snap["open"], "indicativeClose": snap["indicativeClose"]}

    def fetch():
        try:
            r = bse_http.get("https://api.bseindia.com/RealTimeBseIndiaAPI/api/GetSensexData/w", timeout=4)
            r.raise_for_status()
            row = r.json()[0]

            def num(v):
                try:
                    return float(str(v).replace(",", ""))
                except (TypeError, ValueError):
                    return None
            return {"open": num(row.get("I_open")), "indicativeClose": num(row.get("iclsprice"))}
        except (requests.RequestException, KeyError, IndexError, ValueError):
            return {}
    return cached(("bse-raw", "sensex"), QUOTE_CACHE_TTL, fetch) or {}


def start_live_bar_poller():
    threading.Thread(target=_live_bar_poller, daemon=True, name="live-bars").start()
