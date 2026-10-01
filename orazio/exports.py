"""OHLCV export: on-demand downloads from the chart dialog, and a saved end-of-day
schedule that writes CSV/Parquet files into a folder on this machine.

The data path is deliberately the same one the chart uses (yfinance -> df_to_rows ->
bonus/split gap-fill -> live index volume), so an exported bar matches the bar on screen.
"""
import importlib.util
import io
import json
import os
import re
import threading
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from .candles import df_to_rows
from .constants import INTERVAL_SECONDS, IST
from .corporate_actions import adjust_candles_for_splits
from . import live_volume
from .stats import constituent_symbols

# Yahoo's real intraday ceilings (constants.py's HISTORY_PERIOD is deliberately more
# conservative because it serves lazy scroll-back, not bulk export). None = full history.
INTERVAL_MAX_DAYS = {"1m": 7, "5m": 60, "15m": 60, "1h": 730, "1d": None}
PERIOD_ALL = {"1m": "7d", "5m": "60d", "15m": "60d", "1h": "730d", "1d": "max"}
INTERVAL_LABEL = {"1m": "1 minute", "5m": "5 minutes", "15m": "15 minutes", "1h": "1 hour", "1d": "1 day"}

# Universe key -> (index yahoo symbol, NSE index short name). Each expands to the index
# itself plus its current constituents.
UNIVERSES = {
    "NIFTY": ("^NSEI", "NIFTY 50", "NIFTY 50 + constituents"),
    "BANKNIFTY": ("^NSEBANK", "NIFTY BANK", "BANK NIFTY + constituents"),
    "NIFTYIT": ("^CNXIT", "NIFTY IT", "NIFTY IT + constituents"),
}
FORMATS = ("csv", "parquet")

CONFIG_PATH = Path.home() / ".orazio" / "export_schedule.json"
_run_lock = threading.Lock()


def _today():
    return datetime.now(IST).date()


def earliest_date(interval):
    max_days = INTERVAL_MAX_DAYS[interval]
    return _today() - timedelta(days=max_days - 1) if max_days else None


def parquet_available():
    return importlib.util.find_spec("pyarrow") is not None


def options(current_symbol):
    return {
        "today": _today().isoformat(),
        "intervals": [
            {"value": iv, "label": INTERVAL_LABEL[iv], "maxDays": INTERVAL_MAX_DAYS[iv],
             "earliest": earliest_date(iv).isoformat() if earliest_date(iv) else None}
            for iv in INTERVAL_MAX_DAYS
        ],
        "universes": [{"value": "CURRENT", "label": f"Current chart ({current_symbol})"}] +
                     [{"value": k, "label": v[2]} for k, v in UNIVERSES.items()],
        "scheduleUniverses": [{"value": k, "label": v[2]} for k, v in UNIVERSES.items()],
        "formats": [f for f in FORMATS if f == "csv" or parquet_available()],
        "schedule": load_schedule(),
    }


def universe_symbols(universe, current_symbol):
    if universe == "CURRENT":
        return [current_symbol]
    if universe not in UNIVERSES:
        raise ValueError("unknown universe")
    index_symbol, index_name, _label = UNIVERSES[universe]
    return [index_symbol] + constituent_symbols(index_name)


def build_window(interval, mode, day=None, date_from=None, date_to=None):
    if interval not in INTERVAL_MAX_DAYS:
        raise ValueError("unknown bar size")
    if mode == "all":
        return {"mode": "all", "label": "all"}

    def parse(s):
        try:
            return date.fromisoformat(s)
        except (TypeError, ValueError):
            raise ValueError("dates must look like 2026-09-30")

    if mode == "day":
        start = end = parse(day)
        label = start.isoformat()
    elif mode == "range":
        start, end = parse(date_from), parse(date_to)
        label = f"{start.isoformat()}_to_{end.isoformat()}"
    else:
        raise ValueError("unknown range mode")
    if start > end:
        raise ValueError("the start date is after the end date")
    if end > _today():
        raise ValueError("that date is in the future")
    earliest = earliest_date(interval)
    if earliest and start < earliest:
        raise ValueError(f"{INTERVAL_LABEL[interval]} bars only go back {INTERVAL_MAX_DAYS[interval]} days "
                         f"(from {earliest.isoformat()})")
    return {"mode": mode, "start": start.isoformat(), "end": (end + timedelta(days=1)).isoformat(), "label": label}


def fetch_rows(symbols, interval, window):
    kwargs = {"interval": interval, "progress": False, "group_by": "ticker", "threads": True}
    if window["mode"] == "all":
        kwargs["period"] = PERIOD_ALL[interval]
    else:
        kwargs["start"], kwargs["end"] = window["start"], window["end"]
    df = yf.download(symbols, **kwargs)

    step = INTERVAL_SECONDS.get(interval, 86400)
    out = {}
    for s in symbols:
        try:
            sub = df[s] if isinstance(df.columns, pd.MultiIndex) else df
            rows = df_to_rows(sub)
        except (KeyError, ValueError):
            rows = []
        rows = adjust_candles_for_splits(s, rows)
        out[s] = live_volume.apply(s, rows, step)
    return out


def fill_index_volume(universe, data):
    """Yahoo's index volume is 0. When the export holds the index AND all its
    constituents, fill the index bars with the constituents' summed volume at the same
    timestamp — NSE's own definition of an index's volume — but only where the index is
    still 0 (today's bars may already carry live-sampled volume)."""
    if universe not in UNIVERSES:
        return
    index_symbol = UNIVERSES[universe][0]
    index_rows = data.get(index_symbol)
    if not index_rows:
        return
    totals = {}
    for s, rows in data.items():
        if s == index_symbol:
            continue
        for r in rows:
            totals[r["time"]] = totals.get(r["time"], 0.0) + r["volume"]
    for r in index_rows:
        if r["volume"] <= 0 and totals.get(r["time"]):
            r["volume"] = totals[r["time"]]


def rows_frame(symbol, rows):
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df = df.rename(columns={"time": "timestamp"})
    df.insert(0, "symbol", symbol)
    df.insert(1, "datetime_ist", [datetime.fromtimestamp(t, IST).isoformat() for t in df["timestamp"]])
    return df


def encode(df, fmt):
    if fmt == "csv":
        return df.to_csv(index=False).encode("utf-8")
    if fmt == "parquet":
        if not parquet_available():
            raise ValueError("Parquet needs pyarrow — run: pip install pyarrow")
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        return buf.getvalue()
    raise ValueError("format must be csv or parquet")


def safe_name(symbol):
    return re.sub(r"[^A-Za-z0-9_.-]", "", symbol.lstrip("^")) or "symbol"


def build_download(current_symbol, universe, interval, mode, day, date_from, date_to, fmt):
    window = build_window(interval, mode, day, date_from, date_to)
    if fmt not in FORMATS:
        raise ValueError("format must be csv or parquet")
    symbols = universe_symbols(universe, current_symbol)
    data = fetch_rows(symbols, interval, window)
    fill_index_volume(universe, data)

    files = {}
    for s, rows in data.items():
        if rows:
            files[f"{safe_name(s)}_{interval}_{window['label']}.{fmt}"] = encode(rows_frame(s, rows), fmt)
    if not files:
        raise ValueError("No bars for that selection — a market holiday, or outside what Yahoo still serves.")

    if len(files) == 1:
        name, payload = next(iter(files.items()))
        return name, ("text/csv" if fmt == "csv" else "application/octet-stream"), payload

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, payload in files.items():
            z.writestr(name, payload)
    zip_name = f"{safe_name(current_symbol if universe == 'CURRENT' else universe)}_{interval}_{window['label']}.zip"
    return zip_name, "application/zip", buf.getvalue()


# ---------------------------------------------------------------------------
# End-of-day schedule
# ---------------------------------------------------------------------------
def load_schedule():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_schedule(cfg):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(CONFIG_PATH) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    os.replace(tmp, CONFIG_PATH)


def save_schedule(raw):
    """Validate and persist the schedule. A missing folder is created here so a bad path
    fails at save time, not silently at 15:31."""
    if not raw.get("enabled"):
        cfg = load_schedule() or {}
        cfg["enabled"] = False
        _write_schedule(cfg)
        return cfg

    time_str = str(raw.get("time") or "")
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", time_str):
        raise ValueError("time must be HH:MM (24-hour, IST)")
    path = str(raw.get("path") or "").strip()
    if not path or not os.path.isabs(path):
        raise ValueError("folder must be a full path, e.g. C:\\Data\\orazio")
    fmt, interval, universe = raw.get("format"), raw.get("interval"), raw.get("universe")
    if fmt not in FORMATS:
        raise ValueError("format must be csv or parquet")
    if fmt == "parquet" and not parquet_available():
        raise ValueError("Parquet needs pyarrow — run: pip install pyarrow")
    if interval not in INTERVAL_MAX_DAYS:
        raise ValueError("unknown bar size")
    if universe not in UNIVERSES:
        raise ValueError("unknown universe")
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        probe = Path(path) / ".orazio_write_test"
        probe.write_text("ok")
        probe.unlink()
    except OSError as e:
        raise ValueError(f"can't write to that folder: {e.strerror or e}")

    old = load_schedule() or {}
    cfg = {"enabled": True, "time": time_str, "path": path, "format": fmt,
           "interval": interval, "universe": universe, "lastRun": old.get("lastRun")}
    _write_schedule(cfg)
    return cfg


def run_job(cfg):
    """Fetch today's bars for the schedule's universe and write one file per symbol into
    <folder>/<YYYY-MM-DD>/. Returns the lastRun record."""
    with _run_lock:
        today = _today()
        record = {"date": today.isoformat(), "ranAt": datetime.now(IST).isoformat(timespec="seconds"),
                  "ok": False, "files": 0, "skipped": 0, "dir": None, "message": "",
                  "attempts": ((cfg.get("lastRun") or {}).get("attempts", 0)
                               if (cfg.get("lastRun") or {}).get("date") == today.isoformat() else 0) + 1}
        try:
            interval, fmt = cfg["interval"], cfg["format"]
            window = build_window(interval, "day", today.isoformat())
            data = fetch_rows(universe_symbols(cfg["universe"], None), interval, window)
            fill_index_volume(cfg["universe"], data)
            out_dir = Path(cfg["path"]) / today.isoformat()
            written = 0
            for s, rows in data.items():
                if not rows:
                    record["skipped"] += 1
                    continue
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / f"{safe_name(s)}_{interval}.{fmt}").write_bytes(encode(rows_frame(s, rows), fmt))
                written += 1
            record.update(files=written, dir=str(out_dir), ok=written > 0)
            record["message"] = (f"{written} files written" if written
                                 else "no bars for today (market holiday?)")
        except Exception as e:  # noqa: BLE001 — surfaced to the UI, never raised into the scheduler
            record["message"] = f"failed: {e}"
        return record


def run_now():
    cfg = load_schedule()
    if not cfg or not cfg.get("enabled"):
        raise ValueError("save an enabled schedule first")
    cfg["lastRun"] = run_job(cfg)
    _write_schedule(cfg)
    return cfg


def _scheduler_loop():
    while True:
        time.sleep(20)
        try:
            cfg = load_schedule()
            if not cfg or not cfg.get("enabled"):
                continue
            now = datetime.now(IST)
            if now.weekday() >= 5:
                continue
            hh, mm = (int(x) for x in cfg["time"].split(":"))
            if (now.hour, now.minute) < (hh, mm):
                continue
            last = cfg.get("lastRun") or {}
            if last.get("date") == now.date().isoformat():
                if last.get("ok") or last.get("attempts", 1) >= 3:
                    continue  # done for today, or gave up after 3 tries
                if time.time() - datetime.fromisoformat(last["ranAt"]).timestamp() < 300:
                    continue  # retry no sooner than 5 minutes after a failed attempt
            cfg["lastRun"] = run_job(cfg)
            _write_schedule(cfg)
        except Exception:
            pass  # a bad tick must never kill the scheduler


def start_scheduler():
    threading.Thread(target=_scheduler_loop, daemon=True, name="export-scheduler").start()
