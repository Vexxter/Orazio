"""IPO and corporate-action calendar (Bloomberg's IPO / CACT, on public data).

* IPOs open now and coming up: NSE /api/ipo-current-issue and /api/all-upcoming-issues?category=ipo. Both were
  empty on 13 Nov 2026, so their row shape is read defensively from the field names NSE's IPO page uses.
* Recent listings: NSE /api/public-past-issues (measured: symbol, companyName, issuePrice, listingDate,
  securityType EQ/SME). The page prices them now to show the return since issue.
* Corporate actions ahead: NSE /api/corporates-corporateActions over the next 30 days (ex-dates of dividends,
  splits, bonuses, buybacks, rights), equities only.
"""
from datetime import date, datetime, timedelta

from .cache import cached
from .nse_client import nse_get

TTL = 900
AHEAD_DAYS = 30
RECENT_LISTINGS = 40


def _iso(s):
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime((s or "").strip().title(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _first(r, *keys):
    return next((r[k] for k in keys if r.get(k) not in (None, "", "-")), None)


def ipo_row(r, status):
    sym = (_first(r, "symbol") or "").strip().upper()
    return {"symbol": sym, "company": (_first(r, "companyName", "company") or sym).strip(), "status": status,
            "kind": (_first(r, "series", "securityType") or "").strip(),
            "open": _iso(_first(r, "issueStartDate", "ipoStartDate")), "close": _iso(_first(r, "issueEndDate", "ipoEndDate")),
            "priceBand": _first(r, "issuePrice", "priceBand", "priceRange"), "sizeText": _first(r, "issueSize"),
            "subscribed": _num(_first(r, "noOfTime", "subscription")), "lotSize": _num(_first(r, "lotSize", "minBidQuantity"))}


def listing_row(r):
    sym = (r.get("symbol") or "").strip().upper()
    return {"symbol": sym, "chartSymbol": f"{sym}.NS", "company": (r.get("companyName") or r.get("company") or sym).strip(),
            "kind": (r.get("securityType") or "").strip(), "issuePrice": _num(r.get("issuePrice")),
            "listed": _iso(r.get("listingDate")), "priceRange": r.get("priceRange")}


def action_kind(subject):
    s = (subject or "").lower()
    for word, kind in (("buy back", "buyback"), ("buyback", "buyback"), ("split", "split"), ("sub-division", "split"),
                       ("bonus", "bonus"), ("rights", "rights"), ("dividend", "dividend"), ("demerger", "demerger")):
        if word in s:
            return kind
    return "other"


def action_row(r):
    sym = (r.get("symbol") or "").strip().upper()
    return {"date": _iso(r.get("exDate")), "record": _iso(r.get("recDate")), "symbol": sym, "chartSymbol": f"{sym}.NS",
            "company": (r.get("comp") or "").strip(), "subject": (r.get("subject") or "").strip(), "kind": action_kind(r.get("subject"))}


def _list(path, params=None):
    d = nse_get(path, params or {})
    return d if isinstance(d, list) else None


def ipos():
    def fetch():
        cur, up, past = _list("/api/ipo-current-issue"), _list("/api/all-upcoming-issues", {"category": "ipo"}), _list("/api/public-past-issues")
        if cur is None and up is None and past is None:
            return None
        rows = [ipo_row(r, "open") for r in cur or []] + [ipo_row(r, "upcoming") for r in up or []]
        listings = sorted((listing_row(r) for r in past or []), key=lambda r: r["listed"] or "", reverse=True)
        return {"available": True, "issues": rows, "listings": listings[:RECENT_LISTINGS]}
    return cached(("ipos",), TTL, fetch) or {"available": False, "issues": [], "listings": []}


def actions(today=None):
    today = today or date.today()

    def fetch():
        rows = _list("/api/corporates-corporateActions", {"index": "equities", "from_date": today.strftime("%d-%m-%Y"),
                                                         "to_date": (today + timedelta(days=AHEAD_DAYS)).strftime("%d-%m-%Y")})
        if rows is None:
            return None
        out = [action_row(r) for r in rows if (r.get("series") or "").strip() in ("EQ", "BE", "SM", "ST")]
        return sorted((r for r in out if r["date"]), key=lambda r: (r["date"], r["symbol"]))
    got = cached(("corp-actions-ahead", today.isoformat()), TTL, fetch)
    return {"available": got is not None, "days": AHEAD_DAYS, "rows": got or []}
