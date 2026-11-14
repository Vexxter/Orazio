"""NSE MarketLens client and the NSE-first / Yahoo-fallback merge, against MarketLens shapes as measured on 13 Nov 2026."""
from orazio import fundamentals, marketlens

STOCK = {"name": "Tata Consultancy Services Limited", "sector": "IT - Software", "subSector": "Information Technology",
         "marketCap": 8797017991265.2, "lastTradedPrice": 2431.4, "peRatio": 17.04, "pbRatio": 9.59, "returnOnEquity": 0,
         "revenueGrowth": 0, "industryPe": 0, "beta": 1, "roce": 54.93, "roa": 27.12, "netMargin": 18.22, "debtToEquity": 0,
         "divYield": 4.45, "eps": 38.37, "bookValue": 254.634, "netProfit": 494540, "totalEquity": 1084780, "promoterHolding": 71.77,
         "oneYearReturn": -21.71, "description": "TCS, is a  Public Company.<br/><br/> Email: <a href='mailto:x@tcs.com'>x@tcs.com</a>.",
         "lastUpdated": "2026-11-13T10:05:01"}
QUARTERS = [{"date": d, "totalIncome": inc, "profitBeforeTax": 1800000, "netProfitLoss": np_, "eps": eps}
            for d, inc, np_, eps in [("30-Sep-2026", 6349000, 1410400, 38.98), ("30-Jun-2026", 6295900, 1364200, 37.7),
                                     ("31-Mar-2026", 6156800, 1452600, 40.15), ("31-Dec-2025", 5761600, 1019000, 28.16),
                                     ("30-Sep-2025", 5629900, 1182800, 32.7)]]


def fake(pages):
    return lambda path: pages.get(path)


def test_quarterly_converts_lakh_to_crore_oldest_first(monkeypatch):
    monkeypatch.setattr(marketlens, "_get", fake({"/api/stocks/TCS/quarterly-financials": QUARTERS}))
    q = marketlens.quarterly("TCS")
    assert q[0]["period"] == "2025-09-30" and q[-1] == {"period": "2026-09-30", "revenue": 63490.0, "profitBeforeTax": 18000.0, "netIncome": 14104.0, "eps": 38.98}


def test_ratios_drop_placeholders_and_use_ttm_eps(monkeypatch):
    monkeypatch.setattr(marketlens, "_get", fake({"/api/stocks/TCS/quarterly-financials": QUARTERS}))
    r = marketlens.ratios(STOCK, marketlens.quarterly("TCS"))
    assert r["marketCapCr"] == 879702 and r["pe"] == 17.04 and r["pb"] == 9.59 and r["debtToEquity"] == 0   # debt-free is a real 0
    assert r["roe"] == round(494540 / 1084780 * 100, 2)          # computed: its returnOnEquity is a 0 placeholder
    assert r["eps"] == round(38.98 + 37.7 + 40.15 + 28.16, 2)   # its own eps is one quarter
    assert r["revenueGrowth"] == round((63490 / 56299 - 1) * 100, 2)
    assert r["dividendYield"] == 4.45 and r["promoterHolding"] == 71.77 and "beta" not in r
    assert marketlens.ratios({**STOCK, "peRatio": 0, "pbRatio": 0, "totalEquity": 0})["pe"] is None


def test_plain_strips_markup():
    assert marketlens.plain(STOCK["description"]) == "TCS, is a Public Company. Email: x@tcs.com."
    assert marketlens.plain(None) == ""


def test_ticker_only_for_nse_stocks():
    assert marketlens.ticker("tcs.ns") == "TCS" and marketlens.ticker("^NSEI") is None and marketlens.ticker("AAPL") is None


def test_failed_calls_are_not_cached(monkeypatch):
    calls = []

    class Down:
        def get(self, *a, **k):
            calls.append(1)
            raise marketlens.requests.ConnectionError

    monkeypatch.setattr(marketlens, "_http", Down())
    assert marketlens.stock("TCS") is None and marketlens.stock("TCS") is None and len(calls) == 2


def test_merge_prefers_nse_and_says_who_answered():
    out, src = fundamentals.merge({"pe": 17.0, "evEbitda": None}, {"pe": 18.0, "evEbitda": 11.7, "beta": None})
    assert out == {"pe": 17.0, "evEbitda": 11.7, "beta": None} and src == {"pe": "nse", "evEbitda": "yahoo", "beta": None}


def test_fresher_takes_yahoo_only_when_it_has_a_newer_quarter():
    nse = [{"period": "2026-06-30"}]
    yahoo = [{"period": "2026-09-30"}]
    assert fundamentals.fresher(nse, yahoo) == (yahoo, "yahoo")
    assert fundamentals.fresher(yahoo, nse) == (yahoo, "nse")
    assert fundamentals.fresher([], []) == ([], None)


def test_fundamentals_nse_first_yahoo_fills_the_rest(monkeypatch):
    monkeypatch.setattr(marketlens, "_get", fake({"/api/stocks/TCS": STOCK, "/api/stocks/TCS/quarterly-financials": QUARTERS}))
    yahoo = {"quarterly": [{"period": "2026-06-30", "revenue": 1.0}], "annual": [{"period": "2026-03-31", "revenue": 2.0}], "balance": [], "cashflow": [],
             "ratios": {"pe": 99.0, "evEbitda": 11.7}, "info": {}, "price": 2400.0, "reportedIn": "INR", "fxRate": None}
    asked = []
    monkeypatch.setattr(fundamentals, "metrics", lambda sym, with_info=True: asked.append(with_info) or yahoo)
    monkeypatch.setattr(fundamentals, "industries", lambda: {})
    d = fundamentals.fundamentals("TCS.NS")
    assert asked == [False]                                      # NSE had a profile: Yahoo's rate-limited one isn't asked
    assert d["ratios"]["pe"] == 17.04 and d["ratioSource"]["pe"] == "nse"
    assert d["ratios"]["evEbitda"] == 11.7 and d["ratioSource"]["evEbitda"] == "yahoo"
    assert d["quarterlySource"] == "nse" and d["annual"] == yahoo["annual"] and d["price"] == 2431.4
    assert d["name"] == STOCK["name"] and d["summary"].startswith("TCS, is a Public")


def test_peers_use_nse_list_and_fall_back_to_yahoo_per_peer(monkeypatch):
    pages = {"/api/stocks/TCS/peers": [{"ticker": "TCS"}, {"ticker": "INFY"}, {"ticker": "GONE"}], "/api/stocks/TCS": STOCK,
             "/api/stocks/INFY": {**STOCK, "name": "Infosys", "peRatio": 15.0}}
    monkeypatch.setattr(marketlens, "_get", fake(pages))
    monkeypatch.setattr(fundamentals, "industries", lambda: {})
    monkeypatch.setattr(fundamentals, "metrics", lambda sym, with_info=True: {"ratios": {"pe": 20.0, "pb": 3.0, "roe": 10.0, "marketCapCr": 5}} if sym == "GONE.NS" else {})
    p = fundamentals.peers("TCS.NS")
    assert [(r["symbol"], r["source"]) for r in p["rows"]] == [("TCS", "nse"), ("INFY", "nse"), ("GONE", "yahoo")]
    assert p["industry"] == "IT - Software" and p["median"]["pe"] == 17.5 and p["complete"]
