"""Deep search: plain-English stock screens, read by a deterministic grammar, e.g.
  "indian IT companies which have beat earnings, positive growth this year with promoter buying"
  "pharma or chemicals, ROCE 20+, debt free, not small caps, top 10 by 1y return"

How it reads (the Bloomberg approach: a grammar-based semantic parser, not free-form generation):
  1. normalise   unicode ops, Indian number commas, "52-week high", "200 DMA", "15-25"
  2. tokenise    words; misspellings repaired against the vocabulary (difflib) and reported
  3. lexicon     longest phrase first: idioms, fields, ops, qualities, sectors, negations, windows, sort words
  4. grammar     FIELD OP NUM [and NUM] · QUAL FIELD · NUM+ FIELD · OP FIELD (price implied) · NEG X · X or Y
  5. clauses     a small typed AST; every clause carries the words it came from, so the UI shows the reading
Words the grammar can't place come back as `unread`; deep_llm.py may then ask a local or CLI model for the same AST
(validated by `valid()` here), and only if none is configured does MarketLens's own builder get a try.
"Beat earnings" means beat the same quarter last year: public data carries no analyst estimates, and the UI says so.
Run the self-check: python -m pytest tests/test_deep.py
"""
import difflib
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from . import insider, marketlens, screen

QUARTERLY_CAP = 300   # stocks whose quarterly results get fetched (largest first); cached 30 min after

# ---------- vocabulary ----------
# id: (label, source, good direction, synonyms). source: record key, ("calc", fn) or ("q", metric, basis)
FIELDS = {
    "pe": ("P/E", "peRatio", "lo", ["pe", "p/e", "pe ratio", "p/e ratio", "price to earnings", "price earnings", "earnings multiple", "pe multiple"]),
    "pb": ("P/B", "pbRatio", "lo", ["pb", "p/b", "price to book", "pb ratio", "book multiple"]),
    "roce": ("ROCE", "roce", "hi", ["roce", "return on capital employed", "return on capital"]),
    "roe": ("ROE", ("calc", "roe"), "hi", ["roe", "return on equity"]),
    "roa": ("ROA", "roa", "hi", ["roa", "return on assets"]),
    "de": ("Debt to equity", "debtToEquity", "lo", ["debt to equity", "d/e", "de ratio", "debt equity", "debt", "leverage", "gearing"]),
    "divy": ("Dividend yield", "divYield", "hi", ["dividend yield", "div yield", "yield", "dividend"]),
    "mcap": ("Market cap ₹ Cr", ("calc", "mcap"), "hi", ["market cap", "mcap", "m cap", "market capitalisation", "market capitalization", "marketcap"]),
    "price": ("Price", "lastTradedPrice", None, ["price", "share price", "stock price", "ltp", "cmp", "trading"]),
    "promoter": ("Promoter holding", "promoterHolding", "hi", ["promoter holding", "promoter stake", "promoter shareholding", "promoters holding", "promoter"]),
    "npm": ("Net margin", "netMargin", "hi", ["net margin", "net profit margin", "profit margin", "pat margin", "margin", "margins"]),
    "ebitdam": ("EBITDA margin", "ebitdaMargin", "hi", ["ebitda margin", "operating margin", "opm"]),
    "ret1w": ("1W return", "oneWeekReturn", "hi", ["1w return", "1 week return", "weekly return"]),
    "ret1m": ("1M return", "oneMonthReturn", "hi", ["1m return", "1 month return", "monthly return"]),
    "ret3m": ("3M return", "threeMonthReturn", "hi", ["3m return", "3 month return"]),
    "ret6m": ("6M return", "sixMonthReturn", "hi", ["6m return", "6 month return", "six month return"]),
    "ret1y": ("1Y return", "oneYearReturn", "hi", ["1y return", "1 year return", "one year return", "annual return", "12 month return", "return", "returns", "performance"]),
    "retytd": ("YTD return", "ytdReturn", "hi", ["ytd return", "ytd", "year to date return"]),
    "ret3y": ("3Y return", "threeYearReturn", "hi", ["3y return", "3 year return"]),
    "ret5y": ("5Y return", "fiveYearReturn", "hi", ["5y return", "5 year return"]),
    "day": ("Day change", "pchange", "hi", ["day change", "change today", "daily change", "todays change"]),
    "delivery": ("Delivery %", "deliveryPercentage", "hi", ["delivery", "delivery percentage", "delivery %"]),
    "vol": ("Volatility", "annVolatility", "lo", ["volatility", "annual volatility", "vol"]),
    "cr": ("Current ratio", "currentRatio", "hi", ["current ratio"]),
    "icr": ("Interest cover", "interestCover", "hi", ["interest cover", "interest coverage"]),
    "payout": ("Dividend payout", "dividendPayoutRatio", None, ["payout", "dividend payout", "payout ratio"]),
    "volume": ("Volume, lakh shares", ("calc", "volume"), "hi", ["volume", "traded volume"]),
    "netprofit": ("Net profit", "netProfit", "hi", ["net profit", "pat", "profit", "earnings"]),
    "dma20": ("20-day average", "dma20", None, ["dma20"]), "dma50": ("50-day average", "dma50", None, ["dma50"]),
    "dma200": ("200-day average", "dma200", None, ["dma200"]),
    "w52high": ("52-week high", "week52High", None, ["w52high"]), "w52low": ("52-week low", "week52Low", None, ["w52low"]),
    "offhigh": ("% from 52-week high", ("calc", "offhigh"), None, ["off high", "off highs", "from w52high", "below w52high"]),
    "revyoy": ("Revenue YoY %", ("q", "revenue", 5), "hi", ["revenue growth", "sales growth", "topline growth", "top line growth", "revenue yoy", "sales yoy", "growth", "revenue"]),
    "profyoy": ("Profit YoY %", ("q", "netIncome", 5), "hi", ["profit growth", "earnings growth", "pat growth", "net profit growth", "profit yoy", "bottom line growth", "bottomline growth"]),
    "epsyoy": ("EPS YoY %", ("q", "eps", 5), "hi", ["eps growth", "eps yoy"]),
    "revqoq": ("Revenue QoQ %", ("q", "revenue", 2), "hi", ["revenue qoq", "sales qoq", "sequential revenue growth", "sequential growth", "qoq growth", "qoq revenue growth"]),
    "profqoq": ("Profit QoQ %", ("q", "netIncome", 2), "hi", ["profit qoq", "qoq profit growth", "sequential profit growth"]),
}
SECTORS = {   # typed word -> substrings of MarketLens's sector / subSector
    "it": ("it -", "information technology", "software"), "tech": ("it -", "information technology", "software"),
    "technology": ("it -", "information technology", "software"), "software": ("software",),
    "bank": ("bank",), "banks": ("bank",), "banking": ("bank",), "financials": ("bank", "financ", "insurance", "capital markets"),
    "nbfc": ("financ",), "finance": ("financ",), "insurance": ("insurance",), "pharma": ("pharma",), "pharmaceutical": ("pharma",),
    "healthcare": ("health", "pharma", "hospital"), "hospital": ("hospital", "health"), "auto": ("auto",), "autos": ("auto",),
    "automobile": ("auto",), "fmcg": ("fmcg", "food", "personal care", "household", "beverage"), "consumer": ("fmcg", "consumer", "food"),
    "metal": ("metal", "steel", "mining", "minerals"), "metals": ("metal", "steel", "mining", "minerals"), "steel": ("steel",),
    "mining": ("mining", "minerals"), "power": ("power",), "energy": ("power", "oil", "gas", "energy"), "oil": ("oil",),
    "gas": ("gas",), "realty": ("realty",), "cement": ("cement",), "chemical": ("chemical",), "chemicals": ("chemical",),
    "defence": ("defense", "defence"), "defense": ("defense", "defence"), "telecom": ("telecom",), "textile": ("textile",),
    "textiles": ("textile",), "infra": ("construction", "infrastructure"), "construction": ("construction",),
    "capital goods": ("capital goods", "industrial", "electrical equipment"), "media": ("media", "entertainment"),
    "paper": ("paper",), "beverages": ("beverage",), "psu": None,   # None: no field carries ownership; reported unread
}
SECTORS = {k: v for k, v in SECTORS.items() if v}
SECTOR_LABEL = {"it": "IT", "tech": "IT", "technology": "IT", "fmcg": "FMCG", "nbfc": "NBFC"}

OPS = {">": ["above", "over", "more than", "greater than", "higher than", "bigger than", "larger than", "exceeding", "exceeds",
             "north of", "upwards of", ">", "gt", "beyond"],
       ">=": ["at least", "atleast", "min", "minimum", ">=", "not less than", "no less than"],
       "<": ["below", "under", "less than", "lower than", "smaller than", "beneath", "<", "lt", "sub", "within", "south of"],
       "<=": ["at most", "atmost", "max", "maximum", "<=", "not more than", "no more than", "up to", "upto"],
       "between": ["between", "from"], "=": ["=", "equal to", "equals", "around", "about", "of", "is"]}
QUALS = {"hi": ["high", "higher", "strong", "big", "large", "huge", "robust", "solid", "healthy", "good", "great", "decent", "excellent", "superior", "rich"],
         "lo": ["low", "lower", "small", "weak", "poor", "thin", "little", "minimal", "tiny"],
         "pos": ["positive", "rising", "growing", "increasing", "improving", "up", "green", "expanding", "accelerating"],
         "neg": ["negative", "falling", "declining", "decreasing", "shrinking", "down", "red", "contracting"],
         "dd": ["double digit", "double-digit", "two digit"], "td": ["triple digit", "triple-digit"]}
NEGS = ["not", "no", "non", "excluding", "exclude", "except", "ex", "without", "other than", "but not", "avoid", "skip"]
CONJ_OR = ["or", "either"]
SORTS = {"desc": ["top", "best", "highest", "biggest", "largest", "most"], "asc": ["lowest", "cheapest", "smallest", "least", "bottom", "worst"]}
NOISE = set("indian india nse bse listed companies company stocks stock shares share scrips names which that who whose have has had "
            "having with and also the a an in on of for show me find list give get all are is be their its them those these "
            "plus while where by sorted sort order ordered rank ranked please like want looking look screen filter i some any "
            "currently now trading at to as been being whats what more ratio than".split())
# "with" etc. are glue: dropping them never changes the meaning of what's left


def _idioms():
    """phrase -> list of clauses (or a callable(number) for idioms taking a number). Matched before anything else."""
    I = {}

    def add(phrases, *clauses):
        for p in phrases:
            I[p] = list(clauses)
    cmp_ = lambda f, op, v, note=None: {"t": "cmp", "field": f, "op": op, "v": v, **({"note": note} if note else {})}
    rel = lambda f, op, other, k=1.0: {"t": "rel", "field": f, "op": op, "other": other, "k": k}
    beat = "no analyst estimates on public data, so 'beat' means beat the same quarter last year"
    add(["beat earnings", "beat estimates", "beat expectations", "beat results", "earnings beat", "results beat", "earnings surprise",
         "positive surprise", "beat on earnings", "beats earnings", "beating earnings", "beat street", "beat consensus"], cmp_("profyoy", ">", 0, beat))
    add(["missed earnings", "missed estimates", "earnings miss", "results miss", "miss earnings", "negative surprise"], cmp_("profyoy", "<", 0, beat))
    add(["debt free", "debtfree", "zero debt", "no debt", "debtless", "without debt", "nil debt"], cmp_("de", "<=", 0.05))
    add(["loss making", "lossmaking", "in losses", "in loss", "loss", "losses", "unprofitable"], cmp_("netprofit", "<", 0))
    add(["profitable", "profit making", "in profit", "making money"], cmp_("netprofit", ">", 0))
    add(["near w52high", "close to w52high", "at w52high", "near highs", "near their highs", "at highs", "new highs", "new w52high", "w52high"],
        rel("price", ">=", "w52high", 0.95))
    add(["breakout", "breakouts", "breaking out"], rel("price", ">=", "w52high", 0.98))
    add(["near w52low", "close to w52low", "at w52low", "near lows", "new lows", "w52low"], rel("price", "<=", "w52low", 1.05))
    add(["golden cross"], rel("dma50", ">", "dma200"))
    add(["death cross"], rel("dma50", "<", "dma200"))
    add(["uptrend", "up trend", "trending up", "in an uptrend"], rel("price", ">", "dma50"), rel("dma50", ">", "dma200"))
    add(["downtrend", "down trend", "trending down", "in a downtrend"], rel("price", "<", "dma50"), rel("dma50", "<", "dma200"))
    add(["turnaround", "turnarounds", "turned profitable", "back to profit"], {"t": "turnaround"})
    add(["large cap", "large caps", "largecap", "largecaps", "bluechip", "bluechips", "blue chip", "blue chips"], {"t": "size", "cls": "large"})
    add(["mid cap", "mid caps", "midcap", "midcaps"], {"t": "size", "cls": "mid"})
    add(["small cap", "small caps", "smallcap", "smallcaps", "micro cap", "microcap", "microcaps"], {"t": "size", "cls": "small"})
    add(["penny stock", "penny stocks", "penny"], cmp_("price", "<", 20, "'penny' read as a price under ₹20"))
    add(["dividend paying", "dividend payers", "pays dividend", "pays dividends", "dividend payer"], cmp_("divy", ">", 0))
    add(["undervalued", "cheap", "value stocks", "value", "inexpensive", "bargain", "bargains"], {"t": "rank", "field": "pe", "side": "bottom", "pct": 30})
    add(["overvalued", "expensive", "pricey", "rich valuation"], {"t": "rank", "field": "pe", "side": "top", "pct": 30})
    add(["momentum", "momentum stocks", "strong momentum", "high momentum"], {"t": "rank", "field": "ret6m", "side": "top", "pct": 20})
    add(["quality", "quality stocks", "high quality", "compounders", "compounder"], cmp_("roce", ">=", 15), cmp_("de", "<=", 0.5))
    add(["growth stocks", "high growth", "fast growing", "hyper growth"], cmp_("revyoy", ">=", 20))
    add(["growing", "positive growth", "growth positive"], cmp_("revyoy", ">", 0))
    add(["gainers", "top gainers", "gaining today", "up today"], cmp_("day", ">", 0), {"t": "sort", "field": "day", "desc": True})
    add(["losers", "top losers", "falling today", "down today"], cmp_("day", "<", 0), {"t": "sort", "field": "day", "desc": False})
    return I


IDIOMS = _idioms()
INSIDER_WHO = {"promoter": ["promoter", "promoters", "promoter group"], "insider": ["insider", "insiders", "management", "directors", "director", "kmp"]}
INSIDER_SIDE = {"buy": ["buying", "buy", "buys", "bought", "purchase", "purchases", "purchasing", "accumulating", "accumulation",
                        "adding", "added", "increasing stake", "raising stake", "stake increase", "stake hike", "acquisition", "acquiring"],
                "sell": ["selling", "sell", "sells", "sold", "offloading", "dumping", "reducing stake", "cutting stake", "stake sale",
                         "stake cut", "exits", "exiting", "trimming"]}
UNITS = {"%": 1, "pct": 1, "percent": 1, "per cent": 1, "x": 1, "times": 1, "k": 1e3, "thousand": 1e3, "cr": 1, "crore": 1, "crores": 1,
         "lakh crore": 1e5, "lac crore": 1e5, "lakh": 0.01, "lac": 0.01, "lakhs": 0.01, "bn": 100, "billion": 100, "b": 100,
         "mn": 0.1, "million": 0.1, "m": 0.1, "trillion": 1e5, "tn": 1e5}
STRIP = {"the", "their", "its", "a", "an", "his", "her", "our", "my"}   # articles: dropped before any matching
CRORE_UNITS = {"cr", "crore", "crores", "lakh crore", "lac crore", "lakh", "lac", "lakhs", "bn", "billion", "b", "mn", "million", "m", "trillion", "tn"}
TIME_UNITS = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30, "months": 30, "quarter": 91, "quarters": 91, "year": 365, "years": 365, "yr": 365, "yrs": 365}


def _lexicon():
    """(words tuple) -> token. Longest phrases win, so 'debt to equity' beats 'debt', 'no debt' beats 'no'."""
    L = {}

    def put(phrase, tok):
        key = tuple(w for w in phrase.split() if w not in STRIP)
        if key:
            L.setdefault(key, tok)
    for p, cl in IDIOMS.items():
        put(p, {"k": "idiom", "clauses": cl})
    for fid, (_, _, _, syns) in FIELDS.items():
        for s in syns:
            put(s, {"k": "field", "id": fid})
            if s.endswith("return"):
                put(s + "s", {"k": "field", "id": fid})
    for op, ws in OPS.items():
        for w in ws:
            put(w, {"k": "op", "op": op})
    for q, ws in QUALS.items():
        for w in ws:
            put(w, {"k": "qual", "q": q})
    for s in SECTORS:
        put(s, {"k": "sector", "word": s})
    for w in NEGS:
        put(w, {"k": "neg"})
    for w in CONJ_OR:
        put(w, {"k": "or"})
    for d, ws in SORTS.items():
        for w in ws:
            put(w, {"k": "sort", "desc": d == "desc"})
    for who, ws in INSIDER_WHO.items():
        for w in ws:
            put(w, {"k": "who", "who": who})
    for side, ws in INSIDER_SIDE.items():
        for w in ws:
            put(w, {"k": "side", "side": side})
    for u in UNITS:
        put(u, {"k": "unit", "u": u})
    for w in ("this year", "this calendar year", "so far this year", "ytd"):
        put(w, {"k": "time", "days": None, "ytd": True})
    for w in ("recently", "recent", "lately", "of late"):
        put(w, {"k": "time", "days": 90})
    for w in ("last", "past", "previous", "in the last", "in the past", "over the last", "over the past", "since"):
        put(w, {"k": "timeword"})
    for u in TIME_UNITS:
        put(u, {"k": "tunit", "days": TIME_UNITS[u]})
    put("and", {"k": "and"})
    put(",", {"k": "and"})
    put("to", {"k": "to"})
    return L


LEX = _lexicon()
MAXLEN = max(len(k) for k in LEX)
VOCAB = sorted({w for k in LEX for w in k if w.isalpha() and len(w) >= 4} | NOISE)


# ---------- reading ----------
def normalise(text):
    t = (text or "").lower()
    t = t.replace("≥", ">=").replace("≤", "<=").replace("–", "-").replace("—", "-").replace("’", "'").replace("₹", " ")
    t = re.sub(r"\brs\.?\s*(?=\d)", " ", t)
    t = re.sub(r"(?<=\d),(?=\d)", "", t)                                       # 1,00,000 -> 100000
    t = re.sub(r"\b52\s*-?\s*(?:week|wk|w)s?\s*-?\s*(high|low)s?\b", r"w52\1", t)
    t = re.sub(r"\ball[\s-]*time[\s-]*high\b", "w52high", t)                    # ponytail: ATH read as 52-week high
    t = re.sub(r"\b(20|50|200)\s*-?\s*(?:day\s*)?(?:dma|sma|ema|ma|moving average|day average|day moving average)\b", r"dma\1", t)
    t = re.sub(r"\b(?:dma|sma|ema)\s*-?\s*(20|50|200)\b", r"dma\1", t)
    t = re.sub(r"(\d)\s*-\s*(\d)", r"\1 to \2", t)                             # 15-25 -> 15 to 25
    t = re.sub(r"(\d)\s*\+(?!\d)", r"\1 plus ", t)                             # 20+ -> 20 plus
    t = re.sub(r"(\d)(%|x|k|cr|bn|mn|l)\b", r"\1 \2", t)                       # 20% -> 20 %
    t = re.sub(r"(>=|<=|>|<|=)", r" \1 ", t)
    t = re.sub(r"(\d)\s*yr?s?\b", r"\1 y", t)
    t = re.sub(r"\b(\d+)\s*(y|m|w)\s+(?:return|returns)\b", r"\1\2 return", t)  # 1 y return -> 1y return
    t = re.sub(r"\b(?:one|1)\s*-?\s*year\b", "1 year", t)
    return t


def _words(t):
    return re.findall(r"\d+\.\d+|[a-z0-9]+(?:/[a-z]+)?|>=|<=|[<>=,%]", t)


def _isnum(w):
    return re.fullmatch(r"\d+(?:\.\d+)?", w) is not None


def repair(words):
    """Misspelt words -> nearest vocabulary word, only when it's close (ratio 0.84+). Returns (words, [(was, now)])."""
    fixed, notes = [], []
    for w in words:
        if w.isalpha() and len(w) >= 4 and w not in VOCAB and (w,) not in LEX:
            near = difflib.get_close_matches(w, VOCAB, n=1, cutoff=0.84)
            if near:
                notes.append((w, near[0]))
                w = near[0]
        fixed.append(w)
    return fixed, notes


def tokens(words):
    """Greedy longest match against the lexicon; numbers stay numbers; anything else is {'k': 'word'}."""
    out, i = [], 0
    while i < len(words):
        w = words[i]
        for n in range(min(MAXLEN, len(words) - i), 0, -1):
            tok = LEX.get(tuple(words[i:i + n]))
            if tok and (n > 1 or not _isnum(w)):        # "1 year return" is a field; a bare "1" is a number
                out.append({**tok, "i": i, "j": i + n})
                i += n
                break
        else:
            out.append({"k": "num", "v": float(w), "i": i, "j": i + 1} if _isnum(w) else {"k": "word", "w": w, "i": i, "j": i + 1})
            i += 1
    return _merge_units(out)


def _merge_units(toks):
    """A number keeps its raw value and its unit; _unit() converts per field (₹ crore for market cap, lakh for volume)."""
    out = []
    for t in toks:
        if t["k"] == "unit" and out and out[-1]["k"] == "num" and "u" not in out[-1]:
            out[-1].update(u=t["u"], j=t["j"])
            continue
        if t["k"] == "word" and t["w"] == "plus" and out and out[-1]["k"] == "num":
            out[-1]["plus"] = True
            out[-1]["j"] = t["j"]
            continue
        out.append(t)
    return out


def _span(words, toks):
    """The words a clause came from, as typed (bar normalisation): w52high reads back as '52-week high'."""
    if not toks:
        return ""
    s = " ".join(words[min(t["i"] for t in toks):max(t["j"] for t in toks)])
    s = re.sub(r"\bw52(high|low)\b", r"52-week \1", s)
    return re.sub(r"\bdma(\d+)\b", r"\1 DMA", s)


def _days_since_jan1(today=None):
    today = today or date.today()
    return (today - date(today.year, 1, 1)).days or 1


def parse(question, today=None):
    """Sentence -> {clauses, unread, repaired}. Pure: no network."""
    words, repaired = repair([w for w in _words(normalise(question)) if w not in STRIP])
    toks = tokens(words)
    clauses, used = [], set()
    n = len(toks)

    def at(k, kind):
        return 0 <= k < n and toks[k]["k"] == kind and k not in used

    def emit(cl, span, neg=False):
        for k in span:
            used.add(k)
        phrase = _span(words, [toks[k] for k in span])
        for c in cl:
            clauses.append({**c, "phrase": phrase, **({"neg": True} if neg else {})})

    def window(k):
        """A time window at or after token k: ('last 6 months', 'this year', 'recently') -> (days, span)."""
        if at(k, "time"):
            return (_days_since_jan1(today) if toks[k].get("ytd") else toks[k]["days"]), [k]
        if at(k, "timeword"):
            if at(k + 1, "num") and at(k + 2, "tunit"):
                return int(toks[k + 1]["v"] * toks[k + 2]["days"]), [k, k + 1, k + 2]
            if at(k + 1, "tunit"):
                return toks[k + 1]["days"], [k, k + 1]
        return None, []

    def number_clause(fid, k):
        """FIELD at k-1; read OP NUM [and|to NUM] | NUM [to NUM] | NUM plus starting at k. -> (clauses, span) or None."""
        span = []
        op = None
        if at(k, "op"):
            op, span = toks[k]["op"], [k]
            k += 1
        elif at(k, "qual") and toks[k]["q"] in ("dd", "td"):
            return [{"t": "cmp", "field": fid, "op": ">=", "v": 10 if toks[k]["q"] == "dd" else 100}], [k]
        if not at(k, "num"):
            if op and op not in ("between", "=") and at(k, "field"):            # price above dma200
                return [{"t": "rel", "field": fid, "op": op, "other": toks[k]["id"], "k": 1.0}], span + [k]
            return None
        a = toks[k]
        span.append(k)
        if (at(k + 1, "and") or at(k + 1, "to")) and at(k + 2, "num") and op in (None, "between"):
            return [{"t": "cmp", "field": fid, "op": "between", "v": _unit(fid, a), "v2": _unit(fid, toks[k + 2])}], span + [k + 1, k + 2]
        if op in (None, "=", "between"):
            good = FIELDS[fid][2]
            if a.get("plus"):
                op = ">="
            elif op == "=" and fid in ("price", "mcap"):
                return [{"t": "cmp", "field": fid, "op": "between", "v": _unit(fid, a) * 0.9, "v2": _unit(fid, a) * 1.1}], span
            else:
                op = "<=" if good == "lo" else ">="
                if not a.get("plus"):
                    return [{"t": "cmp", "field": fid, "op": op, "v": _unit(fid, a), "assumed": True}], span
        return [{"t": "cmp", "field": fid, "op": op, "v": _unit(fid, a)}], span

    # pass 1: insider phrases (who … side [window]) and idioms
    for k in range(n):
        if at(k, "field") and toks[k]["id"] == "promoter" and words[toks[k]["i"]] == "promoter" and toks[k]["j"] - toks[k]["i"] == 1:
            toks[k] = {**toks[k], "k": "who", "who": "promoter", "maybe_field": True}   # "promoter buying" vs "promoter 70"
        if at(k, "who") and toks[k]["who"]:
            side_k = next((m for m in range(k + 1, min(k + 4, n)) if at(m, "side")), None)
            pre = next((m for m in range(max(0, k - 2), k) if at(m, "side")), None)   # "buying by promoters"
            s = side_k if side_k is not None else pre
            if s is not None:
                span = list(range(min(k, s), max(k, s) + 1))
                m = max(span) + 1
                if m < n and words[toks[m]["i"]] in ("shares", "stake", "stock") and toks[m]["k"] == "word":
                    m += 1                                   # "promoters bought shares recently"
                days, wspan = window(m)                      # only a window right after the phrase binds to it
                emit([{"t": "insider", "who": toks[k]["who"], "side": toks[s]["side"], "_at": max(span), **({"days": days} if days else {})}], span + wspan)
            elif toks[k].get("maybe_field"):
                toks[k] = {"k": "field", "id": "promoter", "i": toks[k]["i"], "j": toks[k]["j"]}
    for k in range(n):
        if at(k, "idiom"):
            span = [k]
            neg = at(k - 1, "neg")
            if neg:
                span.insert(0, k - 1)
            emit(toks[k]["clauses"], span, neg)

    # pass 2: sectors (with OR / AND lists and negation)
    k = 0
    while k < n:
        if at(k, "sector"):
            span, words_ = [k], [toks[k]["word"]]
            m = k + 1
            while (at(m, "or") or at(m, "and")) and at(m + 1, "sector"):
                span += [m, m + 1]
                words_.append(toks[m + 1]["word"])
                m += 2
            neg = at(k - 1, "neg")
            if neg:
                span.insert(0, k - 1)
            emit([{"t": "sector", "words": words_}], span, neg)
            k = m
        else:
            k += 1

    # pass 3: sorting and limits: "top 10 by roce", "highest roe", "10 cheapest", "top 20"
    for k in range(n):
        if at(k, "sort"):
            desc, span, limit = toks[k]["desc"], [k], None
            if at(k + 1, "num"):
                limit, span = int(toks[k + 1]["v"]), span + [k + 1]
            elif at(k - 1, "num"):
                limit, span = int(toks[k - 1]["v"]), [k - 1] + span
            m = max(span) + 1
            if at(m, "word") and toks[m]["w"] in ("by", "on", "in"):
                span.append(m)
                m += 1
            if at(m, "field"):
                fid = toks[m]["id"]
                span.append(m)
                # "highest" on a low-is-good field still means the biggest number; "best"/"worst" follow the field
                w = words[toks[k]["i"]]
                if w in ("best", "worst") and FIELDS[fid][2] == "lo":
                    desc = not desc
                emit([{"t": "sort", "field": fid, "desc": desc, **({"limit": limit} if limit else {})}], span)
            elif w_ := words[toks[k]["i"]]:
                implied = {"cheapest": ("pe", False), "biggest": ("mcap", True), "largest": ("mcap", True), "smallest": ("mcap", False)}.get(w_)
                if implied:
                    emit([{"t": "sort", "field": implied[0], "desc": implied[1], **({"limit": limit} if limit else {})}], span)
                elif limit:
                    emit([{"t": "limit", "limit": limit}], span)

    # pass 4: "up 20% this year", "down 30% from w52high", "gained 50% in 6 months"
    for k in range(n):
        if k in used or not (at(k, "qual") or at(k, "word")):
            continue
        w = words[toks[k]["i"]]
        up = w in ("up", "gained", "rallied", "rose", "risen", "jumped", "surged") or (toks[k]["k"] == "qual" and toks[k]["q"] == "pos")
        down = w in ("down", "fell", "lost", "dropped", "crashed", "corrected", "slumped") or (toks[k]["k"] == "qual" and toks[k]["q"] == "neg")
        if (up or down) and at(k + 1, "num"):
            v = toks[k + 1]["v"]
            span = [k, k + 1]
            m = k + 2
            if m < n and m not in used and words[toks[m]["i"]] in ("from", "off") and toks[m]["j"] - toks[m]["i"] == 1:
                m += 1
            if at(m, "field") and toks[m]["id"] in ("w52high", "offhigh"):
                emit([{"t": "cmp", "field": "offhigh", "op": "<=", "v": -v}], span + list(range(k + 2, m + 1)))
                continue
            if at(m, "word") and toks[m]["w"] == "in":
                m += 1
            days, wspan = window(m)
            if not days and at(m, "num") and at(m + 1, "tunit"):
                days, wspan = int(toks[m]["v"] * toks[m + 1]["days"]), [m, m + 1]
            fid = _return_field(days, today)
            emit([{"t": "cmp", "field": fid, "op": ">=" if up else "<=", "v": v if up else -v}], span + list(range(k + 2, m)) + wspan)

    # pass 5: field comparisons and qualities
    for k in range(n):
        if k in used:
            continue
        t = toks[k]
        if t["k"] == "field":
            fid = t["id"]
            neg = at(k - 1, "neg")
            got = number_clause(fid, k + 1)
            if got:
                cl, span = got
                pre = [k - 1] if neg else []
                emit(cl, pre + [k] + span, neg)
                continue
            if at(k - 1, "qual") or (at(k - 2, "qual") and at(k - 1, "neg")):
                continue                                   # handled from the quality's side below
            if at(k + 1, "qual") or (at(k + 1, "word") and toks[k + 1]["w"] in ("is", "are") and at(k + 2, "qual")):
                q = k + 1 if at(k + 1, "qual") else k + 2
                cl = _qual(toks[q]["q"], fid, words[toks[q]["i"]])
                if cl:
                    emit(cl, list(range(k, q + 1)))
                continue
            if at(k - 1, "num"):                              # "20% roce", "20 plus roce"
                a = toks[k - 1]
                op = ">=" if a.get("plus") or FIELDS[fid][2] != "lo" else "<="
                emit([{"t": "cmp", "field": fid, "op": op, "v": _unit(fid, a), **({} if a.get("plus") else {"assumed": True})}], [k - 1, k])
                continue
        elif t["k"] == "qual":
            m = k + 1
            neg = at(k - 1, "neg")
            if at(m, "field"):
                cl = _qual(t["q"], toks[m]["id"], words[t["i"]])
                if cl:
                    emit(cl, ([k - 1] if neg else []) + [k, m], neg)
        elif t["k"] == "op" and at(k + 1, "field") and t["op"] in (">", "<", ">=", "<="):
            fid = toks[k + 1]["id"]
            if fid in ("dma20", "dma50", "dma200", "w52high", "w52low"):   # "above 200 dma": the price is implied
                emit([{"t": "rel", "field": "price", "op": t["op"], "other": fid, "k": 1.0}], [k, k + 1])

    # a window nobody took binds to an insider clause it follows: "insider selling in banks in the last 3 months"
    for k in range(n):
        if k not in used and (at(k, "time") or at(k, "timeword")):
            days, wspan = window(k)
            ins = [c for c in clauses if c["t"] == "insider" and not c.get("days") and c.get("_at", n) < k]
            if days and len(ins) == 1:
                ins[0]["days"] = days
                used.update(wspan)
    for c in clauses:
        c.pop("_at", None)

    # leftovers: noise words are dropped, the rest is reported so it's never silently ignored
    unread = [_span(words, [toks[k]]) for k in range(n) if k not in used and toks[k]["k"] not in ("and", "or", "to", "unit", "tunit")
              and not (toks[k]["k"] == "word" and toks[k]["w"] in NOISE) and words[toks[k]["i"]] not in NOISE
              and toks[k]["k"] not in ("timeword", "time", "neg")]
    return {"clauses": clauses, "unread": unread, "repaired": repaired}


def _qual(q, fid, word):
    good = FIELDS[fid][2]
    if q == "pos":
        return [{"t": "cmp", "field": fid, "op": ">", "v": 0}]
    if q == "neg":
        return [{"t": "cmp", "field": fid, "op": "<", "v": 0}]
    if q in ("dd", "td"):
        return [{"t": "cmp", "field": fid, "op": ">=", "v": 10 if q == "dd" else 100}]
    literal = word in ("high", "higher", "low", "lower", "big", "large", "small", "huge", "tiny", "little", "rich")
    side = q if literal or not good else (good if q == "hi" else ("hi" if good == "lo" else "lo"))
    if fid in ("revyoy", "profyoy", "epsyoy", "revqoq", "profqoq") and side == "hi" and not literal:
        return [{"t": "cmp", "field": fid, "op": ">=", "v": 15}]    # "strong growth": 15%+, stated in the label
    return [{"t": "rank", "field": fid, "side": "top" if side == "hi" else "bottom", "pct": 30}]


def _return_field(days, today=None):
    if days is None:
        return "ret1y"
    if days == _days_since_jan1(today):
        return "retytd"
    return min((7, "ret1w"), (30, "ret1m"), (91, "ret3m"), (182, "ret6m"), (365, "ret1y"), (1095, "ret3y"), (1825, "ret5y"),
               key=lambda p: abs(p[0] - days))[1]


def _unit(fid, num):
    """A typed number in the field's unit. Market cap is in ₹ crore ("10k" = 10,000 cr, "1 lakh crore", "2bn" = 200 cr);
    volume in lakh shares ("10 lakh", "1 crore" = 100 lakh); everything else takes k/thousand and ignores the rest."""
    v, u = num["v"], num.get("u")
    if fid == "mcap" and u:
        return v * UNITS[u]                         # UNITS are crore-relative for money words; k = thousand crore
    if fid == "volume" and u:
        return v * {"lakh": 1, "lac": 1, "lakhs": 1, "cr": 100, "crore": 100, "crores": 100, "k": 0.01, "thousand": 0.01,
                    "mn": 10, "million": 10, "m": 10}.get(u, 1)
    return v * 1e3 if u in ("k", "thousand") else v


# ---------- validation (also guards anything a model returns) ----------
KINDS = {"cmp", "rel", "rank", "sector", "size", "insider", "turnaround", "sort", "limit"}


def valid(c):
    """True if the clause is well-formed. Model output passes through this before it touches data."""
    if not isinstance(c, dict) or c.get("t") not in KINDS:
        return False
    t = c["t"]
    num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and abs(x) < 1e12
    if t == "cmp":
        return c.get("field") in FIELDS and c.get("op") in (">", "<", ">=", "<=", "between") and num(c.get("v")) \
            and (c["op"] != "between" or num(c.get("v2")))
    if t == "rel":
        return c.get("field") in FIELDS and c.get("other") in FIELDS and c.get("op") in (">", "<", ">=", "<=") and num(c.get("k", 1.0))
    if t == "rank":
        return c.get("field") in FIELDS and c.get("side") in ("top", "bottom") and num(c.get("pct")) and 0 < c["pct"] < 100
    if t == "sector":
        return isinstance(c.get("words"), list) and c["words"] and all(w in SECTORS for w in c["words"])
    if t == "size":
        return c.get("cls") in ("large", "mid", "small")
    if t == "insider":
        return c.get("who") in ("promoter", "insider") and c.get("side") in ("buy", "sell") and (c.get("days") is None or (num(c["days"]) and 0 < c["days"] <= 1095))
    if t == "sort":
        return c.get("field") in FIELDS and isinstance(c.get("desc"), bool) and (c.get("limit") is None or (isinstance(c["limit"], int) and 0 < c["limit"] <= 500))
    if t == "limit":
        return isinstance(c.get("limit"), int) and 0 < c["limit"] <= 500
    return True


# ---------- labels ----------
def _fmt(x):
    return f"{x:,.2f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


OPW = {">": "above", ">=": "at least", "<": "below", "<=": "at most"}


def label(c):
    no = "Not " if c.get("neg") else ""
    t = c["t"]
    if t == "cmp":
        name = FIELDS[c["field"]][0]
        pct = "%" if c["field"] in PCT_FIELDS else ""
        rng = f"between {_fmt(c['v'])}{pct} and {_fmt(c['v2'])}{pct}" if c["op"] == "between" else f"{OPW[c['op']]} {_fmt(c['v'])}{pct}"
        s = f"{no}{name} {rng}"
        if c.get("assumed"):
            s += " (read as a floor)" if c["op"] == ">=" else " (read as a ceiling)"
        return s + (f": {c['note']}" if c.get("note") else "")
    if t == "rel":
        k = f"{_fmt(c['k'] * 100)}% of the " if c.get("k", 1) != 1 else "the "
        return f"{no}{FIELDS[c['field']][0]} {OPW[c['op']]} {k}{FIELDS[c['other']][0].lower()}"
    if t == "rank":
        return f"{no}{'High' if c['side'] == 'top' else 'Low'} {FIELDS[c['field']][0]}: {'top' if c['side'] == 'top' else 'bottom'} {c['pct']:g}% of NSE" \
            + (f", {OPW['>=' if c['side'] == 'top' else '<=']} {_fmt(c['cut'])}" if c.get("cut") is not None else "")
    if t == "sector":
        return f"{'Not in' if c.get('neg') else 'Sector'}: {' or '.join(SECTOR_LABEL.get(w, w.title()) for w in c['words'])}"
    if t == "size":
        return f"{no}{c['cls'].title()} cap (SEBI ranks: {'1 to 100' if c['cls'] == 'large' else '101 to 250' if c['cls'] == 'mid' else '251 and below'} by market cap)"
    if t == "insider":
        who = "Promoters" if c["who"] == "promoter" else "Promoters, directors and KMP"
        days = c.get("used_days") or c.get("days")
        return f"{no}{who} net {'bought' if c['side'] == 'buy' else 'sold'} in the open market" + (f", last {days} days" if days else "") \
            + (f" (NSE's latest disclosure: {c['latest']})" if c.get("latest") else "")
    if t == "turnaround":
        return f"{no}Turnaround: a loss in the year-ago quarter, a profit in the latest"
    if t == "sort":
        return f"Sorted by {FIELDS[c['field']][0]}, {'highest' if c['desc'] else 'lowest'} first" + (f", top {c['limit']}" if c.get("limit") else "")
    if t == "limit":
        return f"Top {c['limit']} by market cap"
    return t


PCT_FIELDS = {"roce", "roe", "roa", "divy", "promoter", "npm", "ebitdam", "ret1w", "ret1m", "ret3m", "ret6m", "ret1y", "retytd", "ret3y",
              "ret5y", "day", "delivery", "vol", "payout", "offhigh", "revyoy", "profyoy", "epsyoy", "revqoq", "profqoq"}


# ---------- running ----------
def _yoy(q, key, back):
    if len(q) >= back and isinstance(q[-1].get(key), (int, float)) and isinstance(q[-back].get(key), (int, float)) and q[-back][key] > 0:
        return round((q[-1][key] / q[-back][key] - 1) * 100, 1)
    return None


def value(fid, r, quarters=None):
    src = FIELDS[fid][1]
    if isinstance(src, tuple) and src[0] == "q":
        return _yoy(quarters or [], src[1], src[2])
    if isinstance(src, tuple):
        kind = src[1]
        if kind == "roe":
            np_, eq = r.get("netProfit"), r.get("totalEquity")
            return np_ / eq * 100 if isinstance(np_, (int, float)) and isinstance(eq, (int, float)) and eq > 0 else None
        if kind == "mcap":
            return r["marketCap"] / 1e7 if isinstance(r.get("marketCap"), (int, float)) else None
        if kind == "volume":
            return r["volume"] / 1e5 if isinstance(r.get("volume"), (int, float)) else None
        if kind == "offhigh":
            p, h = r.get("lastTradedPrice"), r.get("week52High")
            return (p / h - 1) * 100 if isinstance(p, (int, float)) and isinstance(h, (int, float)) and h > 0 else None
    x = r.get(src)
    if not isinstance(x, (int, float)) or isinstance(x, bool) or (x == 0 and src in screen.ZERO_MEANS_NONE):
        return None
    return x


def _test(c, r, ctx):
    t = c["t"]
    if t == "cmp":
        x = value(c["field"], r, ctx["q"].get(r["ticker"]))
        if x is None:
            return False
        return {">": x > c["v"], ">=": x >= c["v"], "<": x < c["v"], "<=": x <= c["v"], "between": c["v"] <= x <= c.get("v2", c["v"])}[c["op"]]
    if t == "rel":
        a, b = value(c["field"], r), value(c["other"], r)
        if a is None or b is None:
            return False
        b *= c.get("k", 1.0)
        return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[c["op"]]
    if t == "rank":
        x = value(c["field"], r, ctx["q"].get(r["ticker"]))
        return x is not None and (x >= c["cut"] if c["side"] == "top" else x <= c["cut"])
    if t == "sector":
        hay = f"{r.get('sector') or ''} | {r.get('subSector') or ''}".lower()
        return any(s in hay for w in c["words"] for s in SECTORS[w])
    if t == "size":
        rank = ctx["mcap_rank"].get(r["ticker"])
        return rank is not None and {"large": rank <= 100, "mid": 100 < rank <= 250, "small": rank > 250}[c["cls"]]
    if t == "insider":
        net = ctx["insider"][id(c)].get(r["ticker"], 0)
        return net > 0 if c["side"] == "buy" else net < 0
    if t == "turnaround":
        q = ctx["q"].get(r["ticker"]) or []
        return len(q) >= 5 and isinstance(q[-1]["netIncome"], (int, float)) and isinstance(q[-5]["netIncome"], (int, float)) \
            and q[-5]["netIncome"] <= 0 < q[-1]["netIncome"]
    return True


def _needs_quarters(c):
    return c["t"] == "turnaround" or (c["t"] in ("cmp", "rank") and isinstance(FIELDS[c["field"]][1], tuple) and FIELDS[c["field"]][1][0] == "q")


def _insider_net(c, today=None):
    """{symbol: net ₹ Cr} for the clause's people and side, and the window used."""
    got = insider.window_rows(today, int(c["days"]) if c.get("days") else None)
    if got is None:
        return None, None, None
    keep = (lambda r: "promoter" in r["category"].lower()) if c["who"] == "promoter" else (lambda r: r["senior"])
    rows = [r for r in got["rows"] if keep(r)]
    latest = max((r["date"] for r in got["rows"]), default=None)
    return {a["symbol"]: a["netCr"] for a in insider.by_company(rows)}, got["days"], latest


Q_TTL = 12 * 3600   # results change once a quarter; a day-old copy is fine, a fresh fetch per search is not


def quarters(tickers):
    """{ticker: marketlens.quarterly rows}, from ~/.orazio/cache first; only missing tickers are fetched (4 at a time)."""
    _, saved = screen.disk_load("ml-quarterly", 30 * 86400)
    now = time.time()
    saved = {t: e for t, e in (saved or {}).items() if now - e[0] < Q_TTL}          # entry: [saved_at, rows]
    missing = [t for t in tickers if t not in saved]
    if missing:
        with ThreadPoolExecutor(max_workers=4) as pool:
            got = {t: [now, q] for t, q in zip(missing, pool.map(marketlens.quarterly, missing)) if q}
        if got:
            saved.update(got)
            screen.disk_save("ml-quarterly", saved)   # ponytail: one file, rewritten whole; fine at ~1,100 tickers x 5 rows
    return {t: saved[t][1] if t in saved else [] for t in tickers}


def _percentile(vals, pct):
    vals = sorted(vals)
    if not vals:
        return None
    k = (len(vals) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return round(vals[lo] + (vals[hi] - vals[lo]) * (k - lo), 2)


def run(clauses, drop=(), notes=None):
    """Clauses -> results with a funnel: how many stocks are left after each clause, cheapest checks first."""
    notes = notes if notes is not None else []
    uni = screen.universe()
    if not uni:
        return {"available": False, "reason": "NSE MarketLens isn't answering right now."}
    active = [c for i, c in enumerate(clauses) if i not in drop]
    by_mcap = sorted(uni.values(), key=lambda r: -(r.get("marketCap") or 0))
    ctx = {"q": {}, "insider": {}, "mcap_rank": {r["ticker"]: i + 1 for i, r in enumerate(by_mcap)}}

    for c in active:                                   # resolve quality words to numbers over the whole universe
        if c["t"] == "rank" and not _needs_quarters(c):
            vals = [x for r in uni.values() if (x := value(c["field"], r)) is not None and (c["field"] not in ("pe", "pb") or x > 0)]
            c["cut"] = _percentile(vals, 100 - c["pct"] if c["side"] == "top" else c["pct"])
    rows = list(uni.values())
    funnel = []
    index = {id(c): i for i, c in enumerate(clauses)}
    order = sorted(range(len(active)), key=lambda i: (active[i]["t"] == "insider", _needs_quarters(active[i]), active[i]["t"] in ("sort", "limit")))
    for i in order:
        c = active[i]
        if c["t"] in ("sort", "limit"):
            continue
        if c["t"] == "insider":
            got, days, latest = _insider_net(c)
            if got is None:
                return {"available": False, "reason": "NSE's insider-trade feed isn't answering right now."}
            ctx["insider"][id(c)] = got
            c["used_days"], c["latest"] = days, latest
        if _needs_quarters(c) and not ctx.get("q_loaded"):
            rows.sort(key=lambda r: -(r.get("marketCap") or 0))
            if len(rows) > QUARTERLY_CAP:
                notes.append(f"Quarterly results checked for the {QUARTERLY_CAP} largest of {len(rows)} candidates; add a sector or a ratio to narrow it.")
                rows = rows[:QUARTERLY_CAP]
            ctx["q"].update(quarters([r["ticker"] for r in rows]))
            ctx["q_loaded"] = True
            if c["t"] == "rank":
                vals = [x for r in rows if (x := value(c["field"], r, ctx["q"].get(r["ticker"]))) is not None]
                c["cut"] = _percentile(vals, 100 - c["pct"] if c["side"] == "top" else c["pct"])
        before = len(rows)
        rows = [r for r in rows if _test(c, r, ctx) != bool(c.get("neg"))]
        funnel.append({"index": index[id(c)], "before": before, "after": len(rows)})

    sort = next((c for c in reversed(active) if c["t"] == "sort"), None)
    limit = next((c.get("limit") for c in reversed(active) if c["t"] in ("sort", "limit") and c.get("limit")), None)
    if sort:
        rows.sort(key=lambda r: (value(sort["field"], r, ctx["q"].get(r["ticker"])) is None,
                                 -(value(sort["field"], r, ctx["q"].get(r["ticker"])) or 0) if sort["desc"] else (value(sort["field"], r, ctx["q"].get(r["ticker"])) or 0)))
    else:
        rows.sort(key=lambda r: -(r.get("marketCap") or 0))
    count = len(rows)
    rows = rows[:limit] if limit else rows
    shown = [f for c in active for f in ([c["field"]] if c["t"] in ("cmp", "rank", "sort") else [c["field"], c["other"]] if c["t"] == "rel" else [])]
    extra = [f for f in dict.fromkeys(shown) if f not in ("price", "mcap", "pe", "roce", "promoter")]
    insider_net = {}
    for c in active:
        if c["t"] == "insider":
            insider_net.update(ctx["insider"][id(c)])
    out = []
    for r in rows[:screen.SHOW]:
        qs = ctx["q"].get(r["ticker"])
        row = {**screen._row(r), "values": {f: _round(value(f, r, qs)) for f in extra}}
        if insider_net:
            row["insiderNetCr"] = insider_net.get(r["ticker"])
        out.append(row)
    return {"available": True, "count": count, "universe": len(uni), "rows": out, "funnel": funnel, "notes": notes,
            "columns": [{"id": f, "label": FIELDS[f][0], "pct": f in PCT_FIELDS} for f in extra] + ([{"id": "insiderNetCr", "label": "Insider net ₹ Cr", "pct": False}] if insider_net else [])}


def _round(x):
    return round(x, 2) if isinstance(x, float) else x


def ask(question, drop=(), llm=None, skipped=False):
    """Plain English -> results. llm: callable(question, parsed) -> dict or None (deep_llm.read), tried only on unread words.
    The answer's "model" says whether a model was used: {"used": False, "why": ...} or {"used": True, source, seconds, cached, ...}."""
    q = (question or "").strip()
    if not q:
        raise ValueError("Describe the stocks you want, like: IT companies that beat earnings with promoter buying")
    p = parse(q)
    clauses, source, notes = p["clauses"], "rules", []
    model = {"used": False, "why": "rules read every word" if not p["unread"] else "switched off for this search" if skipped else "model fallback is off"}
    if p["unread"] and llm:
        got = llm(q, p)
        if got is None:
            model = {"used": False, "why": "model fallback is off"}
        else:
            model = {"used": True, "source": got.get("source"), "seconds": got.get("seconds"), "cached": got.get("cached"),
                     "words": p["unread"], "unsupported": got.get("unsupported") or [], "rejected": got.get("rejected", 0),
                     "error": got.get("error"), "applied": bool(got.get("clauses"))}
            if got.get("clauses"):
                clauses, source = [c for c in got["clauses"] if valid(c)], got.get("source", "model")
                p["unread"] = got.get("unsupported") or []
    if not clauses:
        out = screen.ask(q)                            # last resort: MarketLens's own builder, as Find always did
        return {**out, "clauses": [], "unread": p["unread"], "repaired": p["repaired"], "source": "marketlens", "model": model}
    if p["unread"]:
        built = marketlens.build_query(" ".join(p["unread"]))
        try:
            extra = screen.parse(built["query"], screen.gallery()) if built else []
        except ValueError:
            extra = []
        if extra:
            notes.append(f"MarketLens read “{' '.join(p['unread'])}” as {built['query']}; that part isn't applied yet.")
    out = run(clauses, drop=set(drop), notes=notes)
    out.update(question=q, source=source, model=model, unread=p["unread"], repaired=[{"was": a, "now": b} for a, b in p["repaired"]],
               clauses=[{"phrase": c.get("phrase", ""), "label": label(c), "kind": c["t"], "dropped": i in set(drop)} for i, c in enumerate(clauses)])
    return out


def suggest(text):
    """Autocomplete from the grammar (Bloomberg's 'semantically driven auto-completion'): what can follow what's typed."""
    t = normalise(text)
    head, _, last = t.rpartition(" ")
    out = []
    if last and not last.isdigit():
        names = sorted({p for p in list(IDIOMS) + [s for f in FIELDS.values() for s in f[3]] + list(SECTORS) + ["promoter buying", "insider buying", "promoter selling"]
                        if p.startswith(last) and p != last and not p.startswith(("w52", "dma")) and len(p) > 2}, key=len)
        out = [(head + " " + n).strip() for n in names[:6]]
    toks = tokens(_words(t)) if t.strip() else []
    if toks and toks[-1]["k"] == "field" and not last == "":
        fid = toks[-1]["id"]
        good = FIELDS[fid][2]
        typical = {"pe": 20, "pb": 3, "roce": 20, "roe": 15, "de": 0.5, "divy": 2, "mcap": 10000, "promoter": 50, "npm": 15,
                   "revyoy": 15, "profyoy": 15, "ret1y": 20, "price": 500, "delivery": 50}.get(fid, 10)
        out = [f"{t.strip()} {'below' if good == 'lo' else 'above'} {_fmt(typical)}", f"{t.strip()} between {_fmt(typical / 2)} and {_fmt(typical)}"] + out
    return out[:6]
