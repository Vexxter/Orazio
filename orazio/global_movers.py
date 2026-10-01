"""Top movers (and, for Shanghai, the up/down count) for markets NSE's feed doesn't cover.

NASDAQ: the Nasdaq-100 from Nasdaq's own quote API — live, ~100 stocks, no volume.
SSE:    Shanghai-listed A-shares (main board + STAR, ~2,300) from Sina Finance's market-centre
        list, live. Sina serves at most 100 rows per request (~1.5 s each): the movers table
        needs only the top and bottom page, while the rail's up/down count sweeps all ~24 pages
        in the background. (Eastmoney's list is quicker but returned 502s under load.)
TAIEX:  every TWSE-listed stock from TWSE's open data (STOCK_DAY_ALL). TWSE publishes it
        after the session, so this is the LAST FINISHED SESSION, and the UI says so.
KOSPI/CSI 300/S&P/Dow/SENSEX movers come from constituents.py instead.

Rows match movers.py: symbol, chartSymbol (the Yahoo ticker the chart opens), ltp, perChange,
open, high, low, volume.
"""
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import requests

from .cache import cached

UNIVERSES = ("NASDAQ", "SSE", "TAIEX")
TOP_N = 15
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def _rank(rows, as_of=None):
    rows = [r for r in rows if r["perChange"] is not None]
    return {
        "available": bool(rows), "asOf": as_of,
        "gainers": sorted(rows, key=lambda r: -r["perChange"])[:TOP_N],
        "losers": sorted(rows, key=lambda r: r["perChange"])[:TOP_N],
    }


def _nasdaq_rows():
    def fetch():
        try:
            r = requests.get("https://api.nasdaq.com/api/quote/list-type/nasdaq100",
                             headers={**_HEADERS, "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"},
                             timeout=15)
            r.raise_for_status()
            return [{"symbol": x["symbol"], "chartSymbol": x["symbol"], "ltp": _num(x.get("lastSalePrice")),
                     "perChange": _num(x.get("percentageChange")), "open": None, "high": None, "low": None,
                     "volume": None}
                    for x in r.json()["data"]["data"]["rows"]]
        except (requests.RequestException, KeyError, TypeError, ValueError):
            return None
    return cached(("movers-nasdaq", ""), 60, fetch)


_SINA = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
_SINA_HEADERS = {**_HEADERS, "Referer": "https://finance.sina.com.cn/"}


def _sina_page(page, asc):
    """One page (<=100 rows) of Shanghai A-shares ordered by % change, or None on failure."""
    try:
        r = requests.get(_SINA, params={"page": page, "num": 100, "sort": "changepercent", "asc": asc,
                                        "node": "sh_a", "symbol": "", "_s_r_a": "page"},
                         headers=_SINA_HEADERS, timeout=20)
        r.raise_for_status()
        out = []
        for x in r.json():
            price, pct = _num(x.get("trade")), _num(x.get("changepercent"))
            if not price or pct is None:  # trade 0 = suspended, no live price
                continue
            out.append({"symbol": x["code"], "chartSymbol": f"{x['code']}.SS", "ltp": price, "perChange": pct,
                        "open": _num(x.get("open")), "high": _num(x.get("high")), "low": _num(x.get("low")),
                        "volume": _num(x.get("volume")), "localName": x.get("name")})
        return out
    except (requests.RequestException, KeyError, TypeError, ValueError):
        return None


def sse_snapshot():
    """Top and bottom pages by % change — all the movers table needs. Cached 30 s."""
    def fetch():
        top, bottom = _sina_page(1, 0), _sina_page(1, 1)
        return (top or []) + (bottom or []) if (top or bottom) else None
    return cached(("movers-sse", ""), 30, fetch)


def sse_breadth():
    """Advancing/declining/flat counts over EVERY Shanghai A-share: sweeps all pages
    (4 at a time), de-duplicating by code because the ordering shifts between requests.
    Slow (~10-40 s) — call from a background thread, never from a request."""
    try:
        total = int(requests.get(_SINA.replace("getHQNodeData", "getHQNodeStockCount"), params={"node": "sh_a"},
                                 headers=_SINA_HEADERS, timeout=10).text.strip('"'))
    except (requests.RequestException, ValueError):
        return None
    pages = math.ceil(total / 100)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda p: _sina_page(p, 0), range(1, pages + 1)))
    if sum(r is None for r in results) > 2:  # a partial sweep would skew the counts
        return None
    seen = {row["symbol"]: row["perChange"] for page in results if page for row in page}
    if len(seen) < total * 0.9:
        return None
    return {"advances": sum(v > 0 for v in seen.values()), "declines": sum(v < 0 for v in seen.values()),
            "unchanged": sum(v == 0 for v in seen.values())}


def _twse_rows():
    def fetch():
        try:
            r = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", headers=_HEADERS, timeout=25)
            r.raise_for_status()
            rows, day = [], None
            for x in r.json():
                if not re.fullmatch(r"\d{4}", x.get("Code", "")):  # plain stocks; skips ETFs/warrants
                    continue
                close, change = _num(x.get("ClosingPrice")), _num(x.get("Change"))
                if not close or change is None or close - change <= 0:
                    continue
                day = day or x.get("Date")
                rows.append({"symbol": x["Code"], "chartSymbol": f"{x['Code']}.TW", "ltp": close,
                             "perChange": change / (close - change) * 100, "open": _num(x.get("OpeningPrice")),
                             "high": _num(x.get("HighestPrice")), "low": _num(x.get("LowestPrice")),
                             "volume": _num(x.get("TradeVolume")), "localName": x.get("Name")})
            return {"rows": rows, "day": day} if rows else None
        except (requests.RequestException, KeyError, TypeError, ValueError):
            return None
    return cached(("movers-twse", ""), 600, fetch)


def _roc_date(s):
    """'1150929' (Republic of China calendar, year 115) -> '29 Sep 2026'."""
    try:
        return date(int(s[:-4]) + 1911, int(s[-4:-2]), int(s[-2:])).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return None


def movers(universe):
    if universe == "NASDAQ":
        rows = _nasdaq_rows()
        out = _rank(rows or [])
    elif universe == "SSE":
        out = _rank(sse_snapshot() or [])
    elif universe == "TAIEX":
        snap = _twse_rows()
        out = _rank(snap["rows"] if snap else [], f"last close {_roc_date(snap['day'])}" if snap else None)
    else:
        out = _rank([])
    return {"universe": universe, **out}
