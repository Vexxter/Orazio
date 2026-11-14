"""Alerts that keep running after the tab closes: rules, the store, and the background watcher.

The rules are the same as static/js/alert-rules.js, which the page still uses for its charted backtests;
tests/fixtures/alert_vectors.json holds cases both languages must agree on. Rules are checked every 20 s through the
app's own routes, so a symbol resolves and falls back exactly as it does on the chart. The same thread watches filings
for the user's keywords and sends the daily brief.

ponytail: the watcher lives in the Flask process, so alerts stop if the app or the machine does. Start the app at
login to cover that; a separate service adds nothing until alerts must outlive the app.
"""
import json
import logging
import math
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from statistics import median

from . import notify, user_settings
from .constants import IST

STORE = Path.home() / ".orazio" / "alerts.json"
CHECK_SEC = 20
HISTORY_TTL = 600
FILINGS_EVERY_SEC = 300
MAX_LOG = 50
MAX_SEEN = 5000
TYPES = ("above", "below", "chgUp", "chgDown", "rsiAbove", "rsiBelow", "smaAbove", "smaBelow")
LABELS = {"above": "Price crosses above", "below": "Price crosses below", "chgUp": "Day change ≥ +X%", "chgDown": "Day change ≤ −X%",
          "rsiAbove": "RSI(14) crosses above", "rsiBelow": "RSI(14) crosses below",
          "smaAbove": "Close crosses above SMA(X)", "smaBelow": "Close crosses below SMA(X)"}
EMPTY = {"alerts": [], "log": [], "filingWatch": {"keywords": [], "symbols": [], "seen": []}, "briefDay": None}
log = logging.getLogger(__name__)
_lock = threading.RLock()
_started = False


# ---------- rules (pure) ----------
def _rsi_series(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gain = sum(max(closes[i] - closes[i - 1], 0) for i in range(1, n + 1)) / n
    loss = sum(max(closes[i - 1] - closes[i], 0) for i in range(1, n + 1)) / n

    def value():
        return (50.0 if gain == 0 else 100.0) if loss == 0 else 100 - 100 / (1 + gain / loss)
    out[n] = value()
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        gain = (gain * (n - 1) + max(d, 0)) / n
        loss = (loss * (n - 1) + max(-d, 0)) / n
        out[i] = value()
    return out


def _values(closes, rule):
    t, x = rule["type"], rule["value"]
    if t in ("chgUp", "chgDown"):
        return [None] + [(closes[i] / closes[i - 1] - 1) * 100 for i in range(1, len(closes))]
    if t.startswith("rsi"):
        return _rsi_series(closes)
    if t.startswith("sma"):
        n = max(2, round(x))
        out, total = [None] * len(closes), 0.0
        for i, c in enumerate(closes):
            total += c - (closes[i - n] if i >= n else 0)
            if i >= n - 1:
                out[i] = c - total / n          # > 0 = above the average
        return out
    return list(closes)


def fires(closes, rule):
    """Indices of the closes on which the rule fires; the same decisions as fires() in alert-rules.js."""
    v = _values(closes, rule)
    t = rule["type"]
    level = 0 if t.startswith("sma") else rule["value"]
    out = []
    for i in range(1, len(closes)):
        if v[i] is None:
            continue
        if t == "chgUp":
            hit = v[i] >= rule["value"]
        elif t == "chgDown":
            hit = v[i] <= -abs(rule["value"])
        else:
            if v[i - 1] is None:
                continue
            hit = (v[i - 1] <= level < v[i]) if t.endswith("bove") else (v[i - 1] >= level > v[i])
        if hit:
            out.append(i)
    return out


def _ist_day(ts):
    return math.floor((ts + 19800) / 86400)


def with_live(bars, price, now):
    """Closes with today's replaced (or appended) by the live price, so the last one is "now"."""
    closes = [b["close"] for b in bars]
    if bars and _ist_day(bars[-1]["time"]) == _ist_day(now):
        closes[-1] = price
    else:
        closes.append(price)
    return closes


def describe(rule):
    label = LABELS[rule["type"]]
    value = f"{rule['value']:g}"
    return f"{rule['symbol']} · " + (label.replace("X", value) if "X" in label else f"{label} {value}")


def backtest(bars, rule, horizons=(1, 5, 10, 20)):
    """How often the rule fired over daily bars, and the % move h sessions after each fire."""
    closes = [b["close"] for b in bars]
    hits = fires(closes, rule)
    stats = []
    for h in horizons:
        moves = [(closes[i + h] / closes[i] - 1) * 100 for i in hits if i + h < len(closes)]
        stats.append({"sessions": h, "count": len(moves),
                      "avgPct": round(sum(moves) / len(moves), 3) if moves else None,
                      "medianPct": round(median(moves), 3) if moves else None,
                      "upShare": round(sum(m > 0 for m in moves) / len(moves) * 100, 1) if moves else None})
    return {"bars": len(bars), "fired": len(hits), "stats": stats,
            "lastFires": [datetime.fromtimestamp(bars[i]["time"], IST).date().isoformat() for i in hits[-8:]]}


def clean_rule(raw):
    """A rule from outside this process -> validated, or ValueError with a message for the user."""
    symbol = str((raw or {}).get("symbol") or "").strip().upper()
    kind = (raw or {}).get("type")
    value = (raw or {}).get("value")
    if not symbol or len(symbol) > 40:
        raise ValueError("Enter a symbol")
    if kind not in TYPES:
        raise ValueError("Unknown alert type")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Enter a number")
    return {"symbol": symbol, "type": kind, "value": value}


# ---------- store ----------
def read():
    """The saved state. A corrupt file is set aside, not overwritten, so hand-repair stays possible."""
    try:
        return {**json.loads(json.dumps(EMPTY)), **json.loads(STORE.read_text(encoding="utf-8"))}
    except FileNotFoundError:
        return json.loads(json.dumps(EMPTY))
    except (OSError, ValueError) as e:
        log.error("alerts store unreadable, keeping a copy: %s", e)
        try:
            os.replace(STORE, STORE.with_suffix(f".bad-{int(time.time())}.json"))
        except OSError:
            pass
        return json.loads(json.dumps(EMPTY))


def _write(data):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STORE)


def add(raw):
    rule = clean_rule(raw)
    with _lock:
        d = read()
        a = {**rule, "id": uuid.uuid4().hex[:12], "active": True, "lastFired": None}
        d["alerts"].append(a)
        _write(d)
    return a


def import_local(alerts, entries):
    """One-time move of the rules a browser kept in localStorage. Bad rows are skipped and counted."""
    added = skipped = 0
    with _lock:
        d = read()
        have = {(a["symbol"], a["type"], a["value"]) for a in d["alerts"]}
        for raw in alerts or []:
            try:
                rule = clean_rule(raw)
            except ValueError:
                skipped += 1
                continue
            if (rule["symbol"], rule["type"], rule["value"]) in have:
                continue
            d["alerts"].append({**rule, "id": uuid.uuid4().hex[:12], "active": raw.get("active") is not False,
                                "lastFired": raw.get("lastFired") if isinstance(raw.get("lastFired"), str) else None})
            added += 1
        kept = [e for e in entries or [] if isinstance(e, dict) and isinstance(e.get("at"), str) and isinstance(e.get("msg"), str)]
        d["log"] = (d["log"] + kept)[:MAX_LOG]
        _write(d)
    return {"added": added, "skipped": skipped}


def change(alert_id, active):
    with _lock:
        d = read()
        a = next((x for x in d["alerts"] if x["id"] == alert_id), None)
        if a is None:
            raise ValueError("No such alert")
        a["active"] = bool(active)
        _write(d)


def remove(alert_id):
    with _lock:
        d = read()
        d["alerts"] = [a for a in d["alerts"] if a["id"] != alert_id]
        _write(d)


def set_filing_watch(keywords, symbols):
    if not isinstance(keywords, list) or not isinstance(symbols, list):
        raise ValueError("Keywords and symbols must be lists")
    with _lock:
        d = read()
        d["filingWatch"].update(keywords=[str(k).strip() for k in keywords if str(k).strip()][:50],
                                symbols=[str(s).strip().upper() for s in symbols if str(s).strip()][:500])
        _write(d)
    return d["filingWatch"]


def _log_fire(d, msg, now, kind="alert"):
    d["log"] = [{"at": datetime.fromtimestamp(now, IST).isoformat(timespec="seconds"), "msg": msg, "kind": kind}, *d["log"]][:MAX_LOG]


# ---------- the watcher ----------
_history = {}   # symbol -> (fetched at, daily bars)


def _bars(symbol, fetch, now):
    hit = _history.get(symbol)
    if hit and now - hit[0] < HISTORY_TTL:
        return hit[1]
    bars = (fetch(f"/api/candles?symbol={symbol}&interval=1d&range=1Y") or {}).get("candles") or []
    _history[symbol] = (now, bars)
    return bars


def _hit(rule, quote, bars, now):
    # Day change comes from the quote (the exchange's official previous close); the rest need the daily history.
    if rule["type"] == "chgUp":
        return quote["changePercent"] >= rule["value"]
    if rule["type"] == "chgDown":
        return quote["changePercent"] <= -abs(rule["value"])
    closes = with_live(bars, quote["price"], quote.get("marketTime") or now)
    return (len(closes) - 1) in fires(closes, rule)


def check_rules(fetch, send, now=None):
    """One pass over the active rules: each fires at most once per IST day."""
    now = now or time.time()
    today = datetime.fromtimestamp(now, IST).date().isoformat()
    for rule in [a for a in read()["alerts"] if a["active"] and a.get("lastFired") != today]:
        try:
            quote = fetch(f"/api/quote?symbol={rule['symbol']}")
            bars = _bars(rule["symbol"], fetch, now) if quote else None
            if not quote or not bars or not _hit(rule, quote, bars, now):
                continue
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as e:
            log.warning("alert %s skipped: %s", rule["id"], e)   # one symbol failing must not stop the rest
            continue
        msg = f"{describe(rule)} — now {quote['price']:,.2f}"
        with _lock:
            d = read()
            live = next((a for a in d["alerts"] if a["id"] == rule["id"]), None)
            if live is None:
                continue                                        # deleted while this pass ran
            live["lastFired"] = today
            _log_fire(d, msg, now)
            _write(d)
        send("Orazio alert", msg)


def _safe(fn, *args):
    try:
        fn(*args)
    except Exception:   # noqa: BLE001 — the watcher must outlive any one bad pass
        log.exception("watcher pass failed: %s", getattr(fn, "__name__", fn))


def start(app):
    """Starts the watcher thread once. Called by app.py from the process that actually serves requests."""
    global _started
    if _started:
        return
    _started = True

    def fetch(path):
        resp = app.test_client().get(path)     # through the routes: same symbol handling and fallbacks as the chart
        return resp.get_json(silent=True) if resp.status_code == 200 else None

    from . import brief, filings   # local: they need this module's store

    def loop():
        next_filings = 0
        while True:
            _safe(check_rules, fetch, notify.send)
            now = time.time()
            if now >= next_filings:
                next_filings = now + FILINGS_EVERY_SEC
                _safe(filings.check_watch, notify.send)
            if user_settings.load()["briefEnabled"]:
                _safe(brief.send_if_due, fetch, notify.send)
            time.sleep(CHECK_SEC)

    threading.Thread(target=loop, daemon=True, name="alert-watcher").start()
