"""The morning brief as a notification: a few cross-asset lines, sent once per weekday at the user's chosen time,
with a link back to the full Brief tab. Off until the user turns it on."""
from datetime import datetime

from . import alerts, user_settings
from .config import settings
from .constants import IST

TILES = (("NIFTY", "NIFTY"), ("GIFTNIFTY", "GIFT Nifty"), ("^INDIAVIX", "India VIX"), ("INR=X", "USD/INR"),
         ("BRENT", "Brent"), ("GOLD", "Gold"), ("SPX", "S&P 500"))


def text(fetch):
    lines = []
    for sym, label in TILES:
        q = fetch(f"/api/quote?symbol={sym}")
        if q and q.get("price") is not None:
            lines.append(f"{label} {q['price']:,.2f} ({q.get('changePercent') or 0:+.2f}%)")
    flows = (fetch("/api/flows") or {}).get("cash") or []
    if flows:
        last = flows[-1]
        lines.append(f"FII {((last.get('fii') or {}).get('net') or 0):,.0f} / DII {((last.get('dii') or {}).get('net') or 0):,.0f} ₹ Cr ({last.get('date')})")
    lines.append(f"Full brief: http://{settings.HOST}:{settings.PORT}/?cmd=:BRIEF")
    return "\n".join(lines)


def due(now_ist, at, last_day):
    """True on a weekday at or after the chosen time, if today's hasn't gone yet."""
    return now_ist.weekday() < 5 and now_ist.strftime("%H:%M") >= at and last_day != now_ist.date().isoformat()


def send_if_due(fetch, send, now=None):
    now = now or datetime.now(IST)
    with alerts._lock:
        d = alerts.read()
        if not due(now, user_settings.load()["briefTime"], d.get("briefDay")):
            return
        d["briefDay"] = now.date().isoformat()   # claimed first: a failed send must not repeat every 20 s
        alerts._write(d)
    send("Orazio morning brief", text(fetch))
