"""NSE corporate announcements and shareholding, with keyword alerts.

* Announcements: NSE's /api/corporate-announcements, one market-wide call for the last few days rather than one per
  symbol (a single symbol's full history measured 2.9 MB), cached 5 minutes. Keyword and symbol filters are local.
* Shareholding: /api/corporate-share-holdings-master, one call per symbol, cached a day. It carries the promoter,
  public and employee-trust summary only; pledges are in XBRL filings, which this doesn't read.

* Filing text: one PDF's text, page by page, so the user's own Claude can read and cite it through the MCP server.

Filing text comes from outside and is untrusted: it is escaped by the page, and marked as such for agents.
"""
import io
from datetime import datetime, timedelta
from urllib.parse import urlparse

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from . import alerts
from .cache import cached
from .constants import IST
from .http_clients import nse_http
from .nse_client import nse_get

TTL = 300
DAYS_BACK = 3
PDF_HOST = "nsearchives.nseindia.com"
MAX_PDF_BYTES = 25 * 1024 * 1024


def shape(r):
    return {"id": r.get("seq_id"), "symbol": r.get("symbol"), "chartSymbol": f"{r.get('symbol')}.NS", "name": r.get("sm_name"),
            "category": r.get("desc"), "text": r.get("attchmntText") or "", "pdf": r.get("attchmntFile") or None,
            "size": r.get("fileSize"), "time": r.get("sort_date"), "hasXbrl": bool(r.get("hasXbrl"))}


def recent(today=None):
    """Newest-first announcements for the last few days, or None when NSE didn't answer."""
    def fetch():
        day = today or datetime.now(IST).date()
        d = nse_get("/api/corporate-announcements", {"index": "equities", "from_date": f"{day - timedelta(days=DAYS_BACK):%d-%m-%Y}", "to_date": f"{day:%d-%m-%Y}"})
        if not isinstance(d, list):
            return None
        return sorted((shape(r) for r in d if r.get("symbol")), key=lambda x: x["time"] or "", reverse=True)
    return cached(("filings",), TTL, fetch)


def matches(row, keywords, symbols):
    """symbols empty = any symbol; keywords empty = any filing. A keyword is a case-insensitive phrase."""
    if symbols and row["symbol"] not in symbols:
        return False
    hay = f"{row['category']} {row['text']}".lower()
    return not keywords or any(k.lower() in hay for k in keywords)


def query(symbols=(), q=""):
    rows = recent()
    if rows is None:
        return {"available": False, "rows": []}
    words = [w.strip() for w in (q or "").split(",") if w.strip()]
    wanted = {s.split(".")[0].upper() for s in symbols if s}
    return {"available": True, "asOf": rows[0]["time"] if rows else None, "rows": [r for r in rows if matches(r, words, wanted)][:300]}


def check_watch(send):
    """Notify for new filings matching the watch. The first run only records what's already there, so turning this
    on doesn't send days of old filings."""
    watch = alerts.read()["filingWatch"]
    if not watch["keywords"]:
        return
    rows = recent()
    if not rows:
        return
    with alerts._lock:
        d = alerts.read()
        seen = set(d["filingWatch"]["seen"])
        fresh = [] if not seen else [r for r in rows if r["id"] not in seen and matches(r, watch["keywords"], set(watch["symbols"]))]
        d["filingWatch"]["seen"] = ([r["id"] for r in rows] + d["filingWatch"]["seen"])[:alerts.MAX_SEEN]
        now = datetime.now(IST).timestamp()
        for r in fresh:
            alerts._log_fire(d, f"{r['symbol']} · {r['category']}", now, "filing")
        alerts._write(d)
    for r in fresh[:10]:   # ponytail: a burst past 10 lands in the log only; a digest can replace this if bursts happen
        send(f"Filing: {r['symbol']} · {r['category']}", f"{r['text'][:300]}\n{r['pdf'] or ''}".strip())


def _pct(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def shareholding(symbol):
    """Quarterly promoter, public and employee-trust %, oldest first, with the promoter change on the quarter."""
    base = (symbol or "").upper().split(".")[0]

    def fetch():
        d = nse_get("/api/corporate-share-holdings-master", {"index": "equities", "symbol": base})
        if not isinstance(d, list):
            return None
        rows = []
        for r in d:
            try:
                when = datetime.strptime(r.get("date") or "", "%d-%b-%Y").date()
            except ValueError:
                continue
            rows.append({"period": when.isoformat(), "promoter": _pct(r.get("pr_and_prgrp")), "public": _pct(r.get("public_val")),
                         "employeeTrusts": _pct(r.get("employeeTrusts")), "filed": r.get("broadcastDate"), "xbrl": r.get("xbrl") or None})
        rows.sort(key=lambda x: x["period"])
        for prev, cur in zip(rows, rows[1:]):
            if prev["promoter"] is not None and cur["promoter"] is not None:
                cur["promoterChange"] = round(cur["promoter"] - prev["promoter"], 2)
        return rows
    rows = cached(("shareholding", base), 86400, fetch)
    if rows is None:
        return {"available": False, "symbol": base, "rows": []}
    return {"available": bool(rows), "symbol": base, "asOf": rows[-1]["period"] if rows else None, "rows": rows}


def check_pdf_url(url):
    """Only NSE's own archive: this fetches whatever URL it's given, so anything else would be a way to probe the network."""
    u = urlparse(url or "")
    if u.scheme != "https" or u.hostname != PDF_HOST or not u.path.lower().endswith(".pdf"):
        raise ValueError("Only PDF links on NSE's archive can be read")


def pdf_pages(content):
    """PDF bytes -> [{page, text}] for the pages that have text."""
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [{"page": i + 1, "text": (p.extract_text() or "").strip()} for i, p in enumerate(reader.pages)]
    except (PyPdfError, ValueError, KeyError, TypeError) as e:
        raise ValueError(f"Couldn't read that PDF ({type(e).__name__})") from None
    return [p for p in pages if p["text"]]


def filing_text(url):
    check_pdf_url(url)

    def fetch():
        r = nse_http.get(url, timeout=40, stream=True)
        if r.status_code != 200:
            raise ValueError(f"NSE answered HTTP {r.status_code} for that PDF")
        body = r.raw.read(MAX_PDF_BYTES + 1, decode_content=True)
        if len(body) > MAX_PDF_BYTES:
            raise ValueError("That PDF is over 25 MB")
        pages = pdf_pages(body)
        if not pages:
            raise ValueError("That PDF has no readable text (it may be a scan)")
        return {"url": url, "pages": pages}
    return cached(("filing-text", url), 86400, fetch)
