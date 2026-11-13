"""Client for BSE's live push stream.

BSE's own website connects to a Socket.IO v4 server (websocket transport only) at
bnotification.bseindia.com and joins two channels: `SenSexValue` and
`SensexIndicativePrice`. Measured: it pushes SENSEX roughly twice a second, against
once a minute for BSE's REST endpoint, and the indicative channel carries the
auction fields (`indicativePriceFlag`, `todayIndexClose`, `IChange`, `IpercChange`).

The channel names and message shapes were read out of BSE's own page code
(beta.bseindia.com/D90/Controller/factoryother.js), not from any published docs.

TLS: the server does not send its intermediate certificate (browsers repair that
themselves), so a stock client fails verification. Verification is NOT disabled.
Instead the missing intermediate is fetched from the leaf certificate's own "CA Issuers"
link and added to the trust store, so the chain is still fully checked.
"""
import asyncio
import json
import os
import ssl
import tempfile
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import certifi
import requests
import websockets
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import AuthorityInformationAccessOID, ExtensionOID

HOST = "bnotification.bseindia.com"
URI = f"wss://{HOST}/socket.io/?EIO=4&transport=websocket"
CHANNELS = ("SenSexValue", "SensexIndicativePrice")
IST = timezone(timedelta(hours=5, minutes=30))
CHAIN_FILE = os.path.join(tempfile.gettempdir(), "orazio_bse_chain.pem")


def _num(v):
    """BSE sends numbers as strings with thousands separators, and '-' for 'not set'."""
    if v is None:
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def _stamp(s):
    """'2026-09-21 14:55:0' (seconds are not zero-padded) -> epoch seconds."""
    try:
        date, time_part = s.split(" ")
        h, m, sec = (int(x) for x in time_part.split(":"))
        y, mo, d = (int(x) for x in date.split("-"))
        return int(datetime(y, mo, d, h, m, sec, tzinfo=IST).timestamp())
    except (ValueError, AttributeError):
        return None


def build_ssl_context():
    """A verifying SSL context that trusts certifi's roots plus BSE's missing intermediate."""
    if not os.path.exists(CHAIN_FILE) or time.time() - os.path.getmtime(CHAIN_FILE) > 7 * 86400:
        leaf = x509.load_pem_x509_certificate(ssl.get_server_certificate((HOST, 443)).encode())
        aia = leaf.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
        urls = [d.access_location.value for d in aia
                if d.access_method == AuthorityInformationAccessOID.CA_ISSUERS]
        extra = b""
        for url in urls:
            body = requests.get(url, timeout=15).content
            try:
                cert = x509.load_der_x509_certificate(body)
            except ValueError:
                cert = x509.load_pem_x509_certificate(body)
            extra += cert.public_bytes(serialization.Encoding.PEM)
        if not extra:
            raise RuntimeError("could not obtain BSE's intermediate certificate")
        with open(CHAIN_FILE, "wb") as f:
            f.write(open(certifi.where(), "rb").read() + b"\n" + extra)
    return ssl.create_default_context(cafile=CHAIN_FILE)


class BseStream:
    def __init__(self, on_tick=None):
        self._lock = threading.Lock()
        self._on_tick = on_tick
        self.latest = None                 # most recent parsed SENSEX tick
        self.latest_at = 0.0               # wall-clock time we received it
        self.history = deque(maxlen=20000)  # (epoch, value, indicative_close)
        self.connected = False
        self.last_error = None
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=lambda: asyncio.run(self._forever()), daemon=True, name="bse-stream").start()

    # ---- reading ------------------------------------------------------------
    def fresh(self, max_age=15):
        with self._lock:
            return self.latest is not None and time.time() - self.latest_at < max_age

    def snapshot(self):
        with self._lock:
            return dict(self.latest) if self.latest else None

    def series(self, limit=900):
        with self._lock:
            return list(self.history)[-limit:]

    # ---- connection loop ------------------------------------------------------
    async def _forever(self):
        backoff = 2
        while True:
            try:
                await self._session()
                backoff = 2
            except Exception as e:  # any failure: record it, back off, retry. REST covers the gap.
                self.last_error = f"{type(e).__name__}: {str(e)[:120]}"
            self.connected = False
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def _session(self):
        ctx = await asyncio.get_running_loop().run_in_executor(None, build_ssl_context)
        async with websockets.connect(URI, ssl=ctx, origin="https://www.bseindia.com",
                                      open_timeout=15, ping_interval=None,
                                      additional_headers={"User-Agent": "Mozilla/5.0"}) as ws:
            await ws.recv()          # engine.io open packet
            await ws.send("40")      # connect to the default namespace
            joined = False
            while True:
                # The server pings every 25s; if it goes quiet for far longer, reconnect.
                msg = await asyncio.wait_for(ws.recv(), timeout=60)
                if msg == "2":
                    await ws.send("3")
                    continue
                if msg.startswith("40") and not joined:
                    joined = True
                    self.connected = True
                    self.last_error = None
                    for ch in CHANNELS:
                        await ws.send("42" + json.dumps(["joinChannel", {"channel": ch}]))
                    continue
                if msg.startswith("42"):
                    self._handle(msg[2:])

    def _handle(self, frame):
        try:
            event, payload = json.loads(frame)
            if event != "SensexIndicativePrice":
                return
            d = json.loads(payload) if isinstance(payload, str) else payload
        except (ValueError, TypeError):
            return
        value = _num(d.get("indexValue")) or _num(d.get("currentIndex"))
        t = _stamp(d.get("datettime")) or int(time.time())
        if value is None:
            return
        tick = {
            "t": t, "value": value,
            "open": _num(d.get("indexOpen")), "high": _num(d.get("indexHigh")), "low": _num(d.get("indexLow")),
            "prevClose": _num(d.get("indexClose")),
            "indicativeClose": _num(d.get("todayIndexClose")),
            "indicativeChange": _num(d.get("IChange")),
            "indicativePct": _num(d.get("IpercChange")),
            "flag": d.get("indicativePriceFlag"),
            "session": d.get("session"),
        }
        with self._lock:
            self.latest, self.latest_at = tick, time.time()
            self.history.append((t, value, tick["indicativeClose"]))
        if self._on_tick:
            try:
                self._on_tick(tick)
            except Exception:
                pass  # a consumer bug must never take the stream down
