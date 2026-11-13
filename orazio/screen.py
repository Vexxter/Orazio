"""Plain-English stock screening over NSE MarketLens data: "debt free companies with ROCE above 20" -> a filter -> stocks.

MarketLens turns a question into a filter expression (/api/query/build: "Long Term Borrowings (in Lakhs) <= 0 AND Return
on Capital Employed (ROCE) > 20") but runs custom expressions in its own page, so Orazio evaluates them here, over a
universe it assembles: MarketLens's 19 sector lists (~840 stocks) plus every NIFTY 500 stock they miss (~290 more),
each a full 108-field record. Field names map to data fields through MarketLens's ratio gallery.
Units follow MarketLens's own client: values compare as stored, except market cap (stored in ₹, typed in crore) and
volume (stored in shares, typed in lakh).
ponytail: AND-joined clauses only (MarketLens's builder emits AND); an OR or parenthesis is reported as unsupported.
"""
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from . import marketlens
from .cache import cached

TTL = 1800
OPS = (">=", "<=", "!=", ">", "<", "=")
SCALE = {"marketCap": 1e7, "volume": 1e5}    # typed unit -> stored unit
SHOW = 200
ZERO_MEANS_NONE = {"peRatio", "pbRatio", "roce", "roa", "eps"}   # MarketLens stores "no value" as 0: P/E 0 isn't cheap
log = logging.getLogger(__name__)


def gallery():
    """{display name (lower case, spaces squeezed): field}, from MarketLens's ratio gallery."""
    def fetch():
        cats = marketlens._get("/api/stocks/ratio-gallery") or []
        out = {}
        for c in cats:
            for r in c.get("ratios", []):
                for name in {r.get("name"), r.get("insertText")}:
                    if name and r.get("field"):
                        out[_norm(name)] = r["field"]
        return out
    return cached(("ml-gallery",), 24 * 3600, fetch)


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _operand(text, names):
    """A clause side -> ('field', name), ('num', value) or ('calc', side, op, number) for '52W High * 0.95'.
    Numbers may carry Indian commas (1,00,000)."""
    t = text.strip()
    m = re.match(r"^(.*\S)\s+([*/+\-])\s+([\d.,]+)$", t)
    if m:
        return ("calc", _operand(m.group(1), names), m.group(2), float(m.group(3).replace(",", "")))
    num = t.replace(",", "")
    try:
        return ("num", float(num))
    except ValueError:
        pass
    field = names.get(_norm(t))
    if not field:
        raise ValueError(f"Unknown field: {t}")
    return ("field", field)


def parse(expr, names):
    """'A > 20 AND B <= C' -> [(lhs, op, rhs)], each side ('field', f) or ('num', v)."""
    if re.search(r"\sOR\s", expr or "", flags=re.I):
        raise ValueError("Only AND between conditions is supported")
    clauses = []
    for part in re.split(r"\s+AND\s+", (expr or "").strip(), flags=re.I):
        if not part.strip():
            continue
        for op in OPS:
            # the first operator that splits the clause outside a field name ('Return Over (%) 1 Year > 15')
            m = re.match(rf"^(.*?)\s*{re.escape(op)}\s*(.*)$", part)
            if m and m.group(1).strip() and m.group(2).strip():
                clauses.append((_operand(m.group(1), names), op, _operand(m.group(2), names)))
                break
        else:
            raise ValueError(f"Can't read the condition: {part.strip()}")
    if not clauses:
        raise ValueError("Empty screen")
    return clauses


def _value(side, row):
    if side[0] == "calc":
        _, base, op, k = side
        x = _value(base, row)
        if x is None:
            return None
        return {"*": x * k, "/": x / k if k else None, "+": x + k, "-": x - k}[op]
    kind, v = side
    if kind == "num":
        return v
    x = row.get(v)
    if not isinstance(x, (int, float)) or (x == 0 and v in ZERO_MEANS_NONE):
        return None
    return x / SCALE.get(v, 1)


def matches(row, clauses):
    for lhs, op, rhs in clauses:
        a, b = _value(lhs, row), _value(rhs, row)
        if a is None or b is None:
            return False
        ok = {">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b, "=": abs(a - b) < 0.5, "!=": abs(a - b) >= 0.5}[op]
        if not ok:
            return False
    return True


# ---------- universe ----------
_warming = threading.Lock()


DISK = Path.home() / ".orazio" / "cache"
STALE_OK = 3 * 86400   # when MarketLens refuses (it rate-limits by IP), screens run on the last copy up to 3 days old


def disk_load(name, max_age):
    """(saved_at, value) from ~/.orazio/cache/<name>.json if younger than max_age seconds, else (None, None)."""
    try:
        d = json.loads((DISK / f"{name}.json").read_text(encoding="utf-8"))
        return (d["at"], d["value"]) if time.time() - d["at"] < max_age else (None, None)
    except (OSError, ValueError, KeyError, TypeError):
        return None, None


def disk_save(name, value):
    try:
        DISK.mkdir(parents=True, exist_ok=True)
        tmp = DISK / f"{name}.tmp"
        tmp.write_text(json.dumps({"at": time.time(), "value": value}), encoding="utf-8")
        os.replace(tmp, DISK / f"{name}.json")
    except OSError:
        log.warning("couldn't save %s to disk", name)


def universe():
    """{ticker: full MarketLens record} for every stock Orazio can screen. ~15 s to build, then cached 30 min, on disk
    too, so a restart (or a test run) doesn't rebuild it: ~1,100 requests each time is how MarketLens blocks an IP."""
    def build():
        at, saved = disk_load("ml-universe", TTL)
        if saved:
            return saved
        try:
            out = fresh()
        except _Empty:
            at, saved = disk_load("ml-universe", STALE_OK)
            if saved:
                log.warning("MarketLens refused; screening on the copy from %s", time.ctime(at))
                return saved
            raise
        disk_save("ml-universe", out)
        return out

    def fresh():
        from .fundamentals import industries   # local: fundamentals imports this package's siblings
        out = {}
        for sec in marketlens._get("/api/sector-names") or []:
            d = marketlens._get(f"/api/sectors/{quote(sec)}/stocks?sortBy=marketCap&sortOrder=desc")
            for r in (d.get("stocks", []) if isinstance(d, dict) else d or []):
                if isinstance(r, dict) and r.get("ticker"):
                    out[r["ticker"]] = r
        missing = [t for t in industries() if t not in out]
        with ThreadPoolExecutor(max_workers=8) as pool:
            for t, r in zip(missing, pool.map(marketlens.stock, missing)):
                if r:
                    out[t] = r
        if not out:
            raise _Empty
        return out
    try:
        return cached(("ml-universe",), TTL, build)
    except _Empty:
        return {}


class _Empty(Exception):
    pass


def warm():
    """Builds the universe in the background at startup, so the first screen answers at once."""
    if _warming.acquire(blocking=False):
        def run():
            try:
                universe()
            except Exception:   # noqa: BLE001
                log.exception("screen universe warm-up failed")
            finally:
                _warming.release()
        threading.Thread(target=run, daemon=True, name="screen-warm").start()


def _row(r):
    cr = lambda v: round(v / 1e7) if isinstance(v, (int, float)) else None
    return {"symbol": r["ticker"], "chartSymbol": f"{r['ticker']}.NS", "name": r.get("name"), "sector": r.get("sector"),
            "price": r.get("lastTradedPrice"), "change": r.get("pchange"), "marketCapCr": cr(r.get("marketCap")),
            "pe": r.get("peRatio") or None, "pb": r.get("pbRatio") or None, "roce": r.get("roce") or None,
            "divYield": r.get("divYield") or None, "ret1y": r.get("oneYearReturn"), "promoter": r.get("promoterHolding") or None}


def run(expr):
    """Evaluates a filter expression over the universe; rows biggest first."""
    clauses = parse(expr, gallery())
    uni = universe()
    if not uni:
        return {"available": False, "reason": "NSE MarketLens isn't answering right now."}
    hits = [r for r in uni.values() if matches(r, clauses)]
    hits.sort(key=lambda r: -(r.get("marketCap") or 0))
    return {"available": True, "query": expr, "count": len(hits), "universe": len(uni), "rows": [_row(r) for r in hits[:SHOW]]}


def ask(question):
    """Plain English (or an expression typed directly) -> screen results, with how the question was read."""
    q = (question or "").strip()
    if not q:
        raise ValueError("Ask for something, like: debt free companies with ROCE above 20")
    names = gallery()
    try:                                  # already an expression ("Price to Earning (P/E) < 15 AND ...")
        parse(q, names)
        built = {"query": q, "read_as": ["Run as typed."], "suggestions": []}
    except ValueError:
        built = marketlens.build_query(q)
        if not built or not built.get("query"):
            return {"available": False, "reason": "NSE's query builder couldn't read that. Try naming a ratio: P/E, ROCE, dividend yield, promoter holding."}
    try:
        out = run(built["query"])
    except ValueError as e:            # the builder produced something this evaluator can't read
        out = {"available": False, "query": built["query"], "reason": f"Can't run this screen here: {e}."}
    return {**out, "question": q, "readAs": built.get("read_as") or [], "suggestions": built.get("suggestions") or []}


def presets():
    """MarketLens's ready-made screens: [{id, name, description, category, query}]."""
    d = marketlens._get("/api/screeners") or {}
    return [{k: s.get(k) for k in ("id", "name", "description", "category", "query")} for s in d.get("screeners", [])]
