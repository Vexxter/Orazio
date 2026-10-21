"""Chart data: candles, older history for scroll-back, and the live quote."""
import time

import yfinance as yf
from flask import abort, jsonify, request

from .. import fno as fno_service
from .. import bonds, commodities, futures, gift_nifty, gsec, live_volume, market_data, poller, quotes, spot
from ..candles import df_to_rows, resample_weekly
from ..constants import HISTORY_PERIOD, INTERVAL_SECONDS, RANGE_ALIASES, RANGE_TO_PERIOD
from ..corporate_actions import adjust_candles_for_splits
from ..symbols import clean_symbol, resolve_interval_range
from . import bp

IST_OFFSET_SEC = 19800  # +5:30 — shifts an epoch so gmtime() yields the IST calendar day


def _ist_day(epoch):
    return time.gmtime(epoch + IST_OFFSET_SEC).tm_yday


def _last_session_rows(symbol, interval):
    """Yahoo answers period=1d with ZERO rows from the moment a new session date starts
    (00:00 exchange time) until the first bar prints — for NSE that is 09:00-09:15 IST, so
    every Indian chart read "No data" during pre-open. Fall back to the most recent
    session that has bars."""
    rows = df_to_rows(yf.download(symbol, period="5d", interval=interval, progress=False))
    if not rows:
        return rows
    last_day = _ist_day(rows[-1]["time"])
    return [r for r in rows if _ist_day(r["time"]) == last_day]


# ---- candles ---------------------------------------------------------------------
def _future_candles(symbol, interval, rng):
    try:
        payload = fno_service.candles(symbol, "1d" if interval == "1wk" else interval, rng)
    except ValueError as e:
        abort(404, description=str(e))
    if interval == "1wk":   # NSE has no weekly futures series: build it from the daily one
        payload = {**payload, "interval": "1wk", "candles": resample_weekly(payload["candles"])}
    return jsonify(payload)


def _gift_candles(interval, rng):
    """GIFT Nifty has no Yahoo ticker: intraday bars are the ones this app saved itself, daily
    history is NSE IX's official bhavcopy (see gift_nifty.chart)."""
    used, rows = gift_nifty.chart("1d" if interval == "1wk" else interval, rng)
    if interval == "1wk":
        used, rows = "1wk", resample_weekly(rows)
    return jsonify({"symbol": gift_nifty.SYMBOL, "interval": used, "range": rng, "candles": rows, "liveBars": 0})


def _yahoo_candles(symbol, requested_interval, requested_range, feed=None):
    interval, rng = resolve_interval_range(requested_interval, requested_range)
    df = yf.download(symbol, period=RANGE_TO_PERIOD[rng], interval=interval, progress=False)
    rows = df_to_rows(df)
    if not rows and rng == "1D" and interval in INTERVAL_SECONDS:
        rows = _last_session_rows(symbol, interval)
    rows = adjust_candles_for_splits(symbol, rows)

    # Splice in bars we built ourselves for feeds Yahoo publishes late (SENSEX), or — when Yahoo
    # returns nothing at all for this period/interval combo (it intermittently 0-rows ^BSESN at
    # period=1d while 5d works) — serve our own buffered live bars alone rather than "no data".
    live_added = 0
    if symbol in market_data.LIVE_BAR_SOURCES and interval in INTERVAL_SECONDS:
        anchor = rows[-1]["time"] if rows else 0
        extra = market_data.live_bars_after(symbol, anchor, INTERVAL_SECONDS[interval])
        rows += extra
        live_added = len(extra)

    # Yahoo's index volume is always 0; fill it from the running totals NSE publishes.
    live_volume.apply(symbol, rows, INTERVAL_SECONDS.get(interval, 86400))

    payload = {"symbol": symbol, "interval": interval, "range": rng, "candles": rows, "liveBars": live_added}
    if commodities.is_commodity(symbol):
        # Futures history the perpetuals can't serve (5Y/ALL, long daily ranges): Yahoo's CME futures. The live
        # price is a perpetual that can sit a little away from CME's contract, so the page mustn't fold it in.
        payload["liveFold"] = False
        payload["feedChoice"] = True
        payload["feed"] = "futures"
        payload["note"] = "Futures history: CME via Yahoo (the real-time futures feeds only go back to early 2026)"
    return jsonify(payload)


def _commodity_candles(symbol, interval, rng):
    """Real-time Binance bars when they can serve this request (intraday, up to ~1M); else None."""
    served = commodities.candles(symbol, interval, rng)
    if not served:
        return None
    used, rows = served
    return jsonify({"symbol": symbol, "interval": used, "range": rng, "candles": rows, "liveBars": 0, "source": "binance",
                    "feedChoice": True, "feed": "futures"})


@bp.route("/api/candles")
def candles():
    poller.ensure_poller()
    symbol = clean_symbol(request.args.get("symbol"))
    interval = request.args.get("interval", "1m")
    rng = request.args.get("range", "1D")
    rng = RANGE_ALIASES.get(rng, rng)
    if symbol.endswith("-FUT"):
        return _future_candles(symbol, interval, rng)
    if symbol == gift_nifty.SYMBOL:
        return _gift_candles(interval, rng)
    if bonds.is_bond(symbol):
        return jsonify(bonds.candles(symbol, interval, rng))
    if gsec.is_gsec(symbol):
        return jsonify(gsec.candles(symbol, interval, rng))
    feed = quotes.clean_feed(request.args.get("feed"))
    if commodities.is_commodity(symbol):
        f = quotes.effective_feed(symbol, feed)
        if f == "spot":
            payload = spot.candles(symbol, interval, rng)
            if payload is not None:
                return jsonify(payload)
            f = "futures"                      # Dukascopy unreachable: fall through to the futures feed
        if f == "futures":
            payload = futures.candles(symbol, interval, rng)         # oil, gas, copper: Hyperliquid
            if payload is not None:
                return jsonify(payload)
            response = _commodity_candles(symbol, interval, rng)     # gold, silver (or Hyperliquid down): Binance
            if response is not None:
                return response
    return _yahoo_candles(symbol, interval, rng, feed)


@bp.route("/api/candles/history")
def candles_history():
    symbol = clean_symbol(request.args.get("symbol"))
    interval = request.args.get("interval", "1m")
    if interval not in HISTORY_PERIOD:
        interval = "1m"
    try:
        before = int(request.args.get("before", ""))
    except ValueError:
        abort(400, description="before must be a unix timestamp")
    # ponytail: bond yields don't scroll back past the range loaded; pick a longer range instead. Add a CNBC
    # bars page here if that's wanted.
    if symbol.endswith("-FUT") or symbol == gift_nifty.SYMBOL or bonds.is_bond(symbol) or gsec.is_gsec(symbol):
        return jsonify({"symbol": symbol, "interval": interval, "candles": [], "exhausted": True})

    if request.args.get("source") == "dukascopy" and spot.has_spot(symbol):   # spot chart: page back on Dukascopy
        rows = spot.older(symbol, interval, before)
        return jsonify({"symbol": symbol, "interval": interval, "candles": rows, "exhausted": len(rows) == 0})

    if request.args.get("source") == "hyperliquid" and futures.is_hl(symbol):   # futures chart: same market
        rows = futures.older(symbol, interval, before)
        return jsonify({"symbol": symbol, "interval": interval, "candles": rows, "exhausted": len(rows) == 0})

    if request.args.get("source") == "binance":  # the chart on screen is Binance's: scroll back on the same instrument
        rows = commodities.history(symbol, interval, before)
        return jsonify({"symbol": symbol, "interval": interval, "candles": rows, "exhausted": len(rows) == 0})

    df = yf.download(symbol, period=HISTORY_PERIOD[interval], interval=interval, progress=False)
    rows = [r for r in adjust_candles_for_splits(symbol, df_to_rows(df)) if r["time"] < before]
    # One page per call: the most recent trading day strictly before `before`, so the frontend
    # can prepend it and the session-boundary marker lands cleanly.
    if rows:
        last_day = _ist_day(rows[-1]["time"])
        rows = [r for r in rows if _ist_day(r["time"]) == last_day]
    return jsonify({"symbol": symbol, "interval": interval, "candles": rows, "exhausted": len(rows) == 0})


# ---- quote -----------------------------------------------------------------------
@bp.route("/api/quote")
def quote():
    poller.ensure_poller()
    payload = quotes.quote_payload(clean_symbol(request.args.get("symbol")), feed=quotes.clean_feed(request.args.get("feed")))
    if payload is None:
        abort(502, description="no quote source available")
    return jsonify(payload)
