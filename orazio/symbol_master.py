"""The symbol list the search box ranks locally, the way TradingView's and Bloomberg's finders do.

Every NSE-listed stock (NSE's public EQUITY_L.csv), each F&O stock's front-month future, the rail's
indices/commodities/crypto with their synonyms (USOIL, ^NSEI ...), index futures and the government bond
yields. Yahoo's search still covers everything else (global listings), merged in by the browser.

`pop` (0-9) breaks ties between equally good matches, a liquidity ladder standing in for TradingView's
popularity: Nifty 50 (8) > F&O (7) > Nifty 500 (6) > other NSE (5). The index lists are optional.
A failed NSE download falls back to the last copy on disk, then to the list without NSE stocks.
"""
import csv
import io
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from . import bonds, fno
from .cache import cached
from .constants import FUTURES_META, INDEX_META, SYMBOL_ALIASES
from .http_clients import nse_http
from .stats import _rows

EQUITY_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
EQUITY_COPY = Path.home() / ".orazio" / "EQUITY_L.csv"
TTL = 86400
SERIES_POP = {"EQ": 5, "BE": 2, "BZ": 2}   # BE/BZ: trade-to-trade and suspended-ish names, rarely what's meant
INDEX_FUTURES = [("NIFTY-FUT", "Nifty 50 Futures", "NFO"), ("BANKNIFTY-FUT", "Bank Nifty Futures", "NFO"),
                 ("SENSEX-FUT", "BSE Sensex Futures", "BFO")]


def parse_equity_csv(text):
    """NSE's EQUITY_L.csv -> [(symbol, company name, series)]."""
    rows = csv.reader(io.StringIO(text))
    header = [h.strip().upper() for h in next(rows, [])]
    try:
        i_sym, i_name, i_ser = header.index("SYMBOL"), header.index("NAME OF COMPANY"), header.index("SERIES")
    except ValueError:
        return []
    return [(r[i_sym].strip(), r[i_name].strip(), r[i_ser].strip()) for r in rows
            if len(r) > i_ser and r[i_sym].strip()]


def _equity_text():
    """Today's copy on disk if there is one (NSE's archive takes ~7 s cold), else download, else any old copy."""
    try:
        if time.time() - EQUITY_COPY.stat().st_mtime < TTL:
            return EQUITY_COPY.read_text(encoding="utf-8")
    except OSError:
        pass
    try:
        r = nse_http.get(EQUITY_URL, timeout=10)
        if r.status_code == 200 and r.text.startswith("SYMBOL"):
            EQUITY_COPY.parent.mkdir(parents=True, exist_ok=True)
            EQUITY_COPY.write_text(r.text, encoding="utf-8")
            return r.text
    except (requests.RequestException, OSError):
        pass
    try:
        return EQUITY_COPY.read_text(encoding="utf-8")
    except OSError:
        return ""


def _item(symbol, name, exch, type_, pop, ticker=None, alt=None, fno_=False):
    it = {"symbol": symbol, "ticker": ticker or symbol, "name": name, "exch": exch, "type": type_, "pop": pop}
    if alt:
        it["alt"] = alt
    if fno_:
        it["fno"] = True
    return it


def _members(index_name):
    try:
        return {r["symbol"] for r in _rows(index_name) if r.get("priority") != 1 and r.get("symbol")}
    except Exception:   # optional ranking hint: any NSE hiccup just means coarser popularity
        return set()


def build(equity_text, fno_stocks, nifty50=(), nifty500=()):
    items = []
    by_target = {}
    for alias, target in SYMBOL_ALIASES.items():
        by_target.setdefault(target, []).append(alias)
    for alias, (name, _, type_, exch) in INDEX_META.items():
        target = SYMBOL_ALIASES.get(alias)
        alt = [target] + [a for a in by_target.get(target, []) if a != alias] if target else None
        items.append(_item(alias, name, exch, type_, 9, alt=alt))
    for sym, name, exch in INDEX_FUTURES:
        items.append(_item(sym, name, exch, "future", 8))
    for sym, meta in FUTURES_META.items():
        items.append(_item(sym, meta["name"], "CME", "future", 6))

    names = {}
    for sym, name, series in parse_equity_csv(equity_text):
        if series not in SERIES_POP:
            continue
        names[sym] = name
        is_fno = sym in fno_stocks
        pop = 8 if sym in nifty50 else 7 if is_fno else 6 if sym in nifty500 else SERIES_POP[series]
        items.append(_item(f"{sym}.NS", name, "NSE", "stock", pop, ticker=sym, fno_=is_fno))
    for sym, company in fno_stocks.items():
        items.append(_item(f"{sym}-FUT", f"{names.get(sym) or company or sym} Futures", "NFO", "future", 4))

    for sym, m in bonds.SYMBOLS.items():
        items.append(_item(sym, f"{m['name']} {m['tenor']} Govt Bond Yield", "Govt", "bond", 3, ticker=sym.split("-")[0]))
    return items


def company_names():
    """{NSE symbol: company name as listed} — "Infosys Limited", where NSE's market watch says "INFOSYS LIMITED"."""
    return cached(("equity-names", ""), TTL, lambda: {s: n for s, n, _ in parse_equity_csv(_equity_text())})


class _Incomplete(Exception):
    pass


def _fetch():
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="symbols") as ex:   # ~5 s of NSE calls, run side by side
        text, stocks = ex.submit(_equity_text), ex.submit(fno.fno_stocks)
        n50, n500 = ex.submit(_members, "NIFTY 50"), ex.submit(_members, "NIFTY 500")
        text, stocks = text.result(), stocks.result() or {}
        items = build(text, stocks, n50.result(), n500.result())
    if not text or not stocks:
        raise _Incomplete(items)
    return items


def master():
    """Kept a day once complete; a partial list (NSE down) is served but not cached, so the next load retries."""
    try:
        return cached(("symbol-master", ""), TTL, _fetch)
    except _Incomplete as e:
        return e.args[0]
