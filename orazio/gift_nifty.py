"""GIFT Nifty: the NIFTY futures contract listed on NSE IX (GIFT City), the market's pre-open pulse.

Live: NSE's own `getGiftNifty` call (the one nseindia.com's pages make) — official, free, no login:
last price, day change, contracts traded, and a minute-resolution timestamp. Measured 1 Oct 2026:
it refreshes about once a minute.

Intraday bars: no intraday history is published anywhere free, so the chart is built from what we
have seen: every new reading is folded into a 1-minute bar and the bars are kept on disk (5 days),
so a restart doesn't wipe them. Like SENSEX's REST fallback, a bar opens at the PREVIOUS reading
(readings are a minute apart, so otherwise every candle would be flat) and its high/low are the
range across readings, not true intra-minute extremes.

Daily history: NSE IX publishes an official bhavcopy for every trading day
(https://www.nseix.com/api/content/daily_report/G_T[1]_Bhavcopy_FO_ddmmyy.CSV — open, no login,
back to at least June 2023). Each date has two files: `G_T_` is session 1 only (06:30-15:40 IST),
`G_T1_` is the cumulative end-of-session-2 file, i.e. the whole trading day. Daily bars use the
cumulative file, fall back to session 1, and stitch the nearest unexpired contract day by day
(rolling on expiry, so the roll shows as a gap). Each day is downloaded once and cached.
"""
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from pathlib import Path

import requests

from .cache import cached
from .constants import INTERVAL_SECONDS, IST
from .nse_client import nse_get

SYMBOL = "GIFTNIFTY"
POLL_SEC = 20
RETENTION_DAYS = 5
STORE = Path.home() / ".orazio" / "gift_nifty_bars.json"
CACHE_DIR = Path.home() / ".orazio" / "gift_cache"
ARCHIVE_URL = "https://www.nseix.com/api/content/daily_report/G_T{session}_Bhavcopy_FO_{day:%d%m%y}.CSV"
FETCH_BUDGET_SEC = 25
MAX_DAILY_CALENDAR_DAYS = 1200   # the archive starts mid-2023
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Referer": "https://www.nseix.com/markets/reports"}
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="gift-archive")

_bars = {}  # minute epoch -> [open, high, low, close]
_lock = threading.Lock()
_last_stamp = None


# ---------------------------------------------------------------------------
# Pure helpers (tested in tests/test_gift_nifty.py)
# ---------------------------------------------------------------------------
def parse_reading(payload):
    """NSE's getGiftNifty payload -> {price, prevClose, marketTime, ...}, or None if unusable."""
    g = ((payload or {}).get("data") or {}).get("giftNifty")
    if not g or g.get("lastprice") is None:
        return None
    try:
        price = float(g["lastprice"])
        change = float(g.get("daychange") or 0)
        stamp = int(datetime.strptime(g["timestmp"], "%d-%b-%Y %H:%M").replace(tzinfo=IST).timestamp())
    except (KeyError, TypeError, ValueError):
        return None
    return {"price": price, "prevClose": price - change, "marketTime": stamp, "currency": "INR",
            "contracts": g.get("contractstraded"), "expiry": g.get("expirydate")}


def fold_reading(bars, market_time, price):
    """Fold one reading into its 1-minute bar (mutates `bars`). A new bar opens at the previous
    bar's close so consecutive minutes join up instead of every candle being flat."""
    minute = market_time - (market_time % 60)
    bar = bars.get(minute)
    if bar is None:
        earlier = [m for m in bars if m < minute]
        start = bars[max(earlier)][3] if earlier else price
        bars[minute] = [start, max(start, price), min(start, price), price]
    else:
        bar[1] = max(bar[1], price)
        bar[2] = min(bar[2], price)
        bar[3] = price


def rebucket(minute_bars, step):
    """1-minute bars -> rows of `step` seconds (60..3600), or one row per IST day for step >= 86400."""
    out = {}
    for minute in sorted(minute_bars):
        o, h, l, c = minute_bars[minute]
        slot = (minute + 19800) // 86400 * 86400 - 19800 if step >= 86400 else minute - (minute % step)
        cur = out.get(slot)
        if cur is None:
            out[slot] = [o, h, l, c]
        else:
            cur[1], cur[2], cur[3] = max(cur[1], h), min(cur[2], l), c
    return [{"time": t, "open": o, "high": h, "low": l, "close": c, "volume": 0} for t, (o, h, l, c) in sorted(out.items())]


RANGE_DAYS = {"1D": 1, "5D": 5, "1M": 31, "3M": 92, "6M": 183, "YTD": 366, "1Y": 366, "5Y": MAX_DAILY_CALENDAR_DAYS, "ALL": MAX_DAILY_CALENDAR_DAYS}


def rows_for(minute_bars, interval_step, rng):
    """Bars for a chart request: everything within the range's window before the newest bar."""
    rows = rebucket(minute_bars, interval_step)
    if not rows:
        return rows
    horizon = rows[-1]["time"] - RANGE_DAYS.get(rng, 1) * 86400
    return [r for r in rows if r["time"] > horizon]


# ---- the official daily archive (pure parsing) -------------------------------------
_CONTRACT = re.compile(r"^FUTIDXNIFTY(\d{2}-[A-Z]{3}-\d{4})$")


def parse_bhavcopy(text):
    """Bhavcopy CSV text -> [{expiry (ISO), open, high, low, close, settle, volume}] for the GIFT
    Nifty futures contracts that actually traded. Other products (currencies, Bank Nifty, ...) and
    contracts with no trades are skipped."""
    out = []
    for line in text.splitlines()[1:]:
        cols = line.split(",")
        m = _CONTRACT.match(cols[0].strip()) if cols else None
        if not m or len(cols) < 10:
            continue
        try:
            expiry = datetime.strptime(m.group(1), "%d-%b-%Y").date().isoformat()
            volume = int(float(cols[9] or 0))
            open_, high, low = float(cols[2]), float(cols[3]), float(cols[4])
            close = float(cols[5]) if cols[5].strip() else float(cols[6])
            settle = float(cols[6])
        except ValueError:
            continue
        if volume > 0 and open_ > 0:
            out.append({"expiry": expiry, "open": open_, "high": high, "low": low, "close": close, "settle": settle, "volume": volume})
    return out


def front_contract(contracts, day):
    """The nearest expiry that has not passed on `day` (None if there isn't one)."""
    live = [c for c in contracts if c["expiry"] >= day.isoformat()]
    return min(live, key=lambda c: c["expiry"]) if live else None


def day_slot(day):
    """The IST-midnight epoch for a trade date — the same slot rebucket() uses for daily bars."""
    return int(datetime(day.year, day.month, day.day, tzinfo=IST).timestamp())


def daily_bar(day, session1, session2):
    """One daily bar for `day`: the cumulative end-of-session-2 file is the whole trading day; if
    it isn't published yet (or is missing) fall back to session 1."""
    c = front_contract(session2 or [], day) or front_contract(session1 or [], day)
    if not c:
        return None
    return {"time": day_slot(day), "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"], "volume": c["volume"]}


# ---- download + cache ----------------------------------------------------------------
def _day_path(day):
    return CACHE_DIR / f"{day:%Y%m%d}.json"


def _read_day(day):
    try:
        return json.loads(_day_path(day).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _download(day, session):
    """Parsed contracts for one file; [] for a day with no such file; None if the fetch failed."""
    try:
        r = requests.get(ARCHIVE_URL.format(session="" if session == 1 else "1", day=day), headers=_HEADERS, timeout=30)
    except requests.RequestException:
        return None
    if r.status_code == 404:
        return []
    if r.status_code != 200:
        return None
    return parse_bhavcopy(r.content.decode("utf-8", "ignore"))


def _fetch_day(day):
    """{"s1": [...], "s2": [...]} for a trade date, from cache or the archive; None if unavailable
    right now. A recent day is only cached once its cumulative session-2 file exists, so an early
    fetch (before the evening session ends) can't freeze a half-day."""
    cached_day = _read_day(day)
    if cached_day is not None:
        return cached_day
    s1, s2 = _download(day, 1), _download(day, 2)
    if s1 is None or s2 is None:
        return None
    result = {"s1": s1, "s2": s2}
    if s2 or day < datetime.now(IST).date() - timedelta(days=3):    # complete, or long past (holiday / no data)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _day_path(day).write_text(json.dumps(result), encoding="utf-8")
    return result


def _ensure_days(days):
    """Fetch every missing day in parallel, waiting at most the budget; the rest keep downloading
    in the background and are ready on the next request."""
    got, pending = {}, {}
    for d in days:
        cached_day = _read_day(d)
        if cached_day is not None:
            got[d] = cached_day
        else:
            pending[d] = _pool.submit(_fetch_day, d)
    if pending:
        wait(pending.values(), timeout=FETCH_BUDGET_SEC)
        for d, fut in pending.items():
            if fut.done() and fut.result() is not None:
                got[d] = fut.result()
    return got


def daily_history(calendar_days):
    """Official daily bars for the last `calendar_days` days (oldest first), weekdays only. Today
    is never included: the archive publishes after the session, and today's bar comes from our
    own readings."""
    today = datetime.now(IST).date()
    days = [today - timedelta(n) for n in range(min(calendar_days, MAX_DAILY_CALENDAR_DAYS), 0, -1)]
    days = [d for d in days if d.weekday() < 5]
    got = _ensure_days(days)
    bars = [daily_bar(d, got[d]["s1"], got[d]["s2"]) for d in days if d in got]
    return [b for b in bars if b]


def merge_daily(history, own_daily):
    """History wins for any day it covers; our own readings fill the days it doesn't (today)."""
    by_time = {b["time"]: b for b in own_daily}
    by_time.update({b["time"]: b for b in history})
    return [by_time[t] for t in sorted(by_time)]


def chart(interval, rng, minute_bars=None):
    """(interval actually used, bars) for a chart request.

    Intraday bars exist only for the time this app has been watching, so an intraday request is
    served from them only while they cover the range; otherwise it escalates to the official daily
    history and the caller reports the interval actually used."""
    if minute_bars is None:
        with _lock:
            minute_bars = {m: list(b) for m, b in _bars.items()}
    step = INTERVAL_SECONDS.get(interval)
    wanted_days = RANGE_DAYS.get(rng, 1)
    if step and minute_bars:
        covered_days = (max(minute_bars) - min(minute_bars)) / 86400 + 1
        if wanted_days <= 1 or wanted_days <= covered_days:
            rows = rows_for(minute_bars, step, rng)
            if rows:
                return interval, rows
    window = max(wanted_days, 14)                      # a 5D view at daily resolution would be 3-5 bars
    history = daily_history(window)
    own = rebucket(minute_bars, 86400) if minute_bars else []
    rows = merge_daily(history, own)
    if rows:
        horizon = rows[-1]["time"] - window * 86400
        rows = [r for r in rows if r["time"] > horizon]
    return "1d", rows


# ---------------------------------------------------------------------------
# Live feed + persistence
# ---------------------------------------------------------------------------
def quote():
    return cached(("gift", ""), 2, lambda: parse_reading(nse_get("/api/NextApi/apiClient", {"functionName": "getGiftNifty"})))


def _save():
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        data = {str(m): b for m, b in _bars.items()}
    tmp = str(STORE) + ".tmp"
    Path(tmp).write_text(json.dumps(data), encoding="utf-8")
    Path(tmp).replace(STORE)


def load():
    try:
        raw = json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    horizon = time.time() - RETENTION_DAYS * 86400
    with _lock:
        _bars.update({int(m): b for m, b in raw.items() if int(m) > horizon})


def _poll_once():
    global _last_stamp
    q = quote()
    if not q or q["marketTime"] == _last_stamp:  # NSE hasn't published a new reading yet
        return
    _last_stamp = q["marketTime"]
    with _lock:
        fold_reading(_bars, q["marketTime"], q["price"])
        horizon = time.time() - RETENTION_DAYS * 86400
        for m in [m for m in _bars if m < horizon]:
            del _bars[m]
    _save()


def _loop():
    while True:
        try:
            _poll_once()
        except Exception:
            pass  # a bad poll must never kill the sampler
        time.sleep(POLL_SEC)


def start():
    load()
    threading.Thread(target=_loop, daemon=True, name="gift-nifty").start()
