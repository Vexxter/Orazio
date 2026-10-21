"""Screener rows: NSE market-watch shaping, the technicals merge, the universe whitelist, and the
NSE-blocked path."""
from unittest.mock import patch

import pytest

from orazio import screener, technicals

NSE_ROWS = [
    {"priority": 1, "symbol": "NIFTY 500", "lastPrice": 22000},
    {"priority": 0, "symbol": "ICICIBANK", "series": "EQ", "lastPrice": 1384.9, "pChange": -0.87,
     "totalTradedVolume": 12939108, "totalTradedValue": 18090943241.28, "yearHigh": 1480, "yearLow": 1187.6,
     "perChange30d": 3.44, "perChange365d": -3.59, "companyName": "ICICI BANK LIMITED",
     "lastUpdateTime": "2026-10-19 10:43:02"},
    {"priority": 0, "symbol": "BARE", "lastPrice": None},
]


@pytest.fixture
def no_technicals(monkeypatch):
    monkeypatch.setattr(technicals, "ensure_fresh", lambda now=None: "loading")
    monkeypatch.setattr(technicals, "_data", None)


def test_shape_computes_value_in_crore_and_distance_from_the_52_week_range():
    row = screener.shape(NSE_ROWS[1])
    assert row["chartSymbol"] == "ICICIBANK.NS"
    assert row["valueCr"] == 1809.09
    assert row["fromHigh"] == round((1384.9 - 1480) / 1480 * 100, 2)
    assert row["fromLow"] == round((1384.9 - 1187.6) / 1187.6 * 100, 2)
    assert row["name"] == "ICICI BANK LIMITED"


def test_missing_fields_become_null_not_a_crash():
    row = screener.shape(NSE_ROWS[2])
    assert row["ltp"] is None and row["fromHigh"] is None and row["valueCr"] is None


def test_screen_drops_the_index_row_and_reports_technicals_loading(no_technicals):
    with patch("orazio.screener._rows", return_value=NSE_ROWS):
        d = screener.screen("nifty500")
    assert d["available"] and d["technicals"] == "loading"
    assert [r["symbol"] for r in d["rows"]] == ["ICICIBANK", "BARE"]
    assert d["asOf"] == "2026-10-19 10:43:02"


def test_unknown_universe_falls_back_to_nifty500(no_technicals):
    seen = []
    with patch("orazio.screener._rows", side_effect=lambda name: seen.append(name) or []):
        d = screener.screen("../etc")
    assert d["universe"] == "nifty500" and seen == ["NIFTY 500"]


def test_nse_blocked_means_unavailable(no_technicals):
    with patch("orazio.screener._rows", return_value=[]):
        d = screener.screen("nifty50")
    assert d == {"available": False, "universe": "nifty50", "asOf": None, "technicals": "loading",
                 "technicalsAsOf": None, "rows": []}


def test_technicals_merge_at_the_live_price_skipping_todays_yahoo_bar(monkeypatch):
    bars = [[f"2026-{m:02d}-{d:02d}", 1000.0] for m in range(1, 11) for d in range(1, 26)][:240]
    bars.append(["2026-10-19", 5.0])   # today's partial bar from Yahoo: must be ignored
    monkeypatch.setattr(technicals, "ensure_fresh", lambda now=None: "ready")
    monkeypatch.setattr(technicals, "_data", {"fetchedAt": 1.0, "closes": {"ICICIBANK": bars}})
    with patch("orazio.screener._rows", return_value=NSE_ROWS[:2]):
        row = screener.screen("nifty500")["rows"][0]
    assert row["rsi"] == 100.0                     # flat history, then a jump up to the live 1384.9
    sma200 = (1000.0 * 199 + 1384.9) / 200
    assert row["vsSma200"] == round((1384.9 - sma200) / sma200 * 100, 2)
    assert row["cross"] == "golden"


def test_route_contract(client, no_technicals):
    with patch("orazio.screener._rows", return_value=NSE_ROWS):
        d = client.get("/api/screener?universe=bank").get_json()
    assert d["universe"] == "bank"
    assert set(d["rows"][0]) == {"symbol", "chartSymbol", "name", "ltp", "pChange", "volume", "valueCr", "fromHigh",
                                 "fromLow", "ch30", "ch365", "rsi", "vsSma50", "vsSma200", "cross"}
