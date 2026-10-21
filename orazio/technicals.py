"""Daily technicals for the screener: RSI(14), SMA 20/50/200 and recent 50/200 crosses, per stock.

One batched yfinance download (1 year of daily bars for the NIFTY 500, measured 13 s for 500
tickers) runs in a background thread once per trading day, after 15:45 IST, or at startup when the
saved copy is older than that. Only the closes are kept, in ~/.orazio/technicals.json.

The values move intraday: the live LTP from NSE's market watch is appended as today's close before
RSI and the distance-from-SMA are computed. Yahoo includes today's unfinished bar, so every saved
bar dated on or after NSE's trade date is dropped first (on a weekend that also stops Friday's
close being counted twice).
"""
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

from .stats import _rows

IST = timezone(timedelta(hours=5, minutes=30))
CACHE_FILE = Path.home() / ".orazio" / "technicals.json"
UNIVERSE = "NIFTY 500"
CUTOFF_HM = (15, 45)        # NSE's close is settled by then
RETRY_SEC = 600             # after a failed download
KEEP = 260                  # closes kept per stock: SMA200 + cross window + RSI warm-up

_data = None                # {"fetchedAt": epoch, "closes": {symbol: [[YYYY-MM-DD, close], ...]}}
_loaded = False
_running = False
_last_attempt = 0.0
_lock = threading.Lock()


# ---------- pure maths ----------
def rsi(closes, n=14):
    """Wilder's RSI of the last close — the same smoothing as the chart's RSI (indicators.js)."""
    if len(closes) <= n:
        return None
    gain = loss = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gain += max(d, 0)
        loss += max(-d, 0)
    gain /= n
    loss /= n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        gain = (gain * (n - 1) + max(d, 0)) / n
        loss = (loss * (n - 1) + max(-d, 0)) / n
    if loss == 0:
        return 50.0 if gain == 0 else 100.0
    return 100 - 100 / (1 + gain / loss)


def sma(closes, n):
    return sum(closes[-n:]) / n if len(closes) >= n else None


def cross_within(closes, fast=50, slow=200, sessions=5):
    """'golden' / 'death' when SMA(fast) crossed SMA(slow) within the last `sessions` bars (the most
    recent cross wins), else None."""
    if len(closes) < slow + sessions:
        return None
    diffs = [sma(closes[:len(closes) - j], fast) - sma(closes[:len(closes) - j], slow) for j in range(sessions, -1, -1)]
    found = None
    for prev, cur in zip(diffs, diffs[1:]):
        if prev <= 0 < cur:
            found = "golden"
        elif prev >= 0 > cur:
            found = "death"
    return found


def _pct(a, b):
    return (a - b) / b * 100 if a is not None and b else None


def metrics(closes, ltp):
    series = list(closes) + [ltp]
    s50, s200 = sma(series, 50), sma(series, 200)
    r = rsi(series)
    return {
        "rsi": round(r, 2) if r is not None else None,
        "vsSma50": _pct(ltp, s50),
        "vsSma200": _pct(ltp, s200),
        "cross": cross_within(series),
    }


def last_cutoff(now):
    """The most recent 15:45 IST at or before `now` (an aware datetime)."""
    local = now.astimezone(IST)
    cut = local.replace(hour=CUTOFF_HM[0], minute=CUTOFF_HM[1], second=0, microsecond=0)
    return cut if local >= cut else cut - timedelta(days=1)


def is_stale(fetched_at, now):
    return fetched_at is None or fetched_at < last_cutoff(now).timestamp()


def closes_before(bars, trade_date):
    """Closes of the saved [date, close] bars dated strictly before `trade_date` (YYYY-MM-DD)."""
    return [c for d, c in bars if d < trade_date]


# ---------- storage + refresh ----------
def _load():
    global _data, _loaded
    _loaded = True
    try:
        _data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _data = None


def _save(data):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(CACHE_FILE)
    except OSError:
        pass   # works from memory; just redownloads on the next start


def _download():
    tickers = [f"{r['symbol']}.NS" for r in _rows(UNIVERSE)
               if r.get("priority") != 1 and r.get("symbol") and r.get("series") == "EQ"]
    if not tickers:
        return None
    df = yf.download(tickers, period="1y", interval="1d", progress=False, group_by="ticker", threads=True)
    closes = {}
    for t in tickers:
        try:
            col = df[t]["Close"].dropna()
        except (KeyError, TypeError):
            continue
        if len(col):
            closes[t[:-3]] = [[i.strftime("%Y-%m-%d"), round(float(v), 4)] for i, v in col.items()][-KEEP:]
    return {"fetchedAt": time.time(), "closes": closes} if closes else None


def _refresh():
    global _data, _running
    try:
        data = _download()
        if data:
            _data = data
            _save(data)
    except Exception:   # yfinance raises a zoo of errors on network trouble; retried after RETRY_SEC
        pass
    finally:
        _running = False


def ensure_fresh(now=None):
    """Start a background download when the saved closes are stale. Returns the status the screener
    shows: 'ready' (closes available, possibly being refreshed), 'loading' or 'unavailable'."""
    global _running, _last_attempt
    with _lock:
        if not _loaded:
            _load()
        now = now or datetime.now(timezone.utc)
        stale = is_stale(_data and _data.get("fetchedAt"), now)
        if stale and not _running and time.time() - _last_attempt > RETRY_SEC:
            _running = True
            _last_attempt = time.time()
            threading.Thread(target=_refresh, daemon=True, name="technicals").start()
    if _data:
        return "ready"
    return "loading" if _running else "unavailable"


def fetched_at():
    return _data.get("fetchedAt") if _data else None


def for_symbol(symbol, ltp, trade_date):
    """Technicals for one stock at the live price, or None when there is no (or too little) history."""
    if not _data or ltp is None:
        return None
    bars = _data["closes"].get(symbol)
    if not bars:
        return None
    closes = closes_before(bars, trade_date)
    return metrics(closes, ltp) if len(closes) >= 15 else None
