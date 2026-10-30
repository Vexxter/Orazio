"""Events to mark on the price chart.

* NSE stocks: corporate actions (dividend, split, bonus, rights — NSE, 10 years, the list corporate_actions.py
  already fetches), results board meetings (NSE board-meeting history), and bulk/block deals in the stock over
  the last year (NSE large-deal history).
* Indian indices: days FII cash net buying or selling exceeded ₹5,000 Cr (flows.py history).
RBI policy decisions are added in the page (rbi-dates.js), since they apply to any Indian rate-sensitive chart.
Each event: {date: 'YYYY-MM-DD', kind, text}.
"""
from datetime import date, datetime, timedelta

from . import corporate_actions, flows
from .cache import cached
from .nse_client import nse_get

INDEX_ALIASES = {"NIFTY", "BANKNIFTY", "NIFTYIT", "SENSEX", "NIFTYMIDCAP", "^NSEI", "^NSEBANK", "^CNXIT", "^BSESN"}
FII_BIG_CR = 5000
TTL = 3600


def _iso(s, fmt):
    try:
        return datetime.strptime(s.title(), fmt).date().isoformat()
    except (AttributeError, ValueError):
        return None


def action_kind(subject):
    s = (subject or "").lower()
    if "split" in s or "sub-division" in s or "subdivision" in s:
        return "split"
    if "bonus" in s:
        return "bonus"
    if "dividend" in s:
        return "dividend"
    if "rights" in s:
        return "rights"
    return None


def stock_events(sym):
    out = []
    for a in corporate_actions._fetch_actions(sym):
        kind, d = action_kind(a.get("subject")), _iso(a.get("exDate"), "%d-%b-%Y")
        if kind and d:
            out.append({"date": d, "kind": kind, "text": a.get("subject", "").strip()})
    today = date.today()
    meetings = nse_get("/api/corporate-board-meetings", {"index": "equities", "symbol": sym,
                                                          "from_date": (today - timedelta(days=365 * 5)).strftime("%d-%m-%Y"),
                                                          "to_date": (today + timedelta(days=60)).strftime("%d-%m-%Y")}) or []
    seen = set()
    for m in meetings if isinstance(meetings, list) else []:
        d = _iso(m.get("bm_date"), "%d-%b-%Y")
        if d and "result" in (m.get("bm_purpose") or "").lower() and d not in seen:
            seen.add(d)
            out.append({"date": d, "kind": "results", "text": m.get("bm_purpose")})
    rng = {"symbol": sym, "from": (today - timedelta(days=365)).strftime("%d-%m-%Y"), "to": today.strftime("%d-%m-%Y")}
    for kind in ("bulk_deals", "block_deals"):
        d = nse_get("/api/historicalOR/bulk-block-short-deals", {"optionType": kind, **rng}) or {}
        for r in d.get("data", []) if isinstance(d, dict) else []:
            day = _iso(r.get("BD_DT_DATE"), "%d-%b-%Y")
            if day:
                out.append({"date": day, "kind": "deal", "text": f"{'Block' if kind == 'block_deals' else 'Bulk'} {r.get('BD_BUY_SELL', '')}: "
                                                                   f"{r.get('BD_CLIENT_NAME', '')} {r.get('BD_QTY_TRD', '')} @ {r.get('BD_TP_WATP', '')}"})
    return out


def index_events():
    out = []
    for r in flows.fii_dii():
        net = (r.get("fii") or {}).get("net")
        if net is not None and abs(net) >= FII_BIG_CR:
            out.append({"date": r["date"], "kind": "fii", "text": f"FII net {net:+,.0f} Cr"})
    return out


def events(symbol):
    symbol = (symbol or "").upper()
    nse = corporate_actions.nse_equity_symbol(symbol)
    if nse:
        return cached(("chart-events", nse), TTL, lambda: sorted(stock_events(nse), key=lambda e: e["date"]))
    if symbol in INDEX_ALIASES:
        return index_events()
    return []
