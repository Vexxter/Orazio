"""Server-sent events: the live quote pushed to the browser as it changes.

The page used to ask for a quote every 2 s, which adds up to 2 s of lag on top of the source's own.
Here one long-lived response carries every change the moment this process sees it. Sources that
are pushed into memory (Binance, BSE) are re-read 4x a second; network-backed sources are re-read
about once a second, behind the same TTL caches /api/quote uses, so one open stream costs no more
upstream traffic than the old polling did.
"""
import json
import time

from flask import Response, request, stream_with_context

from .. import poller, quotes
from ..symbols import clean_symbol
from . import bp

PUSHED_TICK_SEC = 0.25
POLLED_TICK_SEC = 1.0
HEARTBEAT_SEC = 15


def sse(event, payload):
    """One server-sent event frame."""
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def quote_events(symbol, feed=None, build=None, pushed=None, sleep=time.sleep, clock=time.time, keep_going=lambda: True):
    """Yield a `quote` event whenever the quote changes, and a `ping` heartbeat while it doesn't
    (proxies drop silent connections, and the page needs to tell "idle market" from "dead stream"). A failing source never ends the stream."""
    build = build or (lambda s: quotes.quote_payload(s, feed=feed))
    pushed = pushed or (lambda s: quotes.is_pushed(s, feed=feed))
    last_key, last_sent = None, clock()
    while keep_going():
        try:
            payload = build(symbol)
        except Exception:  # noqa: BLE001 — one bad poll must not close the stream
            payload = None
        if payload is not None:
            key = (payload["price"], payload["marketTime"])
            if key != last_key:
                last_key, last_sent = key, clock()
                yield sse("quote", payload)
        if clock() - last_sent > HEARTBEAT_SEC:
            last_sent = clock()
            yield sse("ping", {})
        sleep(PUSHED_TICK_SEC if pushed(symbol) else POLLED_TICK_SEC)


@bp.route("/api/stream/quote")
def quote_stream():
    poller.ensure_poller()
    symbol = clean_symbol(request.args.get("symbol"))
    feed = quotes.clean_feed(request.args.get("feed"))
    return Response(stream_with_context(quote_events(symbol, feed)), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
