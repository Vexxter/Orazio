"""Closing-auction (CAS) views: the CAS panel, the live movement chart, and the stock-by-stock feed."""
import time
from datetime import datetime

from flask import abort, jsonify, request

from .. import cas, market_data, poller
from ..constants import IST, NO_AUCTION_ALIASES, NSE_INDEX_NAMES, QUICK_INDICES
from ..nse_client import nse_get
from . import bp


def _pct(value, base):
    """Percent change of `value` against `base`, or None when either is missing/zero."""
    return (value - base) / base * 100 if (value and base) else None


def _nse_index_row(alias, r):
    prev = r.get("previousClose") or 0
    open_ = r.get("open") or 0
    icls = r.get("indicativeClose") or 0
    return {
        "alias": alias, "available": True, "source": "nse",
        "prevClose": prev,
        "open": open_ or None,
        "openChangePct": _pct(open_, prev),
        "indicativeClose": icls or None,
        "indicativeClosePct": _pct(icls, prev),
        "last": r.get("last"),
    }


def _sensex_row():
    """BSE publishes the same two numbers (open, indicative close) for SENSEX on its own feed."""
    q = market_data.bse_live_quote(None) or {}
    raw = market_data.bse_raw_sensex()
    prev = q.get("prevClose")
    return {
        "alias": "SENSEX", "available": bool(q), "source": "bse",
        "prevClose": prev,
        "open": raw.get("open"),
        "openChangePct": _pct(raw.get("open"), prev),
        "indicativeClose": raw.get("indicativeClose"),
        "indicativeClosePct": _pct(raw.get("indicativeClose"), prev),
        "last": q.get("price"),
    }


def _index_rows(by_name):
    rows = []
    for _label, alias in QUICK_INDICES:
        if alias in NO_AUCTION_ALIASES:
            continue
        nse_name = NSE_INDEX_NAMES.get(alias)
        if nse_name and nse_name in by_name:
            rows.append(_nse_index_row(alias, by_name[nse_name]))
        elif alias == "SENSEX":
            rows.append(_sensex_row())
        else:
            rows.append({"alias": alias, "available": False, "reason": "No public closing-auction feed for this market"})
    return rows


def _auction_breadth(phase):
    if phase not in ("pre-open", "closing-auction"):
        return None
    pre = nse_get("/api/market-data-pre-open", {"key": "FO"})
    if not pre:
        return None
    return {"advances": pre.get("advances"), "declines": pre.get("declines"),
            "unchanged": pre.get("unchanged"), "tradedValue": pre.get("totalTradedValue"),
            "asOf": pre.get("timestamp")}


@bp.route("/api/cas")
def cas_route():
    poller.ensure_poller()
    now_ist = datetime.now(IST)
    clock_phase, seconds, stage, session_label = cas.cas_phase(now_ist)
    nse_phase, nse_message, indicative = cas.nse_session()
    # NSE wins when it names a session; the clock only supplies the countdown.
    phase = nse_phase or clock_phase
    if nse_phase and nse_phase != clock_phase:
        seconds = None

    by_name = {row.get("index"): row for row in (cas.all_indices() or {}).get("data", [])}

    return jsonify({
        "phase": phase,
        "clockPhase": clock_phase,
        "stage": stage,
        "sessionLabel": session_label,
        "secondsRemaining": seconds,
        "serverTime": int(time.time()),
        # Straight from NSE, so the UI can show the session's real name instead of whatever our
        # hard-coded windows assume.
        "nseStatus": nse_message,
        "indicativeNifty": indicative,
        "windows": {s["phase"]: "%02d:%02d-%02d:%02d IST" % (s["start"] + s["end"]) for s in cas.CAS_SESSIONS},
        "breadth": _auction_breadth(phase),
        "indices": _index_rows(by_name),
    })


@bp.route("/api/cas/movement")
def cas_movement():
    poller.ensure_poller()
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


def _closing_auction_response(payload, cas_rows, want_symbol, phase, stage, seconds):
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


def _preopen_response(feed, want_symbol, key, phase, stage, seconds):
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
        "breadth": {"advances": feed.get("advances"), "declines": feed.get("declines"),
                    "unchanged": feed.get("unchanged"), "tradedValue": feed.get("totalTradedValue")},
        "rows": rows,
    })


@bp.route("/api/cas/feed")
def cas_feed():
    """The auction feed itself, stock by stock.

    During the closing auction this is NSE's CAS feed (~210 F&O names). Otherwise it is the
    pre-open feed, which keeps serving the last window's snapshot after it closes - so `source`
    and `live` tell the client exactly what it is looking at. `key=FO|ALL` only applies to the
    pre-open feed. With `symbol=`, one stock's order book.
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
    if cas_rows or phase == "closing-auction":
        return _closing_auction_response(payload, cas_rows, want_symbol, phase, stage, seconds)

    # pre-open: live 09:00-09:15, otherwise the last snapshot
    feed = cas.cas_feed_payload(key)
    if not feed:
        return jsonify({"available": False, "reason": "NSE pre-open feed unreachable", "rows": []})
    return _preopen_response(feed, want_symbol, key, phase, stage, seconds)
