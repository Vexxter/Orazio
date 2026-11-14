"""Macro: the week's economic calendar and Indian banking-system liquidity.

* Calendar: ForexFactory's public weekly feed (nfs.faireconomy.media), the major currencies' scheduled releases
  with impact, forecast and previous. It has no INR events and no actuals.
* Liquidity: RBI's daily "Money Market Operations" press release (rbi.org.in, published the next morning):
  overnight call / TREPS / market-repo weighted rates, the day's SDF (banks parking cash) and MSF (banks
  borrowing at the penal rate), and net liquidity injected (+) or absorbed (-) by RBI. Each release is parsed
  once and cached under ~/.orazio/rbi_mmo/ (they never change). RBI's index lists only the last ~8 releases, so
  the history grows from the day this app first ran.
"""
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests

from .cache import cached
from .constants import USER_AGENT

CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CAL_FILE = Path.home() / ".orazio" / "calendar.json"
RBI_INDEX = "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"
MMO_DIR = Path.home() / ".orazio" / "rbi_mmo"
_http = requests.Session()
_http.headers.update({"User-Agent": USER_AGENT})
_pool = ThreadPoolExecutor(max_workers=6)


# ---------- calendar ----------
def _shape_event(e):
    return {"title": e.get("title"), "country": e.get("country"), "time": e.get("date"), "impact": e.get("impact"),
            "forecast": e.get("forecast") or None, "previous": e.get("previous") or None}


def calendar():
    """The feed rate-limits hard (429 after a few calls), so the last good copy is kept on disk and served
    whenever it refuses."""
    def fetch():
        try:
            r = _http.get(CAL_URL, timeout=15)
            rows = [_shape_event(e) for e in r.json()] if r.status_code == 200 else None
        except (requests.RequestException, ValueError):
            rows = None
        if rows:
            CAL_FILE.parent.mkdir(parents=True, exist_ok=True)
            CAL_FILE.write_text(json.dumps(rows), encoding="utf-8")
            return rows
        try:
            return json.loads(CAL_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    return cached(("macro-calendar",), 3600, fetch)


# ---------- RBI money market operations ----------
def _cells(row_html):
    cells = [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c))).strip()
             for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S)]
    return [c for c in cells if c]


def _num(s):
    try:
        return float(s.replace(",", ""))
    except (AttributeError, ValueError):
        return None


def parse_mmo(page):
    """One release -> {date, call, treps, repo, sdf, msf, net}; rates in %, amounts in ₹ crore."""
    m = re.search(r"Money Market Operations as on ([A-Z][a-z]+ \d{1,2}, \d{4})", page)
    if not m:
        return None
    out = {"date": datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()}
    labels = {"I. Call Money": "call", "II. Triparty Repo": "treps", "III. Market Repo": "repo"}
    section = None
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        c = _cells(row)
        if not c:
            continue
        if c[0].startswith("A. Overnight"):
            section = "overnight"
        elif c[0].startswith("B. Term"):
            section = None
        elif section == "overnight" and c[0] in labels and len(c) >= 3:
            out[labels[c[0]]] = _num(c[2])
        elif c[0].startswith("3. MSF") and len(c) >= 5 and "msf" not in out:
            out["msf"] = _num(c[4])
        elif c[0].startswith("4. SDF") and len(c) >= 5 and "sdf" not in out:
            out["sdf"] = _num(c[4])
        elif c[0].startswith("F. Net liquidity injected") and len(c) >= 2:
            out["net"] = _num(c[-1])
    return out


def _release(prid):
    path = MMO_DIR / f"{prid}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        r = _http.get(RBI_INDEX, params={"prid": prid}, timeout=20)
    except requests.RequestException:
        return None
    row = parse_mmo(r.text) if r.status_code == 200 else None
    if row:
        MMO_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(row), encoding="utf-8")
    return row


def liquidity():
    def fetch():
        try:
            index = _http.get(RBI_INDEX, timeout=20).text
        except requests.RequestException:
            index = ""
        prids = re.findall(r"prid=(\d+)>Money Market Operations as on", index)
        rows = [r for r in _pool.map(_release, prids[:25]) if r]
        for path in MMO_DIR.glob("*.json") if MMO_DIR.exists() else []:   # older days RBI's index no longer lists
            try:
                rows.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return sorted({r["date"]: r for r in rows}.values(), key=lambda r: r["date"])
    return cached(("rbi-liquidity",), 1800, fetch)


def payload():
    return {"calendar": calendar(), "liquidity": liquidity()}
