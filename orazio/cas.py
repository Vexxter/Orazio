"""Call Auction Session (CAS): pre-open, closing auction, and post-market.

Pre-open  09:00-09:15 IST: orders collected 09:00-09:08, matched 09:08-09:12.
  Price discovery is real here, and NSE publishes each stock's IEP (indicative
  equilibrium price). The index level it implies shows up as that index's `open`.
Post-close 15:40-16:00 IST: this is NOT price discovery — it is trading AT the
  already-determined close, so there is no IEP. What is meaningful is the
  indicative/official closing value, which NSE and BSE both publish.
Only NSE/BSE indices have a public auction feed; the rest are reported as such
rather than filled with a guess.

Verified against NSE and broker documentation (Sept 2026), not assumed:
  SEBI circular HO/47/11/11(3)2025-MRD-POD2/I/2765/2026 (16 Jan 2026) introduced the
  Closing Auction Session, live from 3 August 2026, for F&O-eligible stocks only.
  Continuous trading in those names now STOPS at 15:15 — it does not run to 15:30.
  Non-F&O stocks keep the old VWAP close and trade through to 15:30.
"""
import json
import os
import tempfile
import threading
import time
from collections import deque
from datetime import datetime

import yfinance as yf

from .cache import cached
from .candles import df_to_rows
from .constants import (CAS_REFERENCE_AT, CAS_SESSIONS, IST, NSE_INDEX_NAMES, NSE_POLL_SEC,
                         QUOTE_CACHE_TTL, YAHOO_INDEX_SYMBOL)
from .market_data import bse_stream, yahoo_live_quote
from .nse_client import nse_get

# The reference price is locked once for the day and the chart history lives in memory, so a
# server restart (e.g. Flask's debug reloader restarting on every edit) would silently wipe
# both mid-auction. Persist them every few seconds and reload on start.
SEED_FILE = os.path.join(tempfile.gettempdir(), "orazio_cas_seed.json")

_nse_series = {alias: deque(maxlen=6000) for alias in NSE_INDEX_NAMES}   # (t, last, indicative)
_nse_prev = {}
_nse_started = False
_cas_reference = {}   # (yyyy-mm-dd, alias) -> {"value","t","source"}


def _mins(hm):
    return hm[0] * 60 + hm[1]


def cas_phase(now_ist):
    """Which auction window we are in, its current stage, and seconds to its start/end.

    Returns (phase, seconds, stage, label). `phase` is a session name while one is
    running, otherwise "waiting:<next session>".
    """
    mins = now_ist.hour * 60 + now_ist.minute + now_ist.second / 60
    weekday = now_ist.weekday() < 5

    if weekday:
        for sess in CAS_SESSIONS:
            if _mins(sess["start"]) <= mins < _mins(sess["end"]):
                stage = next((text for st, en, text in sess["stages"]
                              if _mins(st) <= mins < _mins(en)), None)
                return sess["phase"], int((_mins(sess["end"]) - mins) * 60), stage, sess["label"]

        upcoming = [(_mins(s["start"]) - mins, s) for s in CAS_SESSIONS
                    if _mins(s["start"]) > mins]
        if upcoming:
            delta, sess = min(upcoming, key=lambda x: x[0])
            return "waiting:" + sess["phase"], int(delta * 60), None, sess["label"]

    return "waiting:pre-open", None, None, "Pre-open auction"


def nse_session():
    """What NSE itself says is running right now.

    Clock windows are a guess that goes stale whenever SEBI changes the timetable
    (a closing auction session has been under consultation), so the live session is
    read from NSE and the clock is only used for the countdown. Returns
    (phase or None, status message, indicative index dict or None).
    """
    d = cached(("nse-status", ""), QUOTE_CACHE_TTL, lambda: nse_get("/api/marketStatus"))
    if not d:
        return None, None, None

    message = ""
    for m in d.get("marketState", []):
        if m.get("market") == "Capital Market":
            message = m.get("marketStatusMessage") or ""
            break

    ind = d.get("indicativenifty50") or {}
    # Populated only while an auction is actually matching; "CLOSE" means no auction.
    live_auction = bool(ind.get("indicativeTime")) and (ind.get("status") or "").upper() != "CLOSE"
    indicative = {
        "value": ind.get("indexLast"),
        "change": ind.get("change"),
        "percentChange": ind.get("indexPercChange") if ind.get("indexPercChange") is not None else ind.get("perChange"),
        "time": ind.get("indicativeTime") or ind.get("dateTime"),
        "status": ind.get("status"),
    } if ind else None

    low = message.lower()
    phase = None
    if "pre open" in low or "pre-open" in low:
        phase = "pre-open"
    elif "closing" in low or "post close" in low:
        phase = "post-close"
    elif live_auction:
        phase = "auction"  # NSE is matching an auction the clock windows don't know about
    return phase, message, indicative


def cas_payload():
    """NSE's dedicated closing-auction feed.

    This is what nseindia.com/market-data/closing-auction-session calls; the path was
    read out of that page's JavaScript bundle (it is documented nowhere else). Outside
    the 15:15-15:35 window `data` is empty but `symbols` still lists the eligible names.
    """
    return cached(("cas-api", ""), QUOTE_CACHE_TTL, lambda: nse_get(
        "/api/NextApi/apiClient/casApi", {"functionName": "getCASData"}))


def cas_feed_payload(key):
    return cached(("cas-feed", key), QUOTE_CACHE_TTL, lambda: nse_get("/api/market-data-pre-open", {"key": key}))


def normalise_cas_rows(payload):
    """Map NSE's CAS row fields to ours. Verified against the live 15:20 payload (210 rows):
      IEP        indicative equilibrium price. NOT `finalPrice`, which stays 0 until matching.
      iiqAtMO    indicative imbalance from market orders = atoBuy - atoSell (210/210 rows),
                 so positive means a buy surplus.
      iiqAtEP    indicative imbalance at the equilibrium price (same sign convention assumed).
      change/perChange are measured against `refrencePrice` (NSE's spelling).
    """
    rows = []
    for r in (payload or {}).get("data") or []:
        if not isinstance(r, dict) or not r.get("symbol"):
            continue
        rows.append({
            "symbol": r["symbol"],
            "refPrice": r.get("refrencePrice"),
            "iep": r.get("IEP"),
            "finalPrice": r.get("finalPrice"),
            "change": r.get("change"),
            "pChange": r.get("perChange"),
            "imbalanceEP": r.get("iiqAtEP"),
            "imbalanceMO": r.get("iiqAtMO"),
            "buyQty": r.get("totalBuyQuantity"),
            "sellQty": r.get("totalSellQuantity"),
            "atoBuy": r.get("atoBuyQuantity"),
            "atoSell": r.get("atoSellQuantity"),
            "lastPrice": r.get("lastTradedPrice"),
            "upperBand": r.get("upperBand"),
            "lowerBand": r.get("lowerBand"),
            "bestBid": r.get("bestBidPrice"), "bestBidQty": r.get("bestBidQty"),
            "bestAsk": r.get("bestAskPrice"), "bestAskQty": r.get("bestAskQty"),
            "tradedQty": r.get("totTradedQty"),
            "finalQuantity": r.get("finalQuantity"),
            "finalValue": r.get("finalValue"),
            "orderBook": r.get("orderBook"),
        })
    return rows


def normalise_cas_book(order_book):
    """`orderBook` items: price / buyQuantity / sellQuantity / flag. Observed: `flag` is a
    boolean that is true exactly on the equilibrium-price rung (38/38 rungs had price == IEP)."""
    items = order_book if isinstance(order_book, list) else []
    return [{"price": i.get("price"), "buyQty": i.get("buyQuantity"),
             "sellQty": i.get("sellQuantity"), "flag": None, "isIep": i.get("flag") is True}
            for i in items if isinstance(i, dict)]


def breadth_from_all_indices(payload):
    """Shape NSE's `allIndices` rows into per-index breadth. NSE already publishes
    advances/declines/unchanged on each index row of that same payload this app already
    polls for /api/cas — no extra request needed. Only the indices we track by name are
    returned; an index missing from the payload or missing the count fields is skipped
    rather than reported as zero."""
    by_name = {row.get("index"): row for row in (payload or {}).get("data", [])}
    rows = []
    for alias, nse_name in NSE_INDEX_NAMES.items():
        row = by_name.get(nse_name)
        if not row:
            continue
        try:
            advances, declines, unchanged = int(row["advances"]), int(row["declines"]), int(row["unchanged"])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append({"alias": alias, "advances": advances, "declines": declines, "unchanged": unchanged})
    return rows


def breadth_rows():
    payload = all_indices()
    return breadth_from_all_indices(payload)


def all_indices():
    """`allIndices`, cached like every other NSE poll here — shared by /api/cas and
    /api/breadth so polling both doesn't double the outbound NSE traffic."""
    return cached(("all-indices", ""), QUOTE_CACHE_TTL, lambda: nse_get("/api/allIndices"))


def _save_seed():
    today = datetime.now(IST).strftime("%Y-%m-%d")
    seed = {
        "date": today,
        "refs": {alias: ref for (day, alias), ref in _cas_reference.items() if day == today},
        "series": {**{a: [list(p) for p in list(_nse_series[a])[-3000:]] for a in _nse_series},
                   "SENSEX": [list(p) for p in bse_stream.series(3000)]},
    }
    tmp = SEED_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(seed, f)
    os.replace(tmp, SEED_FILE)


def load_seed():
    """Restore today's reference and series after a restart. Ignored if it is from another day."""
    try:
        with open(SEED_FILE, encoding="utf-8") as f:
            seed = json.load(f)
        today = datetime.now(IST).strftime("%Y-%m-%d")
        if seed.get("date") != today:
            return
        for alias, ref in (seed.get("refs") or {}).items():
            _cas_reference[(today, alias)] = ref
        for alias, pts in (seed.get("series") or {}).items():
            if alias == "SENSEX":
                bse_stream.history.extend((p[0], p[1], p[2]) for p in pts)
            elif alias in _nse_series:
                _nse_series[alias].extend((p[0], p[1], p[2]) for p in pts)
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        pass  # no usable seed: start fresh


def _seed_loop():
    while True:
        time.sleep(10)
        try:
            _save_seed()
        except Exception:
            pass


def start_seed_loop():
    threading.Thread(target=_seed_loop, daemon=True, name="cas-seed").start()


def cas_reference_epoch(now_ist):
    h, m, sec = CAS_REFERENCE_AT
    return int(now_ist.replace(hour=h, minute=m, second=sec, microsecond=0).timestamp())


def _last_at_or_before(points, epoch, max_gap=120):
    """Last (t, value) with t <= epoch, provided it is not implausibly stale."""
    best = None
    for pt in points:
        if pt[0] <= epoch:
            best = pt
        else:
            break
    return best if best and epoch - best[0] <= max_gap else None


def _yahoo_minute_close(symbol, epoch):
    """Close of the 1-minute bar covering `epoch` (the 15:14 bar's close IS the value at 15:14:59)."""
    try:
        rows = df_to_rows(yf.download(symbol, period="1d", interval="1m", progress=False))
        bar_start = epoch - (epoch % 60)
        for r in reversed(rows):
            if r["time"] <= bar_start:
                return {"value": r["close"], "t": r["time"] + 59, "source": "Yahoo 1m bar close"} \
                    if bar_start - r["time"] <= 120 else None
    except Exception:
        return None
    return None


def cas_reference(alias, now_ist, points):
    """Locked reference for `alias`, or None while it is not yet knowable."""
    if now_ist.weekday() >= 5 or (now_ist.hour, now_ist.minute, now_ist.second) < (15, 15, 0):
        return None  # 15:14:59 has not passed yet
    key = (now_ist.strftime("%Y-%m-%d"), alias)
    if key in _cas_reference:
        return _cas_reference[key]
    epoch = cas_reference_epoch(now_ist)
    hit = _last_at_or_before([(t, v) for t, v, _i in points], epoch)
    ref = {"value": hit[1], "t": hit[0], "source": "last traded value at 15:14:59"} if hit else None
    if ref is None and alias in YAHOO_INDEX_SYMBOL:
        ref = _yahoo_minute_close(YAHOO_INDEX_SYMBOL[alias], epoch)
    if ref:
        _cas_reference[key] = ref
    return ref


def _nse_index_poller():
    while True:
        try:
            d = nse_get("/api/allIndices") or {}
            by = {r.get("index"): r for r in d.get("data", [])}
            _p, _m, ind = nse_session()
            for alias, name in NSE_INDEX_NAMES.items():
                r = by.get(name) or {}
                y = yahoo_live_quote(YAHOO_INDEX_SYMBOL[alias])
                last = y["price"] if y else r.get("last")
                if last is None:
                    continue
                t = y["marketTime"] if y else int(time.time())
                icls = r.get("indicativeClose") or None
                if alias == "NIFTY" and ind and ind.get("value"):
                    icls = icls or ind["value"]
                _nse_prev[alias] = (y or {}).get("prevClose") or r.get("previousClose")
                series = _nse_series[alias]
                # keep only changes: Yahoo's tick moves every ~11s, the indicative every ~1 min
                if not series or (series[-1][1], series[-1][2]) != (last, icls):
                    series.append((t, last, icls))
        except Exception:
            pass  # a bad poll must not kill the thread
        time.sleep(NSE_POLL_SEC)


def ensure_nse_poller():
    global _nse_started
    if not _nse_started:
        _nse_started = True
        threading.Thread(target=_nse_index_poller, daemon=True, name="nse-index").start()


def nse_series(alias):
    return _nse_series[alias]


def nse_prev_close(alias):
    return _nse_prev.get(alias)
