"""Company fundamentals (Bloomberg's DES / FA / RV, on public data): profile, ratios, statements, and peers.

Source order: NSE MarketLens (marketlens.py) first for profile, ratios, quarterly results and peers; Yahoo where
MarketLens lags: annual statements, balance-sheet and cash-flow history, EV/EBITDA, any ratio it leaves empty, any
quarter it hasn't picked up yet, and stocks it doesn't carry. Each response says which source answered each field.

* Statements: Yahoo Finance through yfinance (quarterly and annual income statement, balance sheet, cash flow), which
  read Yahoo's timeseries API. Ratios are computed here from them plus price and share count (fast_info): P/E on
  trailing-twelve-month EPS, P/B, ROE, margin, debt/equity, EV/EBITDA, revenue growth.
* Description, sector, forward P/E, beta, dividend yield: Yahoo's quoteSummary (Ticker.info) when it answers. It
  needs a session crumb and answers bursts with 429 (measured 13 Nov 2026), so the panel never depends on it.
* Peers: NSE's NIFTY 500 list tags every stock with an industry (nsearchives ind_nifty500list.csv). Peers are the
  stocks in the same industry closest in free-float market cap (NSE market watch).
NSE's own results-comparison API stopped at Dec 2024 (checked 13 Nov 2026), so it isn't used.
Amounts are ₹ crore, EPS in ₹. Some Indian companies report to Yahoo in another currency (Infosys files in USD): the
statements are converted at today's rate (ponytail: past periods at today's rate, so growth rates are unaffected but
old absolute numbers drift with the currency).
"""
import csv
import io
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import yfinance as yf

from . import cache, marketlens
from .cache import cached
from .http_clients import nse_http, yahoo_http

TTL = 6 * 3600
TIMESERIES = "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{}"
LIST_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
PEERS = 8
INCOME = (("Total Revenue", "revenue"), ("EBITDA", "ebitda"), ("Operating Income", "operatingIncome"),
          ("Net Income", "netIncome"), ("Diluted EPS", "eps"))
BALANCE = (("Total Assets", "totalAssets"), ("Total Debt", "totalDebt"), ("Cash And Cash Equivalents", "cash"),
           ("Stockholders Equity", "equity"))
CASH = (("Operating Cash Flow", "operatingCashFlow"), ("Capital Expenditure", "capex"), ("Free Cash Flow", "freeCashFlow"))
PEER_KEYS = ("marketCapCr", "pe", "pb", "roe", "roce", "margin", "dividendYield", "evEbitda", "revenueGrowth")
PEER_FILL = ("marketCapCr", "pe", "pb", "roe", "margin")
MEDIAN_KEYS = ("pe", "pb", "roe", "roce", "margin", "evEbitda", "revenueGrowth")


def _finite(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def statement(df, rows, per_share=("eps",)):
    """A yfinance statement (rows = line items, columns = period ends, newest first) -> periods oldest first,
    each {period: 'YYYY-MM-DD', <key>: ₹ Cr | EPS in ₹}. Missing lines stay None."""
    if df is None or getattr(df, "empty", True):
        return []
    out = []
    for col in reversed(list(df.columns)):
        p = {"period": str(col)[:10]}
        for line, key in rows:
            v = _finite(df.at[line, col]) if line in df.index else None
            p[key] = None if v is None else (round(v, 4) if key in per_share else round(v / 1e7, 2))
        if any(p[k] is not None for _, k in rows):
            out.append(p)
    return out


def _days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def ttm(quarterly, annual, key):
    """Trailing twelve months of `key`: the last four quarters when they are consecutive (Yahoo's quarterly list has
    gaps), else the latest fiscal year."""
    q = [p for p in quarterly if p.get(key) is not None][-4:]
    if len(q) == 4 and _days(q[0]["period"], q[-1]["period"]) <= 290:
        return sum(p[key] for p in q)
    a = [p for p in annual if p.get(key) is not None]
    return a[-1][key] if a else None


def yoy(quarterly, annual, key="revenue"):
    """Latest quarter against the same quarter a year earlier, else latest year against the one before, in %."""
    q = [p for p in quarterly if p.get(key)]
    if q:
        last = q[-1]
        prior = next((p for p in q if 350 <= _days(p["period"], last["period"]) <= 380), None)
        if prior:
            return round((last[key] / prior[key] - 1) * 100, 2)
    a = [p for p in annual if p.get(key)]
    return round((a[-1][key] / a[-2][key] - 1) * 100, 2) if len(a) >= 2 else None


def _div(a, b, scale=1.0):
    """a / b x scale, or None when either is missing or b is not positive (a P/E on a loss is meaningless)."""
    if a is None or b is None or b <= 0:
        return None
    return round(a / b * scale, 2)


def _from_info(info, key, f):
    v = _finite(info.get(key))
    return None if v is None else f(v)


def ratios(quarterly, annual, balance, price, shares, info=None):
    """Valuation and quality ratios from the statements; info (Yahoo quoteSummary) only fills what can't be computed."""
    info = info or {}
    eps, ni, rev, ebitda = (ttm(quarterly, annual, k) for k in ("eps", "netIncome", "revenue", "ebitda"))
    bal = balance[-1] if balance else {}
    equity, debt, cash = bal.get("equity"), bal.get("totalDebt"), bal.get("cash")
    mcap = price * shares / 1e7 if price and shares else None
    ev = mcap + (debt or 0) - (cash or 0) if mcap else None
    mine = {
        "marketCapCr": round(mcap) if mcap else None, "pe": _div(price, eps), "forwardPe": None, "pb": _div(mcap, equity),
        "evEbitda": _div(ev, ebitda), "roe": _div(ni, equity, 100), "margin": _div(ni, rev, 100),
        "debtToEquity": _div(debt, equity) if debt is not None else None, "revenueGrowth": yoy(quarterly, annual),
        "eps": round(eps, 2) if eps is not None else None, "bookValue": _div(equity * 1e7, shares) if equity else None,
        "dividendYield": None, "beta": None,
    }
    fill = {   # key -> (Yahoo info key, its units -> ours)
        "marketCapCr": ("marketCap", lambda v: round(v / 1e7)), "pe": ("trailingPE", lambda v: round(v, 2)),
        "forwardPe": ("forwardPE", lambda v: round(v, 2)), "pb": ("priceToBook", lambda v: round(v, 2)),
        "evEbitda": ("enterpriseToEbitda", lambda v: round(v, 2)), "roe": ("returnOnEquity", lambda v: round(v * 100, 2)),
        "margin": ("profitMargins", lambda v: round(v * 100, 2)), "debtToEquity": ("debtToEquity", lambda v: round(v / 100, 2)),
        "revenueGrowth": ("revenueGrowth", lambda v: round(v * 100, 2)), "eps": ("trailingEps", lambda v: round(v, 2)),
        "bookValue": ("bookValue", lambda v: round(v, 2)), "dividendYield": ("dividendYield", lambda v: round(v, 2)),
        "beta": ("beta", lambda v: round(v, 2)),
    }
    return {k: v if v is not None else _from_info(info, *fill[k]) for k, v in mine.items()}


class _NoData(Exception):
    pass


def _cached_or_empty(key, fn, empty):
    """cached(), except a failed fetch (raised _NoData) isn't stored, so the next ask retries."""
    try:
        return cached(key, TTL, fn)
    except _NoData:
        return empty


def _info(chart_symbol):
    def fetch():
        try:
            info = yf.Ticker(chart_symbol).info or {}
        except Exception as e:   # noqa: BLE001 — Yahoo answers garbage in many shapes
            raise _NoData from e
        if not (info.get("longName") or info.get("shortName")):
            raise _NoData
        return info
    return _cached_or_empty(("fund-info", chart_symbol), fetch, {})


def reporting_currency(chart_symbol):
    """The currency Yahoo's statements are in (its timeseries carries it per value; yfinance drops it). INR on failure."""
    try:
        d = yahoo_http.get(TIMESERIES.format(chart_symbol), params={"type": "annualTotalRevenue", "period1": 1500000000,
                                                                    "period2": int(time.time()) + 86400}, timeout=10).json()
        rows = d["timeseries"]["result"][0].get("annualTotalRevenue") or []
        return next((x["currencyCode"] for x in reversed(rows) if x and x.get("currencyCode")), "INR")
    except Exception:   # noqa: BLE001
        return "INR"


def convert(periods, rate):
    return [{k: (round(v * rate, 2) if isinstance(v, (int, float)) and k != "period" else v) for k, v in p.items()} for p in periods]


def _safe(tk, attr):
    try:
        return getattr(tk, attr)
    except Exception:   # noqa: BLE001
        return None


def metrics(chart_symbol, with_info=True):
    """Statements + computed ratios for one symbol, cached. {} if Yahoo has no statements for it."""
    def fetch():
        tk = yf.Ticker(chart_symbol)
        quarterly, annual = statement(_safe(tk, "quarterly_income_stmt"), INCOME), statement(_safe(tk, "income_stmt"), INCOME)
        if not (quarterly or annual):
            raise _NoData
        try:
            fi = tk.fast_info
            price, shares = _finite(fi["lastPrice"]), _finite(fi["shares"])
        except Exception:   # noqa: BLE001
            price = shares = None
        out = {"quarterly": quarterly, "annual": annual, "balance": statement(_safe(tk, "balance_sheet"), BALANCE),
               "cashflow": statement(_safe(tk, "cashflow"), CASH) if with_info else []}
        cur = reporting_currency(chart_symbol) if chart_symbol.endswith(".NS") else "INR"
        rate = None
        if cur != "INR":
            try:
                rate = _finite(yf.Ticker(f"{cur}INR=X").fast_info["lastPrice"])
            except Exception:   # noqa: BLE001
                rate = None
            if not rate:
                raise _NoData   # mixing USD statements with a ₹ price would make every ratio wrong
            out = {k: convert(v, rate) for k, v in out.items()}
        return {**out, "price": price, "shares": shares, "reportedIn": cur, "fxRate": rate}
    m = _cached_or_empty(("fund-metrics", chart_symbol, with_info), fetch, {})
    if not m:
        return {}
    info = _info(chart_symbol) if with_info else {}
    return {**m, "info": info, "ratios": ratios(m["quarterly"], m["annual"], m["balance"], m["price"], m["shares"], info)}


def merge(primary, fallback):
    """Field by field: the primary (NSE MarketLens) value where it has one, else the fallback (Yahoo); plus which
    source answered each field."""
    out, src = {}, {}
    for k in {**fallback, **primary}:
        if primary.get(k) is not None:
            out[k], src[k] = primary[k], "nse"
        else:
            out[k], src[k] = fallback.get(k), ("yahoo" if fallback.get(k) is not None else None)
    return out, src


def fresher(nse_q, yahoo_q):
    """NSE's quarters unless Yahoo already has a newer one (MarketLens lagging a fresh results filing)."""
    if nse_q and (not yahoo_q or nse_q[-1]["period"] >= yahoo_q[-1]["period"]):
        return nse_q, "nse"
    return yahoo_q, ("yahoo" if yahoo_q else None)


def fundamentals(chart_symbol):
    """NSE MarketLens first (profile, ratios, quarters); Yahoo for what it lacks (annual statements, balance sheet and
    cash-flow history, EV/EBITDA) and for any field or quarter where MarketLens is missing or behind."""
    t = marketlens.ticker(chart_symbol)
    s = marketlens.stock(t) if t else None
    nse_q = marketlens.quarterly(t) if s else []
    m = metrics(chart_symbol, with_info=s is None)   # Yahoo's rate-limited profile API only when NSE has no profile
    if not s and not m:
        return {"available": False, "symbol": chart_symbol, "reason": "Neither NSE MarketLens nor Yahoo has fundamentals for this symbol right now."}
    ratios_, sources = merge(marketlens.ratios(s, nse_q) if s else {}, m.get("ratios") or {})
    quarters, q_source = fresher(nse_q, m.get("quarterly") or [])
    info = m.get("info") or {}
    s = s or {}
    listing = industries().get(t or "")
    ts = _finite(info.get("earningsTimestamp"))
    return {
        "available": True, "symbol": chart_symbol,
        "name": s.get("name") or info.get("longName") or (listing[0] if listing else chart_symbol),
        "sector": s.get("subSector") or info.get("sector") or (listing[1] if listing else None), "industry": s.get("sector") or info.get("industry"),
        "summary": marketlens.plain(s.get("description")) or info.get("longBusinessSummary"),
        "website": s.get("website") or info.get("website"), "headquarters": s.get("headquarters"), "founded": s.get("foundedYear"),
        "employees": info.get("fullTimeEmployees"), "nextEarnings": int(ts) if ts else None,
        "price": s.get("lastTradedPrice") or m.get("price"), "ratios": ratios_, "ratioSource": sources,
        "quarterly": quarters, "quarterlySource": q_source,
        "annual": m.get("annual") or [], "balance": m.get("balance") or [], "cashflow": m.get("cashflow") or [],
        "reportedIn": m.get("reportedIn", "INR"), "fxRate": m.get("fxRate"), "nseUpdated": s.get("lastUpdated"),
        "profileComplete": bool(s or info),
    }


# ---------- peers ----------
def parse_list(text):
    """NSE's index list CSV -> {symbol: (company, industry)}."""
    return {r["Symbol"].strip(): (r["Company Name"].strip(), r["Industry"].strip())
            for r in csv.DictReader(io.StringIO(text.lstrip("﻿"))) if r.get("Symbol") and r.get("Industry")}


def industries():
    def fetch():
        try:
            r = nse_http.get(LIST_URL, timeout=10)
        except Exception as e:   # noqa: BLE001
            raise _NoData from e
        got = parse_list(r.text) if r.status_code == 200 else {}
        if not got:
            raise _NoData
        return got
    return _cached_or_empty(("nifty500-list",), fetch, {})


def pick_peers(symbol, listing, sizes, n=PEERS):
    """Same-industry stocks nearest in size (by log free-float market cap), the stock itself excluded."""
    if symbol not in listing:
        return []
    ind = listing[symbol][1]
    me = sizes.get(symbol)
    same = [s for s, (_, i) in listing.items() if i == ind and s != symbol]
    if me:
        same.sort(key=lambda s: abs(math.log(sizes[s] / me)) if sizes.get(s) else 99)
    return same[:n]


def _market_watch():
    from . import screener   # local: screener pulls technicals at import
    try:
        return {r["symbol"]: r for r in screener._rows("NIFTY 500") if r.get("symbol")}
    except Exception:   # noqa: BLE001
        return {}


def _median(vals):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    m = len(v) // 2
    return round(v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2, 2)


def _industry_peers(sym):
    """Fallback when NSE has no peer list: NIFTY 500 stocks in the same industry, nearest in free-float market cap."""
    listing = industries()
    if sym not in listing:
        return [], None
    mw = _market_watch()
    return pick_peers(sym, listing, {s: _finite(r.get("ffmc")) for s, r in mw.items()}), listing[sym][1]


def _peer_row(sym, names):
    st = marketlens.stock(sym)
    if st:
        r = marketlens.ratios(st)
        if any(r.get(k) is None for k in ("pe", "pb", "roe")):   # MarketLens left a key ratio blank: Yahoo fills it
            y = (metrics(f"{sym}.NS", with_info=False) or {}).get("ratios") or {}
            r = {k: (y.get(k) if v is None and k in PEER_FILL else v) for k, v in r.items()}   # core blanks only: no new columns for one row
        return {"symbol": sym, "chartSymbol": f"{sym}.NS", "name": st.get("name") or names.get(sym, (sym,))[0],
                "price": st.get("lastTradedPrice"), "ch365": st.get("oneYearReturn"), "source": "nse",
                **{k: r.get(k) for k in PEER_KEYS}}
    r = (metrics(f"{sym}.NS", with_info=False) or {}).get("ratios") or {}   # not on MarketLens: Yahoo statements
    return {"symbol": sym, "chartSymbol": f"{sym}.NS", "name": names.get(sym, (sym,))[0], "price": None, "ch365": None,
            "source": "yahoo" if r else None, **{k: r.get(k) for k in PEER_KEYS}}


def peers(chart_symbol):
    """NSE MarketLens's own peer list (tight sub-industry matches), each peer's ratios from MarketLens; Yahoo only for
    a peer MarketLens doesn't carry. Falls back to NIFTY 500 industry peers when NSE lists none."""
    sym = chart_symbol.upper().removesuffix(".NS")

    def build():
        others = [p for p in marketlens.peers(sym) if p != sym][:PEERS]
        industry, basis = (marketlens.stock(sym) or {}).get("sector"), "NSE's peer list"
        if not others:
            (others, industry), basis = _industry_peers(sym), "same NIFTY 500 industry, nearest in size"
        if not others:
            return {"available": False, "reason": "No peer list for this stock on NSE MarketLens or in the NIFTY 500."}
        names = industries()
        with ThreadPoolExecutor(max_workers=4) as pool:   # Yahoo (the fallback) answers 429 to bigger bursts
            rows = list(pool.map(lambda s: _peer_row(s, names), [sym, *others]))
        med = {k: _median([r[k] for r in rows[1:]]) for k in MEDIAN_KEYS}
        return {"available": True, "industry": industry or "same industry", "basis": basis, "rows": rows, "median": med,
                "complete": all(r["source"] for r in rows)}
    got = cached(("peers", sym), TTL, build)
    if not got.get("complete", True):
        cache._store.pop(("peers", sym), None)   # some peers failed: rebuild next time (the rest are cached)
    return got
