"""Live per-bar volume for the NSE indices.

Yahoo reports Volume = 0 for every index, so the volume histogram under NIFTY, BANKNIFTY
and NIFTYIT was empty. NSE's market-watch feed (see stats.py) does carry the running
total of shares traded today for each index (the sum over its constituents). Sampling that
running total every few seconds and differencing consecutive samples gives the shares
traded in each bar.

Sampling alone only knows volume from the moment the app started, so the earlier minutes
of the session are rebuilt a second way: an index's volume IS the sum of its constituents'
volume (NSE's own definition), and Yahoo serves every constituent's 1-minute volume for the
whole day. That history is refreshed every minute and is authoritative for every minute it
has; the fresh samples only fill the newest minutes Yahoo hasn't published yet. A daily bar
just uses the latest running total, which is the whole day's volume regardless.
"""
import json
import os
import tempfile
import threading
import time
from collections import deque
from datetime import datetime

import yfinance as yf

from .constants import IST
from .stats import INDEX_QUERY, constituent_symbols, stats_for

TRACKED = tuple(INDEX_QUERY)  # yahoo symbols: ^NSEI, ^NSEBANK, ^CNXIT
POLL_SEC = 3
SEED_FILE = os.path.join(tempfile.gettempdir(), "orazio_live_volume_seed.json")

_samples = {sym: deque(maxlen=20000) for sym in TRACKED}  # (epoch, running total shares)
_hist = {sym: {} for sym in TRACKED}  # symbol -> {1-minute bar epoch: summed constituent volume}
HIST_REFRESH_SEC = 60
_lock = threading.Lock()


def _today():
    return datetime.now(IST).strftime("%Y-%m-%d")


def _seconds_since_open(now):
    t = datetime.fromtimestamp(now, IST)
    return (t.hour * 3600 + t.minute * 60 + t.second) - (9 * 3600 + 15 * 60)


def record(symbol, total, now=None):
    now = now or time.time()
    with _lock:
        dq = _samples[symbol]
        if dq and total < dq[-1][1]:
            # The running total only falls when a new session starts. If we are watching it
            # happen (within 2 minutes of the 09:15 open) everything so far is opening
            # volume, so baseline at 0. Any later than that we caught it mid-session (e.g. a
            # restart over a stale seed) and cannot know how the volume was spread, so
            # baseline at the current total instead of dumping it all into one bar.
            dq.clear()
            if 0 <= _seconds_since_open(now) <= 120:
                dq.append((now - 1, 0.0))
        if not dq or total != dq[-1][1]:
            dq.append((now, float(total)))


def _slot(t, step):
    if step == 3600:  # Yahoo's hourly NSE bars start at :15, not :00
        return ((t - 900) // 3600) * 3600 + 900
    return (t // step) * step


def _day_slot(t):
    return ((int(t) + 19800) // 86400) * 86400 - 19800


def _minute_volumes(symbol):
    """Merge Yahoo's constituent-sum history with our own samples at 1-minute resolution."""
    with _lock:
        pts = list(_samples[symbol])
        hist = dict(_hist[symbol])

    sampled = {}
    for (_t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if v1 > v0:
            m = int(t1) // 60 * 60
            sampled[m] = sampled.get(m, 0.0) + (v1 - v0)
    if not hist:
        return sampled, pts

    # Yahoo's newest constituent minutes are still filling in (some stocks report a minute
    # before others), so from the newest history minute onward trust our own fresh samples.
    newest = max(hist)

    # Measured against NSE (30 Sep 2026, all 50 NIFTY stocks): Yahoo's minute volumes sum to
    # ~24% LESS than NSE's own totals (median -18% per stock, worst -47%). NSE's running total
    # is the truth, so wherever our samples overlap Yahoo's minutes, learn the ratio and scale
    # Yahoo's minute-by-minute SHAPE up to NSE's level. Needs a few full minutes of sampling;
    # until then Yahoo's raw numbers are used.
    scale = 1.0
    if pts:
        first_full = int(pts[0][0]) // 60 * 60 + 60
        overlap = [m for m in hist if first_full <= m < newest]
        yahoo_sum = sum(hist[m] for m in overlap)
        if len(overlap) >= 3 and yahoo_sum > 0:
            scale = min(3.0, max(1.0, sum(sampled.get(m, 0.0) for m in overlap) / yahoo_sum))
    out = {m: v * scale for m, v in hist.items() if m < newest}
    for m in {newest, *sampled}:
        if m >= newest:
            out[m] = sampled.get(m, hist.get(m, 0.0))

    # Yahoo reports the 09:15 bar (opening auction + first minute) with volume 0. NSE's
    # running total does include it, so it is whatever the total holds beyond every later bar.
    open_min = int(datetime.now(IST).replace(hour=9, minute=15, second=0, microsecond=0).timestamp())
    if pts and not out.get(open_min):
        est = pts[-1][1] - sum(v for m, v in out.items() if m > open_min)
        if est > 0:
            out[open_min] = est
    return out, pts


def bucket_volumes(symbol, step):
    """{bar start epoch: shares traded in that bar} for today, step in seconds (86400 = daily)."""
    if symbol not in _samples:
        return {}
    minutes, pts = _minute_volumes(symbol)
    if step >= 86400:
        return {_day_slot(pts[-1][0]): pts[-1][1]} if pts else {}
    out = {}
    for m, v in minutes.items():
        slot = _slot(m, step)
        out[slot] = out.get(slot, 0.0) + v
    return out


def apply(symbol, rows, step):
    """Fill zero-volume rows of `rows` (Yahoo's index bars) from our samples."""
    if symbol not in _samples or not step:
        return rows
    vols = bucket_volumes(symbol, step)
    if not vols:
        return rows
    for r in rows:
        if r["volume"] <= 0 and r["time"] in vols:
            r["volume"] = vols[r["time"]]
    return rows


def _save():
    with _lock:
        seed = {"date": _today(), "samples": {s: list(dq) for s, dq in _samples.items()}}
    tmp = SEED_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(seed, f)
    os.replace(tmp, SEED_FILE)


def load_seed():
    try:
        with open(SEED_FILE, encoding="utf-8") as f:
            seed = json.load(f)
        if seed.get("date") != _today():
            return
        with _lock:
            for sym, pts in (seed.get("samples") or {}).items():
                if sym in _samples:
                    _samples[sym].extend((p[0], p[1]) for p in pts)
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        pass  # no usable seed: start fresh


def _refresh_history():
    today = _today()
    for sym, index_name in INDEX_QUERY.items():
        tickers = constituent_symbols(index_name)
        if not tickers:
            continue
        df = yf.download(tickers, period="1d", interval="1m", progress=False, group_by="ticker", threads=True)
        totals = {}
        for t in tickers:
            try:
                col = df[t]["Volume"].dropna()
            except (KeyError, TypeError):
                continue
            for ts, v in col.items():
                if datetime.fromtimestamp(ts.timestamp(), IST).strftime("%Y-%m-%d") == today:
                    totals[int(ts.timestamp())] = totals.get(int(ts.timestamp()), 0.0) + float(v)
        with _lock:
            _hist[sym] = totals


def _hist_loop():
    while True:
        try:
            _refresh_history()
        except Exception:
            pass  # keep the last good history; the next cycle retries
        time.sleep(HIST_REFRESH_SEC)


def _loop():
    last_save = 0
    while True:
        try:
            for sym in TRACKED:
                s = stats_for(sym)
                if s and s.get("volume") is not None:
                    record(sym, s["volume"])
            if time.time() - last_save > 10:
                last_save = time.time()
                _save()
        except Exception:
            pass  # a bad poll must never kill the sampler
        time.sleep(POLL_SEC)


def start():
    threading.Thread(target=_loop, daemon=True, name="live-volume").start()
    threading.Thread(target=_hist_loop, daemon=True, name="live-volume-history").start()
