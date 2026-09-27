"""HTTP routes. Each view is thin glue: parse the request, call a service
function, shape the JSON response — no business logic lives here."""
import time
from datetime import datetime

import requests
import yfinance as yf
from flask import Blueprint, abort, current_app, jsonify, request

from . import cas, constituents as constituents_service, market_data, movers as movers_service
from .candles import df_to_rows
from .constants import (FUTURES_MAP, FUTURES_META, HISTORY_PERIOD, INTERVAL_SECONDS,
                         NSE_INDEX_BY_YAHOO, NSE_INDEX_NAMES, QUICK_INDICES, RANGE_TO_PERIOD,
                         YAHOO_STALE_SEC, IST)
from .nse_client import nse_get
from .poller import ensure_poller
from .symbols import clean_symbol, resolve_interval_range

bp = Blueprint("orazio", __name__)


@bp.route("/")
def index():
    return current_app.send_static_file("index.html")


@bp.route("/api/config")
def config():
    return jsonify({
        "quickIndices": [alias for _, alias in QUICK_INDICES],
        "futuresMap": FUTURES_MAP,
        "futuresMeta": FUTURES_META,
    })


@bp.route("/api/candles")
def candles():
    ensure_poller()
    symbol = clean_symbol(request.args.get("symbol"))
    requested_interval = request.args.get("interval", "1m")
    requested_range = request.args.get("range", "1D")
    interval, rng = resolve_interval_range(requested_interval, requested_range)
    period = RANGE_TO_PERIOD[rng]

    df = yf.download(symbol, period=period, interval=interval, progress=False)
    rows = df_to_rows(df)

    # Splice in bars we built ourselves for feeds Yahoo publishes late (SENSEX), or —
    # when Yahoo returns nothing at all for this period/interval combo (observed: it
    # intermittently 0-rows `^BSESN` at period=1d while 5d works fine for the same
    # ticker) — serve our own buffered live bars alone rather than showing "no data"
    # while a live BSE feed is sitting right there in memory.
    live_added = 0
    if symbol in market_data.LIVE_BAR_SOURCES and interval in INTERVAL_SECONDS:
        anchor = rows[-1]["time"] if rows else 0
        extra = market_data.live_bars_after(symbol, anchor, INTERVAL_SECONDS[interval])
        rows += extra
        live_added = len(extra)

    return jsonify({
        "symbol": symbol,
        "interval": interval,
        "range": rng,
        "candles": rows,
        "liveBars": live_added,
    })


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

    df = yf.download(symbol, period=HISTORY_PERIOD[interval], interval=interval, progress=False)
    rows = [r for r in df_to_rows(df) if r["time"] < before]
    # One page per call: the most recent trading day strictly before `before`, so the
    # frontend can prepend it and the session-boundary marker lands cleanly.
    if rows:
        last_day = time.gmtime(rows[-1]["time"] + 19800).tm_yday  # +5:30 for IST day boundary
        rows = [r for r in rows if time.gmtime(r["time"] + 19800).tm_yday == last_day]

    return jsonify({
        "symbol": symbol,
        "interval": interval,
        "candles": rows,
        "exhausted": len(rows) == 0,
    })


@bp.route("/api/quote")
def quote():
    ensure_poller()
    symbol = clean_symbol(request.args.get("symbol"))

    source, q = None, None
    if symbol in market_data.SPECIAL_QUOTE_SOURCES:
        source, fn = market_data.SPECIAL_QUOTE_SOURCES[symbol]
        q = fn(symbol)
    if q is None:
        source, q = "yahoo", market_data.yahoo_live_quote(symbol)
        if q is not None and symbol in NSE_INDEX_BY_YAHOO and time.time() - q["marketTime"] > YAHOO_STALE_SEC:
            nse_q = market_data.nse_index_quote(symbol)
            if nse_q and nse_q["marketTime"] > q["marketTime"]:
                source, q = "nse", nse_q
    if q is None:
        source, q = "yfinance", market_data.yfinance_quote(symbol)
    if q is None:
        abort(502, description="no quote source available")

    now = int(time.time())
    price, prev_close = q["price"], q["prevClose"]
    change = price - prev_close
    return jsonify({
        "symbol": symbol,
        "price": price,
        "time": now,
        "marketTime": q["marketTime"],
        "delaySec": max(0, now - q["marketTime"]) if q["marketTime"] else None,
        "change": change,
        "changePercent": (change / prev_close) * 100 if prev_close else 0,
        "currency": q["currency"],
        "source": source,
    })


@bp.route("/api/breadth")
def breadth():
    ensure_poller()
    return jsonify({"indices": cas.breadth_rows() + constituents_service.breadth_rows()})


@bp.route("/api/cas")
def cas_route():
    ensure_poller()
    now_ist = datetime.now(IST)
    clock_phase, seconds, stage, session_label = cas.cas_phase(now_ist)
    nse_phase, nse_message, indicative = cas.nse_session()
    # NSE wins when it names a session; the clock only supplies the countdown.
    phase = nse_phase or clock_phase
    if nse_phase and nse_phase != clock_phase:
        seconds = None

    all_idx = cas.all_indices() or {}
    by_name = {row.get("index"): row for row in all_idx.get("data", [])}

    rows = []
    for _label, alias in QUICK_INDICES:
        nse_name = NSE_INDEX_NAMES.get(alias)
        if nse_name and nse_name in by_name:
            r = by_name[nse_name]
            prev = r.get("previousClose") or 0
            open_ = r.get("open") or 0
            icls = r.get("indicativeClose") or 0
            rows.append({
                "alias": alias, "available": True, "source": "nse",
                "prevClose": prev,
                "open": open_ or None,
                "openChangePct": ((open_ - prev) / prev * 100) if (open_ and prev) else None,
                "indicativeClose": icls or None,
                "indicativeClosePct": ((icls - prev) / prev * 100) if (icls and prev) else None,
                "last": r.get("last"),
            })
            continue
        if alias == "SENSEX":
            # BSE publishes the same two numbers for SENSEX on its own feed.
            q = market_data.bse_live_quote(None) or {}
            raw = market_data.bse_raw_sensex()
            icls = raw.get("indicativeClose")
            prev = q.get("prevClose")
            rows.append({
                "alias": alias, "available": bool(q), "source": "bse",
                "prevClose": prev,
                "open": raw.get("open"),
                "openChangePct": ((raw["open"] - prev) / prev * 100) if (raw.get("open") and prev) else None,
                "indicativeClose": icls,
                "indicativeClosePct": ((icls - prev) / prev * 100) if (icls and prev) else None,
                "last": q.get("price"),
            })
            continue
        rows.append({"alias": alias, "available": False,
                     "reason": "No public call-auction feed for this market"})

    breadth = None
    if phase in ("pre-open", "closing-auction"):
        pre = nse_get("/api/market-data-pre-open", {"key": "FO"})
        if pre:
            breadth = {
                "advances": pre.get("advances"), "declines": pre.get("declines"),
                "unchanged": pre.get("unchanged"), "tradedValue": pre.get("totalTradedValue"),
                "asOf": pre.get("timestamp"),
            }

    return jsonify({
        "phase": phase,
        "clockPhase": clock_phase,
        "stage": stage,
        "sessionLabel": session_label,
        "secondsRemaining": seconds,
        "serverTime": int(time.time()),
        # Straight from NSE, so the UI can show the session's real name instead of
        # whatever our hard-coded windows assume.
        "nseStatus": nse_message,
        "indicativeNifty": indicative,
        "windows": {s["phase"]: "%02d:%02d-%02d:%02d IST" % (s["start"] + s["end"])
                    for s in cas.CAS_SESSIONS},
        "breadth": breadth,
        "indices": rows,
    })


@bp.route("/api/cas/movement")
def cas_movement():
    ensure_poller()
    now_ist = datetime.now(IST)
    clock_phase, seconds, stage, _label = cas.cas_phase(now_ist)
    nse_phase, nse_message, _ind = cas.nse_session()
    phase = nse_phase or clock_phase
    ref_epoch = cas.cas_reference_epoch(now_ist)
    window_from = ref_epoch - 600   # 10 minutes of pre-auction context

    out = []
    for alias in ("NIFTY", "BANKNIFTY", "NIFTYIT", "SENSEX"):
        if alias == "SENSEX":
            snap = market_data.bse_stream.snapshot()
            raw = market_data.bse_stream.series(20000)
            source, live = "BSE live stream", market_data.bse_stream.fresh()
            prev = snap and snap["prevClose"]
        else:
            raw = list(cas.nse_series(alias))
            source, live = "Yahoo tick + NSE indicative", bool(raw)
            prev = cas.nse_prev_close(alias)
        points = [[t, v, ind] for t, v, ind in raw]
        ref = cas.cas_reference(alias, now_ist, points)
        recent = [pt for pt in points if pt[0] >= window_from][-3000:]
        last = points[-1] if points else None
        out.append({
            "alias": alias, "available": bool(points), "source": source, "live": live,
            "prevClose": prev, "last": last and last[1], "indicative": last and last[2],
            "reference": ref, "points": recent,
        })

    return jsonify({
        "phase": phase, "stage": stage, "secondsRemaining": seconds,
        "nseStatus": nse_message, "serverTime": int(time.time()),
        "referenceAt": ref_epoch, "referenceLocked": (now_ist.hour, now_ist.minute) >= (15, 15),
        "stream": {"connected": market_data.bse_stream.connected, "error": market_data.bse_stream.last_error},
        "indices": out,
    })


@bp.route("/api/cas/feed")
def cas_feed():
    """The auction feed itself, stock by stock.

    During the closing auction this is NSE's CAS feed (~210 F&O names). Otherwise it is
    the pre-open feed, which keeps serving the last window's snapshot after it closes -
    so `source` and `live` tell the client exactly what it is looking at.
    `key=FO|ALL` only applies to the pre-open feed. With `symbol=`, one stock's order book.
    """
    key = (request.args.get("key") or "FO").upper()
    if key not in ("FO", "ALL"):
        abort(400, description="key must be FO or ALL")
    want_symbol = (request.args.get("symbol") or "").strip().upper()

    clock_phase, seconds, stage, _label = cas.cas_phase(datetime.now(IST))
    nse_phase, _msg, _ind = cas.nse_session()
    phase = nse_phase or clock_phase

    payload = cas.cas_payload() or {}
    cas_rows = cas.normalise_cas_rows(payload)

    # ---- closing auction -------------------------------------------------------
    if cas_rows or phase == "closing-auction":
        if want_symbol:
            for r in cas_rows:
                if r["symbol"].upper() == want_symbol:
                    return jsonify({"available": True, "source": "cas", "symbol": r["symbol"],
                                    "iep": r.get("iep"), "ladder": cas.normalise_cas_book(r["orderBook"]),
                                    "updated": payload.get("timestamp")})
            return jsonify({"available": False, "reason": "no order book for this symbol yet", "ladder": []})
        return jsonify({
            "available": True, "source": "cas", "live": bool(cas_rows) or phase == "closing-auction",
            "phase": phase, "stage": stage, "secondsRemaining": seconds,
            "asOf": payload.get("timestamp"), "status": payload.get("status"), "statusMsg": payload.get("statusMsg"),
            "eligible": len(payload.get("symbols") or []),
            "totals": {"quantity": payload.get("totalQuantity"), "value": payload.get("totalValue"),
                       "indicativeQuantity": payload.get("indicativeTotalQuantity"),
                       "indicativeValue": payload.get("indicativeTotalValue")},
            "note": None if cas_rows else "The auction is running, but NSE has not published order data yet (the first stage only sets the reference price).",
            "rows": cas_rows,
        })

    # ---- pre-open (live 09:00-09:15, otherwise the last snapshot) ---------------
    feed = cas.cas_feed_payload(key)
    if not feed:
        return jsonify({"available": False, "reason": "NSE pre-open feed unreachable", "rows": []})

    if want_symbol:
        for row in feed.get("data", []):
            meta, pre = row.get("metadata", {}), row.get("detail", {}).get("preOpenMarket", {})
            if meta.get("symbol", "").upper() != want_symbol:
                continue
            ladder = [{"price": r.get("price"), "buyQty": r.get("buyQty"),
                       "sellQty": r.get("sellQty"), "flag": None, "isIep": bool(r.get("iep"))}
                      for r in pre.get("preopen", [])]
            return jsonify({"available": True, "source": "pre-open", "symbol": meta.get("symbol"),
                            "iep": pre.get("IEP"), "ladder": ladder,
                            "atoBuy": pre.get("atoBuyQty"), "atoSell": pre.get("atoSellQty"),
                            "updated": pre.get("lastUpdateTime")})
        return jsonify({"available": False, "reason": "symbol not in this auction feed", "ladder": []})

    rows = []
    for row in feed.get("data", []):
        meta, pre = row.get("metadata", {}), row.get("detail", {}).get("preOpenMarket", {})
        if not meta.get("symbol"):
            continue
        rows.append({
            "symbol": meta["symbol"], "iep": pre.get("IEP"), "prevClose": pre.get("prevClose"),
            "change": pre.get("Change"), "pChange": pre.get("perChange"),
            "finalQuantity": pre.get("finalQuantity"),
            "buyQty": pre.get("totalBuyQuantity"), "sellQty": pre.get("totalSellQuantity"),
            "atoBuy": pre.get("atoBuyQty"), "atoSell": pre.get("atoSellQty"),
        })

    return jsonify({
        "available": True, "source": "pre-open", "key": key, "phase": phase,
        "stage": stage, "secondsRemaining": seconds,
        "asOf": feed.get("timestamp"), "live": phase == "pre-open",
        "breadth": {
            "advances": feed.get("advances"), "declines": feed.get("declines"),
            "unchanged": feed.get("unchanged"), "tradedValue": feed.get("totalTradedValue"),
        },
        "rows": rows,
    })


@bp.route("/api/movers")
def movers_route():
    universe = request.args.get("universe") or "allSec"
    # NIFTY/BANKNIFTY/allSec come live from NSE (movers.py). SENSEX/DOWJONES/SPX/CHINA
    # have no such feed, so they're computed from the same constituent data /api/breadth
    # already polls (orazio/constituents.py) rather than a second, duplicate fetch.
    if universe in constituents_service.CONSTITUENT_ALIASES:
        cached = constituents_service.movers_for(universe)
        if not cached:
            return jsonify({"available": False, "universe": universe, "gainers": [], "losers": []})
        return jsonify({"available": True, "universe": universe, **cached})
    return jsonify(movers_service.movers(universe))


@bp.route("/api/search")
def search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 1:
        return jsonify([])
    # Yahoo Finance's own public symbol-search endpoint (same one their site's search
    # box calls) — not a third-party site, no anti-bot bypass involved.
    try:
        resp = requests.get(
            "https://query1.finance.yahoo.com/v1/finance/search",
            params={"q": q, "quotesCount": 8, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        resp.raise_for_status()
        quotes = resp.json().get("quotes", [])
    except (requests.RequestException, ValueError):
        return jsonify([])
    results = [
        {
            "symbol": item.get("symbol"),
            "name": item.get("shortname") or item.get("longname") or item.get("symbol"),
            "exchange": item.get("exchange"),
            "type": item.get("quoteType"),
        }
        for item in quotes
        if item.get("symbol")
    ]
    return jsonify(results)


def _option_rows(df):
    cols = ["strike", "lastPrice", "bid", "ask", "volume", "openInterest", "impliedVolatility"]
    return [
        {c: (None if c not in row or row[c] != row[c] else float(row[c])) for c in cols}
        for row in df.to_dict("records")
    ]


@bp.route("/api/options")
def options():
    symbol = clean_symbol(request.args.get("symbol"))
    t = yf.Ticker(symbol)

    try:
        expiries = list(t.options)
    except Exception as e:
        return jsonify({"available": False, "reason": str(e)[:200], "expiries": []})

    if not expiries:
        return jsonify({
            "available": False,
            "reason": "no option chain for this symbol",
            "expiries": [],
        })

    expiry = request.args.get("expiry") or expiries[0]
    if expiry not in expiries:
        abort(400, description="unknown expiry for this symbol")

    chain = t.option_chain(expiry)
    return jsonify({
        "available": True,
        "symbol": symbol,
        "expiry": expiry,
        "expiries": expiries,
        "calls": _option_rows(chain.calls),
        "puts": _option_rows(chain.puts),
    })
