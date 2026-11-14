"""Deep search grammar: each sentence must read to exactly these clauses, offline (orazio/deep.py parse())."""
from datetime import date

import pytest

from orazio import deep

TODAY = date(2026, 11, 13)


def read(q):
    p = deep.parse(q, today=TODAY)
    out = set()
    for c in p["clauses"]:
        t = c["t"]
        key = {"cmp": lambda: (c["field"], c["op"], c["v"]) + ((c["v2"],) if c["op"] == "between" else ()),
               "rel": lambda: (c["field"], c["op"], c["other"], c.get("k", 1.0)),
               "rank": lambda: ("rank", c["field"], c["side"]),
               "sector": lambda: ("sector",) + tuple(c["words"]),
               "size": lambda: ("size", c["cls"]),
               "insider": lambda: ("insider", c["who"], c["side"]) + ((c["days"],) if c.get("days") else ()),
               "turnaround": lambda: ("turnaround",),
               "sort": lambda: ("sort", c["field"], c["desc"]) + ((c["limit"],) if c.get("limit") else ()),
               "limit": lambda: ("limit", c["limit"])}[t]()
        out.add(("not",) + key if c.get("neg") else key)
    return out, p["unread"]


CASES = [
    ("Indian IT companies which have beat earnings, positive growth this year with promoter buying",
     {("sector", "it"), ("profyoy", ">", 0), ("revyoy", ">", 0), ("insider", "promoter", "buy")}),
    ("debt free companies with ROCE above 20", {("de", "<=", 0.05), ("roce", ">", 20)}),
    ("roce > 20 and pe < 15", {("roce", ">", 20), ("pe", "<", 15)}),
    ("ROCE 20+", {("roce", ">=", 20)}),
    ("20%+ roce", {("roce", ">=", 20)}),
    ("pe between 10 and 20", {("pe", "between", 10, 20)}),
    ("p/e 10-20", {("pe", "between", 10, 20)}),
    ("market cap above 10,000 crore", {("mcap", ">", 10000)}),
    ("mcap over 1 lakh crore", {("mcap", ">", 100000)}),
    ("market cap > 10k cr", {("mcap", ">", 10000)}),
    ("market cap above 10k", {("mcap", ">", 10000)}),
    ("promoter holding above 70 and debt to equity below 0.1", {("promoter", ">", 70), ("de", "<", 0.1)}),
    ("golden cross stocks with price above their 50 DMA", {("dma50", ">", "dma200", 1.0), ("price", ">", "dma50", 1.0)}),
    ("stocks above 200 dma", {("price", ">", "dma200", 1.0)}),
    ("trading above the 200-day moving average", {("price", ">", "dma200", 1.0)}),
    ("near 52 week high", {("price", ">=", "w52high", 0.95)}),
    ("stocks near their 52-week lows", {("price", "<=", "w52low", 1.05)}),
    ("high dividend yield and low PE", {("rank", "divy", "top"), ("rank", "pe", "bottom")}),
    ("cheap pharma stocks", {("rank", "pe", "bottom"), ("sector", "pharma")}),
    ("pharma or chemicals with roce above 15", {("sector", "pharma", "chemicals"), ("roce", ">", 15)}),
    ("banks excluding small caps", {("sector", "banks"), ("not", "size", "small")}),
    ("non banking financials", {("sector", "financials"), ("not", "sector", "banking")}),
    ("large cap IT stocks", {("size", "large"), ("sector", "it")}),
    ("midcap auto stocks with strong growth", {("size", "mid"), ("sector", "auto"), ("revyoy", ">=", 15)}),
    ("revenue growth above 15% and profit growth over 20%", {("revyoy", ">", 15), ("profyoy", ">", 20)}),
    ("double digit revenue growth", {("revyoy", ">=", 10)}),
    ("top 10 by roce", {("sort", "roce", True, 10)}),
    ("10 cheapest banks", {("sort", "pe", False, 10), ("sector", "banks")}),
    ("highest dividend yield fmcg stocks", {("sort", "divy", True), ("sector", "fmcg")}),
    ("insider selling in banks in the last 3 months", {("insider", "insider", "sell", 90), ("sector", "banks")}),
    ("promoters bought shares recently", {("insider", "promoter", "buy", 90)}),
    ("stocks with buying by promoters", {("insider", "promoter", "buy")}),
    ("turnaround stocks", {("turnaround",)}),
    ("loss making companies", {("netprofit", "<", 0)}),
    ("up 20% this year", {("retytd", ">=", 20)}),
    ("stocks down 30% from 52 week high", {("offhigh", "<=", -30)}),
    ("gained 50% in 6 months", {("ret6m", ">=", 50)}),
    ("positive 1 year returns", {("ret1y", ">", 0)}),
    ("low debt high roe", {("rank", "de", "bottom"), ("rank", "roe", "top")}),
    ("good pe", {("rank", "pe", "bottom")}),
    ("quality midcaps", {("roce", ">=", 15), ("de", "<=", 0.5), ("size", "mid")}),
    ("companies that missed earnings", {("profyoy", "<", 0)}),
    ("penny stocks", {("price", "<", 20)}),
    ("roce ≥ 25", {("roce", ">=", 25)}),
    ("dividend yield at least 3%", {("divy", ">=", 3)}),
    ("p/b under 1.5", {("pb", "<", 1.5)}),
    ("price below rs 100", {("price", "<", 100)}),
    ("volume above 10 lakh", {("volume", ">", 10)}),
]


@pytest.mark.parametrize("q,want", CASES)
def test_reads(q, want):
    got, unread = read(q)
    assert got == want, f"{q!r}: got {got}"
    assert not unread, f"{q!r}: unread {unread}"


def test_typos_repaired():
    got, unread = read("promotor buyng in pharmaceutcal companies")
    assert ("insider", "promoter", "buy") in got and ("sector", "pharmaceutical") in got and not unread


def test_unknown_words_reported():
    _, unread = read("stocks with ROCE above 20 favoured by FIIs")
    assert "fiis" in " ".join(unread)


def test_every_clause_is_valid_and_labelled():
    for q, _ in CASES:
        for c in deep.parse(q, today=TODAY)["clauses"]:
            assert deep.valid(c), (q, c)
            assert deep.label(c)


def test_valid_rejects_bad_model_output():
    assert not deep.valid({"t": "cmp", "field": "roce", "op": ">", "v": "20"})
    assert not deep.valid({"t": "cmp", "field": "__import__", "op": ">", "v": 1})
    assert not deep.valid({"t": "sector", "words": ["crypto"]})
    assert deep.valid({"t": "insider", "who": "promoter", "side": "buy", "days": 90})


def test_suggest_completes_fields():
    s = deep.suggest("debt free stocks with ro")
    assert any("roce" in x for x in s)


# ---------- running, offline: a fixture universe, no NSE calls ----------
def _stock(t, sector, mcap_cr, roce, pe, profit_now, profit_ago, rev_now, rev_ago):
    return {"ticker": t, "name": t, "sector": sector, "subSector": "", "marketCap": mcap_cr * 1e7, "roce": roce, "peRatio": pe,
            "lastTradedPrice": 100, "week52High": 110, "netProfit": profit_now, "totalEquity": 100,
            "_q": [{"period": f"p{i}", "revenue": rev_ago if i == 0 else rev_now, "netIncome": profit_ago if i == 0 else profit_now, "eps": 1}
                   for i in range(5)]}


UNI = {s["ticker"]: s for s in [
    _stock("TCS", "IT - Software", 1200000, 60, 25, 14000, 12000, 63000, 56000),
    _stock("INFY", "IT - Software", 600000, 40, 22, 6000, 6500, 40000, 38000),
    _stock("WIPRO", "IT - Software", 250000, 18, 19, 3000, 2500, 22000, 23000),
    _stock("SUNPHARMA", "Pharmaceuticals & Biotechnology", 400000, 20, 35, 3000, 2000, 13000, 11000),
]}


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(deep.screen, "universe", lambda: UNI)
    monkeypatch.setattr(deep, "quarters", lambda ts: {t: UNI[t]["_q"] for t in ts})
    rows = [{"symbol": "TCS", "chartSymbol": "TCS.NS", "company": "TCS", "name": "Promoter Co", "category": "Promoter Group",
             "senior": True, "side": "buy", "qty": 1, "valueCr": 50.0, "date": "2026-04-20", "filed": None},
            {"symbol": "INFY", "chartSymbol": "INFY.NS", "company": "INFY", "name": "Founder", "category": "Promoter",
             "senior": True, "side": "buy", "qty": 1, "valueCr": 5.0, "date": "2026-04-21", "filed": None}]
    monkeypatch.setattr(deep.insider, "window_rows", lambda today=None, days=None: {"days": days or 365, "rows": rows})


def test_users_question_end_to_end(offline):
    d = deep.ask("Indian IT companies which have beat earnings, positive growth this year with promoter buying")
    assert [r["symbol"] for r in d["rows"]] == ["TCS"]          # INFY: profit fell; WIPRO: revenue fell, no buying
    assert [f["after"] for f in d["funnel"]][-1] == 1
    assert "latest disclosure: 2026-04-21" in next(c["label"] for c in d["clauses"] if c["kind"] == "insider")


def test_dropping_a_clause_loosens(offline):
    q = "IT companies which beat earnings with promoter buying"
    full = deep.ask(q)
    i = next(i for i, c in enumerate(full["clauses"]) if c["kind"] == "insider")
    assert deep.ask(q, drop={i})["count"] >= full["count"]


def test_rank_and_sort(offline):
    d = deep.ask("top 2 by roce")
    assert [r["symbol"] for r in d["rows"]] == ["TCS", "INFY"]
    d = deep.ask("not IT")
    assert [r["symbol"] for r in d["rows"]] == ["SUNPHARMA"]


def test_model_fallback_used_only_for_unread_words(offline):
    calls = []

    def llm(q, parsed):
        calls.append(q)
        return {"clauses": [{"t": "cmp", "field": "roce", "op": ">", "v": 30, "phrase": "x"}, {"t": "cmp", "field": "evil", "op": ">", "v": 1}],
                "source": "fake"}
    deep.ask("IT companies with roce above 30", llm=llm)
    assert not calls                                              # all words read: no model call
    d = deep.ask("IT companies favoured by fiis", llm=llm)
    assert calls and d["source"] == "fake" and [r["symbol"] for r in d["rows"]] == ["TCS", "INFY"]   # invalid clause dropped


def test_openai_compatible_backend_falls_back_to_plainer_format(monkeypatch):
    from orazio import deep_llm
    seen = []

    class R:
        def __init__(self, code, content=None):
            self.status_code, self._c = code, content

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": self._c}}]}

    def post(url, json, headers, timeout):
        seen.append(json.get("response_format", {}).get("type"))
        if json.get("response_format", {}).get("type") == "json_schema":
            return R(400)
        return R(200, '```json\n{"clauses":[{"t":"size","cls":"large","phrase":"large caps"}],"unsupported":[]}\n```')
    monkeypatch.setattr(deep_llm.requests, "post", post)
    d = deep_llm.read("large caps loved by everyone", cfg={"provider": "openai", "model": "qwen", "base": "ollama", "key": ""})
    assert seen == ["json_schema", "json_object"] and d["clauses"] == [{"t": "size", "cls": "large", "phrase": "large caps"}]


def test_answer_always_says_whether_a_model_was_used(offline):
    assert deep.ask("IT companies with roce above 30")["model"] == {"used": False, "why": "rules read every word"}
    assert deep.ask("IT companies favoured by fiis")["model"]["why"] == "model fallback is off"
    assert deep.ask("IT companies favoured by fiis", skipped=True)["model"]["why"] == "switched off for this search"
    failed = deep.ask("IT companies favoured by fiis", llm=lambda q, p: {"error": "timeout", "source": "claude", "cached": False, "seconds": 90})
    assert failed["model"]["used"] and failed["model"]["error"] == "timeout" and not failed["model"]["applied"]


def test_every_model_use_is_logged_and_cache_hits_marked(monkeypatch):
    from orazio import deep_llm
    calls = []
    monkeypatch.setitem(deep_llm.BACKENDS, "openai", lambda q, cfg: calls.append(q) or {"clauses": [{"t": "size", "cls": "mid", "phrase": "mid"}], "unsupported": []})
    cfg = {"provider": "openai", "model": "m", "base": "ollama", "key": ""}
    deep_llm.LOG.clear()
    first = deep_llm.read("midcaps loved by fiis zz1", cfg=cfg)
    second = deep_llm.read("midcaps loved by fiis zz1", cfg=cfg)
    assert len(calls) == 1 and not first["cached"] and second["cached"]
    assert [e["cached"] for e in deep_llm.log()] == [True, False] and all(e["ok"] for e in deep_llm.log())
