"""Institutional flows: FII/DII cash-market buying and selling, and participant-wise derivatives open interest.

* FII/DII cash: NSE's /api/fiidiiTradeReact gives only the latest day (provisional, ~6 pm IST). Each day seen
  is appended to ~/.orazio/fiidii.json, so the history grows from the day this app first ran; NSE has no
  public archive of it.
* Participant OI: NSE publishes fao_participant_oi_<DDMMYYYY>.csv every trading day (contracts held long and
  short by Client / DII / FII / Pro in index and stock futures and options). A missing day answers 404, which
  is a holiday once the day is safely in the past. Each day is parsed once and cached under
  ~/.orazio/participant_oi/.
"""
import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from pathlib import Path

from .cache import cached
from .constants import IST
from .http_clients import nse_http
from .nse_client import nse_get

FIIDII_FILE = Path.home() / ".orazio" / "fiidii.json"
OI_DIR = Path.home() / ".orazio" / "participant_oi"
OI_URL = "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{d:%d%m%Y}.csv"
PARTIES = ("FII", "DII", "Pro", "Client")
FETCH_BUDGET_SEC = 12
_pool = ThreadPoolExecutor(max_workers=6)


# ---------- FII / DII cash ----------
def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_fiidii(rows):
    """[{category: 'FII/FPI'|'DII', date: '29-Oct-2026', buyValue, sellValue, netValue}] -> {iso date: {fii, dii}}."""
    out = {}
    for r in rows or []:
        try:
            day = datetime.strptime(r["date"], "%d-%b-%Y").date().isoformat()
        except (KeyError, TypeError, ValueError):
            continue
        who = "fii" if str(r.get("category", "")).upper().startswith("FII") else "dii" if r.get("category") == "DII" else None
        if who:
            out.setdefault(day, {})[who] = {"buy": _num(r.get("buyValue")), "sell": _num(r.get("sellValue")), "net": _num(r.get("netValue"))}
    return out


def _load_history():
    try:
        return json.loads(FIIDII_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def fii_dii():
    def fetch():
        history = _load_history()
        latest = parse_fiidii(nse_get("/api/fiidiiTradeReact"))
        if latest:
            history.update(latest)
            FIIDII_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = FIIDII_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(history), encoding="utf-8")
            tmp.replace(FIIDII_FILE)
        return [{"date": d, **v} for d, v in sorted(history.items())]
    return cached(("fiidii",), 300, fetch)


# ---------- participant-wise open interest ----------
def parse_participant_oi(text):
    """NSE's CSV -> {party: {fut_idx_long, fut_idx_short, ...}}; None if it isn't that file."""
    lines = text.strip().splitlines()
    if len(lines) < 3 or "Participant" not in lines[0]:
        return None
    reader = csv.reader(io.StringIO("\n".join(lines[1:])))
    header = [h.strip().lower().replace(" ", "_") for h in next(reader)]
    out = {}
    for row in reader:
        if not row or not row[0].strip():
            continue
        party = row[0].strip()
        try:
            out[party] = {h: int(float(v)) for h, v in zip(header[1:], row[1:]) if v.strip()}
        except ValueError:
            continue
    return out or None


def _oi_path(d):
    return OI_DIR / f"{d:%Y%m%d}.json"


def _fetch_oi_day(d):
    """The day's table; {} for a holiday; None if not published yet / unreachable."""
    try:
        return json.loads(_oi_path(d).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        r = nse_http.get(OI_URL.format(d=d), timeout=15)
    except Exception:
        return None
    if r.status_code == 404:
        if d < datetime.now(IST).date() - timedelta(days=3):
            OI_DIR.mkdir(parents=True, exist_ok=True)
            _oi_path(d).write_text("{}", encoding="utf-8")
            return {}
        return None
    table = parse_participant_oi(r.text) if r.status_code == 200 else None
    if table:
        OI_DIR.mkdir(parents=True, exist_ok=True)
        _oi_path(d).write_text(json.dumps(table), encoding="utf-8")
    return table


def summarise(day, table):
    """The numbers traders read off this file, per party: net index futures, net index calls/puts
    (long - short contracts) and, for index futures, the share of their position that is long."""
    out = {"date": day}
    for p in PARTIES:
        t = table.get(p) or {}
        fl, fs = t.get("future_index_long", 0), t.get("future_index_short", 0)
        out[p] = {
            "futIdxNet": fl - fs,
            "futIdxLongPct": round(fl / (fl + fs) * 100, 1) if fl + fs else None,
            "callIdxNet": t.get("option_index_call_long", 0) - t.get("option_index_call_short", 0),
            "putIdxNet": t.get("option_index_put_long", 0) - t.get("option_index_put_short", 0),
            "futStkNet": t.get("future_stock_long", 0) - t.get("future_stock_short", 0),
        }
    return out


def participant_oi(days=30):
    def fetch():
        today = datetime.now(IST).date()
        cal = [today - timedelta(days=i) for i in range(int(days * 1.6) + 5)]
        cal = [d for d in cal if d.weekday() < 5]
        futures = {d: _pool.submit(_fetch_oi_day, d) for d in cal}
        wait(futures.values(), timeout=FETCH_BUDGET_SEC)
        got = sorted((d, f.result()) for d, f in futures.items() if f.done() and f.result())
        return [summarise(d.isoformat(), t) for d, t in got][-days:]
    return cached(("participant-oi", days), 120, fetch)


def payload():
    return {"cash": fii_dii(), "oi": participant_oi()}
