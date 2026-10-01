"""Company names for tickers that are just numbers to a human (688185.SS, 457190.KS, 3518.TW).

Yahoo's search endpoint returns the full English name; lookups run in parallel and are
cached (a week when found, five minutes when not, so a rate-limit hiccup can't hide a name
for long). Movers tables call attach_names(): rows whose name isn't cached yet are looked up
within a short time budget, and any that miss it show up on the next poll.
"""
import time
from concurrent.futures import ThreadPoolExecutor, wait

import requests

FOUND_TTL = 7 * 86400
MISSING_TTL = 300
BUDGET_SEC = 5
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

_cache = {}  # symbol -> (name or None, fetched_at)
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="names")


def _cached(symbol):
    hit = _cache.get(symbol)
    if hit and time.time() - hit[1] < (FOUND_TTL if hit[0] else MISSING_TTL):
        return hit
    return None


def english_name(symbol):
    hit = _cached(symbol)
    if hit:
        return hit[0]
    name = None
    try:
        r = requests.get("https://query1.finance.yahoo.com/v1/finance/search",
                         params={"q": symbol, "quotesCount": 3, "newsCount": 0}, headers=_UA, timeout=8)
        r.raise_for_status()
        match = next((q for q in r.json().get("quotes") or [] if q.get("symbol") == symbol), None)
        if match:
            name = match.get("longname") or match.get("shortname")
    except (requests.RequestException, ValueError):
        pass
    _cache[symbol] = (name, time.time())
    return name


def attach_names(rows):
    """Set row['name'] on every row with a chartSymbol, waiting at most BUDGET_SEC."""
    pending = {}
    for row in rows:
        sym = row.get("chartSymbol")
        if not sym:
            continue
        hit = _cached(sym)
        if hit:
            row["name"] = hit[0]
        elif sym not in pending:
            pending[sym] = _pool.submit(english_name, sym)
    if pending:
        wait(pending.values(), timeout=BUDGET_SEC)
        for row in rows:
            fut = pending.get(row.get("chartSymbol"))
            if fut is not None and fut.done():
                row["name"] = fut.result()
