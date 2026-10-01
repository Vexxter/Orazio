"""Binance's public futures websocket: the live commodity price, pushed.

Polling Binance's REST ticker gives a price at most 2 s old (our cache) plus the round trip. The
`bookTicker` stream pushes every change of the best bid/ask — measured 1 Oct 2026: ~23 updates a
second for gold, ~5 for WTI — so the live price is limited by the market, not by us. The price is
the MID of best bid and ask, which moves continuously (the last TRADE of these contracts only
prints about once a second; `aggTrade`, the usual trade stream, is empty for them). No key is
needed — it is the same public market-data stream Binance's own site uses.

The connection lives in a daemon thread and reconnects with backoff. Nothing depends on it being
up: `latest()` returns None when the newest price is older than FRESH_SEC, and callers then use the
REST quote exactly as before.
"""
import asyncio
import json
import threading
import time

import websockets

URL = "wss://fstream.binance.com/stream?streams="
FRESH_SEC = 5            # a price older than this is not "live" any more
MAX_BACKOFF_SEC = 30

_last = {}               # chart symbol -> {"price", "time" (event ms), "received" (epoch s)}
_lock = threading.Lock()
_yahoo_by_binance = {}
state = {"connected": False, "error": None, "messages": 0}


def parse_message(raw, yahoo_by_binance):
    """One combined-stream message -> (chart symbol, mid price, event time in ms), or None for
    anything that isn't a best-bid/ask update for a symbol we follow."""
    try:
        msg = json.loads(raw)
        data = msg.get("data", msg)
        if data.get("e") != "bookTicker":
            return None
        chart_symbol = yahoo_by_binance.get(data["s"])
        if chart_symbol is None:
            return None
        bid, ask = float(data["b"]), float(data["a"])
        if bid <= 0 or ask < bid:           # a crossed or empty book is not a price
            return None
        return chart_symbol, (bid + ask) / 2, int(data.get("T") or data["E"])
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def record(chart_symbol, price, event_ms, received=None):
    with _lock:
        _last[chart_symbol] = {"price": price, "time": event_ms, "received": received or time.time()}
    state["messages"] += 1


def latest(chart_symbol, now=None):
    """The newest price for a symbol if it is fresh, else None (so the caller falls back to REST)."""
    with _lock:
        tick = _last.get(chart_symbol)
    if tick is None or (now or time.time()) - tick["received"] > FRESH_SEC:
        return None
    return dict(tick)


def is_streaming(chart_symbol):
    return latest(chart_symbol) is not None


def next_backoff(current):
    return min(MAX_BACKOFF_SEC, max(1, current * 2))


async def _run(symbols):
    backoff = 1
    url = URL + "/".join(f"{b.lower()}@bookTicker" for b in symbols.values())
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, open_timeout=10) as ws:
                state.update(connected=True, error=None)
                backoff = 1
                async for raw in ws:
                    parsed = parse_message(raw, _yahoo_by_binance)
                    if parsed:
                        record(*parsed)
        except Exception as e:  # noqa: BLE001 — any failure just means "reconnect"
            state.update(connected=False, error=f"{type(e).__name__}: {e}"[:200])
        await asyncio.sleep(backoff)
        backoff = next_backoff(backoff)


def start(symbols):
    """symbols: {chart symbol: Binance futures symbol}. Idempotent per process (the poller calls it once)."""
    _yahoo_by_binance.update({binance: chart for chart, binance in symbols.items()})
    threading.Thread(target=lambda: asyncio.run(_run(symbols)), daemon=True, name="binance-stream").start()
