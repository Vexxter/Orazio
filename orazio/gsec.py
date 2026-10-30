"""Indian government securities live from CCIL's NDS-OM (the RBI's electronic G-sec platform), and a recorder
that keeps each security's trades so it can be charted.

NDS-OM's public market watch (ccilindia.com/market-watch) loads one JSON call per segment:
  NDSOMCG  central government securities      NDSOMSG  state government securities (SDLs)
  NDSOM_TBILL  treasury bills                 NDSOM_WI_NEW_ISSUED  when-issued (often empty)
Each row has the best bid/offer (amount ₹ Cr, yield, price), last traded yield/price/amount and the total traded
amount. CCIL's field names are SWAPPED for G-secs and SDLs — `ltp` holds the last traded YIELD and `lty` the
PRICE (checked against CNBC's IN10Y: 7.357 = `ltp` of 6.94 GS 2036) — but NOT for T-bills, where `lty` is the
yield (5.75) and `ltp` the price (98.68). The call needs the Akamai cookies the page sets, so the session
warms up on the page first and again whenever a reply isn't JSON. CCIL's server sometimes takes ~10 s.

History: CCIL shows only the current day, so a background thread polls the segments every 20 s during the
session (09:00–17:15 IST, weekdays) and appends a tick whenever a security's traded amount grows. Ticks live
in ~/.orazio/gsec_ticks/<date>.json; a security is chartable from the first day this app recorded it.
"""
import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .bonds import weekly
from .cache import cached
from .http_clients import ccil_http

IST = timezone(timedelta(hours=5, minutes=30))
CCIL_PAGE = "https://www.ccilindia.com/market-watch"
CCIL_PORTLET = "com_ccil_ndsom_marketwatch_CcilNDSOMMarketWatchPortlet_INSTANCE_swas"
CCIL_TTL = 5
# segment key -> (CCIL resource id, field names swapped?, label)
SEGMENTS = {
    "cg": ("NDSOMCG", True, "Central govt"),
    "sdl": ("NDSOMSG", True, "State govt (SDL)"),
    "tbill": ("NDSOM_TBILL", False, "T-Bills"),
    "wi": ("NDSOM_WI_NEW_ISSUED", True, "When-issued"),   # layout unverified: empty on the day this was built
}
RECORDED = ("cg", "sdl", "tbill")
TICK_DIR = Path.home() / ".orazio" / "gsec_ticks"
POLL_SEC = 20
SESSION = ((9, 0), (17, 15))
DECIMALS = 4

_warm = False
_ticks = {}          # {"YYYY-MM-DD": {chart id: [[epoch, yield, price, traded Cr], ...]}}
_ticks_lock = threading.Lock()
_started = False


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def chart_id(security):
    """'06.94 GS 2036' -> 'NDS_0694_GS_2036': a chart symbol (letters, digits, _) for one security."""
    return "NDS_" + re.sub(r"[^A-Z0-9]+", "_", security.upper().replace(".", "")).strip("_")


def is_gsec(symbol):
    return symbol.startswith("NDS_")


# ---------- CCIL ----------
def _resource(rid):
    return (f"{CCIL_PAGE}?p_p_id={CCIL_PORTLET}&p_p_lifecycle=2&p_p_state=normal&p_p_mode=view"
            f"&p_p_resource_id={rid}&p_p_cacheability=cacheLevelPage")


def _ccil_post(rid):
    """POST one market-watch resource; warm the Akamai cookies first, and once more on a non-JSON reply."""
    global _warm
    for attempt in range(2):
        if not _warm or attempt:
            ccil_http.get(CCIL_PAGE, timeout=20)
            _warm = True
        r = ccil_http.post(_resource(rid), timeout=20)
        try:
            return r.json()
        except ValueError:
            continue
    return None


def _iso_date(dmy):
    try:
        return datetime.strptime(dmy, "%d/%m/%Y").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def gsec_row(r, swapped=True):
    """One NDS-OM row -> one row for the page. Zero bid/offer amounts mean no order on that side."""
    bid_amt, ask_amt = _num(r.get("a")), _num(r.get("f"))
    traded = _num(r.get("tta")) or 0.0
    yld, px = (r.get("ltp"), r.get("lty")) if swapped else (r.get("lty"), r.get("ltp"))
    security = (r.get("ismt_idnt") or "").strip()
    return {
        "security": security,
        "id": chart_id(security),
        "maturity": _iso_date(r.get("mrty_date")),
        "ltYield": _num(yld) if traded else None,
        "ltPrice": _num(px) if traded else None,
        "lastAmt": _num(r.get("lta")) if traded else None,
        "traded": traded,                                      # ₹ Cr, today
        "bidYield": _num(r.get("b")) if bid_amt else None,
        "bidPrice": _num(r.get("c")) if bid_amt else None,
        "bidAmt": bid_amt or None,
        "askYield": _num(r.get("e")) if ask_amt else None,
        "askPrice": _num(r.get("d")) if ask_amt else None,
        "askAmt": ask_amt or None,
    }


def _rows_of(payload):
    """CCIL wraps rows as JSON strings under result1 (and result2 for when-issued)."""
    out = []
    for key in ("result1", "result2"):
        raw = (payload or {}).get(key)
        try:
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except ValueError:
            rows = []
        out += [r for r in rows if isinstance(r, dict) and r.get("ismt_idnt")]
    return out


def _fetch(seg):
    rid, swapped, _ = SEGMENTS[seg]
    rows = [gsec_row(r, swapped) for r in _rows_of(_ccil_post(rid))]
    rows.sort(key=lambda x: -x["traded"])
    status = cached(("gsec", "ticker"), 30, lambda: _ccil_post("ticker") or {})
    return {"available": bool(rows), "open": status.get("resultMarketOpenClose") == "Y", "rows": rows}


def segment(seg):
    if seg not in SEGMENTS:
        seg = "cg"
    try:
        return {"segment": seg, **cached(("gsec", seg), CCIL_TTL, lambda: _fetch(seg))}
    except Exception:   # network trouble: the panel says "unavailable" rather than erroring
        return {"segment": seg, "available": False, "open": None, "rows": []}


# ---------- recorder ----------
def _day(epoch):
    return datetime.fromtimestamp(epoch, IST).strftime("%Y-%m-%d")


def _load_day(day):
    try:
        return json.loads((TICK_DIR / f"{day}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_day(day, data):
    try:
        TICK_DIR.mkdir(parents=True, exist_ok=True)
        tmp = TICK_DIR / f"{day}.tmp"
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(TICK_DIR / f"{day}.json")
    except OSError:
        pass   # recording is best-effort: memory still has today's ticks


def record(rows, now):
    """Append a tick for every security whose traded amount grew since its last tick. Returns how many."""
    day = _day(now)
    added = 0
    with _ticks_lock:
        today = _ticks.setdefault(day, _load_day(day))
        for r in rows:
            if not r["traded"] or r["ltYield"] is None:
                continue
            ticks = today.setdefault(r["id"], [])
            if not ticks or r["traded"] > ticks[-1][3]:
                ticks.append([int(now), r["ltYield"], r["ltPrice"], r["traded"]])
                added += 1
        if added:
            _save_day(day, today)
    return added


def in_session(now):
    t = datetime.fromtimestamp(now, IST)
    return t.weekday() < 5 and SESSION[0] <= (t.hour, t.minute) <= SESSION[1]


def _loop():
    while True:
        now = time.time()
        if in_session(now):
            for seg in RECORDED:
                try:
                    record(segment(seg)["rows"], now)
                except Exception:   # one bad poll mustn't stop the recorder
                    pass
        time.sleep(POLL_SEC)


def start():
    global _started
    if not _started:
        _started = True
        threading.Thread(target=_loop, daemon=True, name="gsec-recorder").start()


def ticks_for(symbol, since):
    """[(epoch, yield)] for one security from every recorded day since `since` (epoch)."""
    out = []
    try:
        days = sorted(p.stem for p in TICK_DIR.glob("*.json"))
    except OSError:
        days = []
    first = _day(since)
    with _ticks_lock:
        for day in days + [d for d in _ticks if d not in days]:
            if day < first:
                continue
            data = _ticks.get(day) if day in _ticks else _load_day(day)
            out += [(t, y) for t, y, *_ in data.get(symbol, []) if t >= since]
    return sorted(out)


# ---------- charting one security ----------
def bars(ticks, step):
    """Ticks -> OHLC bars of `step` seconds (daily: one bar per IST day, stamped 00:00 UTC of that date)."""
    out = []
    for t, y in ticks:
        if step >= 86400:
            d = datetime.fromtimestamp(t, IST).date()
            b = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
        else:
            b = t - t % step
        if out and out[-1]["time"] == b:
            o = out[-1]
            o["high"], o["low"], o["close"] = max(o["high"], y), min(o["low"], y), y
        else:
            out.append({"time": b, "open": y, "high": y, "low": y, "close": y, "volume": 0})
    return out


STEP = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}
RANGE_DAYS = {"1D": 1, "1W": 7, "1M": 31, "3M": 92, "6M": 183, "YTD": 366, "1Y": 366, "5Y": 1827, "ALL": 36500}


def candles(symbol, interval, rng, now=None):
    now = now or time.time()
    interval = interval if interval in STEP or interval == "1wk" else "1d"
    ticks = ticks_for(symbol, now - RANGE_DAYS.get(rng, 1) * 86400)
    rows = bars(ticks, STEP.get(interval, 86400))
    if interval == "1wk":
        rows = weekly(rows)
    return {"symbol": symbol, "interval": interval, "range": rng, "candles": rows, "liveBars": 0,
            "source": "ccil", "decimals": DECIMALS, "closeOnly": False}


def find(symbol):
    for seg in RECORDED:
        row = next((r for r in segment(seg)["rows"] if r["id"] == symbol), None)
        if row:
            return row
    return None


def quote(symbol, now=None):
    """Live yield of one security as a chart quote: the last trade, else the bid/offer middle."""
    row = find(symbol)
    if not row:
        return None
    price = row["ltYield"]
    if price is None and row["bidYield"] and row["askYield"]:
        price = (row["bidYield"] + row["askYield"]) / 2
    if price is None:
        return None
    now = now or time.time()
    earlier = [y for t, y in ticks_for(symbol, now - 10 * 86400) if _day(t) < _day(now)]
    today = [(t, y) for t, y in ticks_for(symbol, now - 86400) if _day(t) == _day(now)]
    prev = earlier[-1] if earlier else (today[0][1] if today else price)
    return {"price": price, "prevClose": prev, "marketTime": today[-1][0] if today else int(now), "currency": "%"}


def name(symbol):
    row = find(symbol)
    return f"{row['security']} · India G-sec yield (%)" if row else "India government security (%)"
