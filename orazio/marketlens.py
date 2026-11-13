"""NSE MarketLens (marketlens.nseindia.com): NSE's own screener site, whose JSON API answers without login or key.

Unofficial: the paths come from the site's Next.js bundles (probed 13 Nov 2026), so they can change without notice.
Every call here returns None on any failure, and callers fall back to Yahoo. Units as measured:
  marketCap ₹; quarterly figures ₹ lakh; netProfit and totalEquity in the same unit (₹ million), so their ratio is
  ROE; `eps` is the latest QUARTER's EPS, not trailing twelve months; returnOnEquity, revenueGrowth, industryPe and
  beta are placeholders (0 or 1) and must not be shown.
"""
import re
from datetime import datetime

import requests

from .cache import cached

BASE = "https://marketlens.nseindia.com"
TTL = 1800
_http = requests.Session()
_http.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
                      "Accept": "application/json", "Referer": f"{BASE}/screener"})


class _Miss(Exception):
    pass


def _get(path):
    """data of one API call, cached; None on 404, network trouble or an unexpected shape (not cached, so it retries)."""
    def fetch():
        try:
            r = _http.get(BASE + path, timeout=10)
            d = r.json() if r.status_code == 200 else None
        except (requests.RequestException, ValueError) as e:
            raise _Miss from e
        if not isinstance(d, dict) or not d.get("success") or d.get("data") is None:
            raise _Miss
        return d["data"]
    try:
        return cached(("marketlens", path), TTL, fetch)
    except _Miss:
        return None


def ticker(chart_symbol):
    """'TCS.NS' -> 'TCS'; None for anything that isn't an NSE stock."""
    s = (chart_symbol or "").upper()
    return s[:-3] if s.endswith(".NS") else None


def stock(t):
    d = _get(f"/api/stocks/{t}")
    return d if isinstance(d, dict) else None


def quarterly(t):
    """Up to five quarters, oldest first, in ₹ Cr: {period, revenue (total income), profitBeforeTax, netIncome, eps}."""
    rows = _get(f"/api/stocks/{t}/quarterly-financials")
    out = []
    for r in rows if isinstance(rows, list) else []:
        try:
            period = datetime.strptime(r["date"], "%d-%b-%Y").date().isoformat()
        except (KeyError, TypeError, ValueError):
            continue
        lakh = lambda k: round(r[k] / 100, 2) if isinstance(r.get(k), (int, float)) else None
        out.append({"period": period, "revenue": lakh("totalIncome"), "profitBeforeTax": lakh("profitBeforeTax"),
                    "netIncome": lakh("netProfitLoss"), "eps": r.get("eps") if isinstance(r.get("eps"), (int, float)) else None})
    return sorted(out, key=lambda p: p["period"])


def peers(t):
    rows = _get(f"/api/stocks/{t}/peers")
    return [r["ticker"] for r in rows if isinstance(r, dict) and r.get("ticker")] if isinstance(rows, list) else []


def _pos(v):
    return v if isinstance(v, (int, float)) and v > 0 else None


def ratios(s, q=()):
    """Ratios MarketLens has right, in the panel's units; None where it has a placeholder or nothing. `q` = quarterly()
    rows, for trailing-twelve-month EPS and year-on-year growth (its own `eps` is one quarter's)."""
    q = list(q)
    last4 = q[-4:]
    ttm_eps = round(sum(p["eps"] for p in last4), 2) if len(last4) == 4 and all(p["eps"] is not None for p in last4) else None
    growth = None
    if len(q) >= 5 and q[-1]["revenue"] and q[-5]["revenue"]:
        growth = round((q[-1]["revenue"] / q[-5]["revenue"] - 1) * 100, 2)
    np_, eq = s.get("netProfit"), s.get("totalEquity")
    de = s.get("debtToEquity")
    return {
        "marketCapCr": round(s["marketCap"] / 1e7) if _pos(s.get("marketCap")) else None,
        "pe": _pos(s.get("peRatio")), "pb": _pos(s.get("pbRatio")),
        "roe": round(np_ / eq * 100, 2) if isinstance(np_, (int, float)) and _pos(eq) else None,
        "roce": _pos(s.get("roce")), "roa": _pos(s.get("roa")),
        "margin": s.get("netMargin") if isinstance(s.get("netMargin"), (int, float)) and s.get("netMargin") != 0 else None,
        "debtToEquity": de if isinstance(de, (int, float)) and de >= 0 else None,
        "dividendYield": _pos(s.get("divYield")), "eps": ttm_eps, "bookValue": _pos(s.get("bookValue")),
        "revenueGrowth": growth, "promoterHolding": _pos(s.get("promoterHolding")),
    }


def build_query(question):
    """MarketLens's plain-English query builder: {query, read_as, suggestions} or None. Not cached: each question once."""
    try:
        r = _http.get(f"{BASE}/api/query/build", params={"question": question}, timeout=20)
        d = r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("query") else None


def plain(html):
    """MarketLens descriptions carry <br/> and mailto links: plain text, whitespace squeezed."""
    text = re.sub(r"<br\s*/?>", " ", html or "")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()
