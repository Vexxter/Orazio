"""Plain-English screens: parsing MarketLens filter expressions and evaluating them over the universe."""
import pytest

from orazio import screen

NAMES = {"price to earning (p/e)": "peRatio", "return on capital employed (roce)": "roce", "market cap (in cr)": "marketCap",
         "close price": "closePrice", "52w high": "week52High", "50 dma": "dma50", "200 dma": "dma200", "return over (%) 1 year": "oneYearReturn",
         "volume (in lakhs)": "volume"}
TCS = {"ticker": "TCS", "name": "TCS", "peRatio": 17.0, "roce": 54.9, "marketCap": 8.8e12, "closePrice": 2431.0, "week52High": 3350.0,
       "dma50": 2295.0, "dma200": 2399.0, "oneYearReturn": -21.7, "volume": 664428}
ZERO = {**TCS, "ticker": "ZERO", "peRatio": 0, "marketCap": 5e10}


def test_parse_reads_fields_numbers_commas_and_arithmetic():
    c = screen.parse("Market Cap (in Cr) >= 10,000 AND Close Price >= 52W High * 0.95 AND Return Over (%) 1 Year > 15", NAMES)
    assert c[0] == (("field", "marketCap"), ">=", ("num", 10000.0))
    assert c[1] == (("field", "closePrice"), ">=", ("calc", ("field", "week52High"), "*", 0.95))
    assert c[2] == (("field", "oneYearReturn"), ">", ("num", 15.0))


def test_parse_rejects_what_it_cannot_read():
    with pytest.raises(ValueError, match="Unknown field"):
        screen.parse("Moon Phase > 3", NAMES)
    with pytest.raises(ValueError, match="Only AND"):
        screen.parse("Close Price > 1 OR Close Price < 2", NAMES)


def test_matches_scales_market_cap_and_volume_and_treats_zero_pe_as_missing():
    assert screen.matches(TCS, screen.parse("Market Cap (in Cr) > 800000 AND Volume (in Lakhs) > 6", NAMES))
    assert not screen.matches(TCS, screen.parse("Close Price >= 52W High * 0.95", NAMES))
    assert screen.matches(TCS, screen.parse("50 DMA < 200 DMA * 1", NAMES))
    assert not screen.matches(ZERO, screen.parse("Price to Earning (P/E) < 15", NAMES))   # 0 is "no P/E", not cheap


def test_ask_runs_expressions_directly_and_questions_through_nse(monkeypatch):
    monkeypatch.setattr(screen, "gallery", lambda: NAMES)
    monkeypatch.setattr(screen, "universe", lambda: {"TCS": TCS, "ZERO": ZERO})
    d = screen.ask("Price to Earning (P/E) < 20")
    assert d["count"] == 1 and d["rows"][0]["symbol"] == "TCS" and d["readAs"] == ["Run as typed."]
    monkeypatch.setattr(screen.marketlens, "build_query", lambda q: {"query": "Return on Capital Employed (ROCE) > 50", "read_as": ["ROCE above 50"], "suggestions": []})
    d = screen.ask("very high roce companies")
    assert d["query"] == "Return on Capital Employed (ROCE) > 50" and d["readAs"] == ["ROCE above 50"] and d["rows"][0]["marketCapCr"] == 880000
    monkeypatch.setattr(screen.marketlens, "build_query", lambda q: {"query": "Moon Phase > 3"})
    assert not screen.ask("lunar stocks")["available"]


def test_ask_needs_a_question():
    with pytest.raises(ValueError):
        screen.ask("  ")
