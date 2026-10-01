"""The Closing Auction Session (CAS) routes: panel rows, movement chart data, and the stock-by-stock feed."""
from collections import deque

import pytest

from orazio import cas, market_data
from orazio.constants import NO_AUCTION_ALIASES
from orazio.routes import auction


def get_json(client, url, status=200):
    resp = client.get(url)
    assert resp.status_code == status, f"{url} -> {resp.status_code}: {resp.get_data(as_text=True)[:200]}"
    return resp.get_json()


@pytest.fixture
def nse_quiet(monkeypatch):
    """No live auction: NSE names no session, the clock decides."""
    monkeypatch.setattr(cas, "nse_session", lambda: (None, "Normal Market has Closed", None))


# ---- /api/cas ------------------------------------------------------------------------
def test_panel_rows_use_nse_for_nse_indices_and_bse_for_sensex(client, nse_quiet, monkeypatch):
    monkeypatch.setattr(cas, "all_indices", lambda: {"data": [
        {"index": "NIFTY 50", "previousClose": 100.0, "open": 101.0, "indicativeClose": 102.0, "last": 101.5}]})
    monkeypatch.setattr(market_data, "bse_live_quote", lambda _s: {"price": 72000.0, "prevClose": 72100.0})
    monkeypatch.setattr(market_data, "bse_raw_sensex", lambda: {"open": 72050.0, "indicativeClose": None})
    rows = {r["alias"]: r for r in get_json(client, "/api/cas")["indices"]}

    nifty = rows["NIFTY"]
    assert nifty["source"] == "nse" and nifty["openChangePct"] == pytest.approx(1.0) and nifty["indicativeClosePct"] == pytest.approx(2.0)
    sensex = rows["SENSEX"]
    assert sensex["source"] == "bse" and sensex["available"] and sensex["open"] == 72050.0 and sensex["indicativeClosePct"] is None
    assert rows["SPX"]["available"] is False and "No public closing-auction feed" in rows["SPX"]["reason"]


def test_assets_with_no_auction_are_left_out_of_the_panel(client, nse_quiet, monkeypatch):
    monkeypatch.setattr(cas, "all_indices", lambda: {"data": []})
    monkeypatch.setattr(market_data, "bse_live_quote", lambda _s: {})
    monkeypatch.setattr(market_data, "bse_raw_sensex", lambda: {})
    aliases = {r["alias"] for r in get_json(client, "/api/cas")["indices"]}
    assert not aliases & NO_AUCTION_ALIASES                         # no GIFT Nifty / commodities / crypto rows
    assert {"NIFTY", "SENSEX", "SPX"} <= aliases


def test_nse_naming_a_session_overrides_the_clock_and_drops_the_countdown(client, monkeypatch):
    monkeypatch.setattr(cas, "nse_session", lambda: ("pre-open", "Pre Open", {"value": 22000}))
    monkeypatch.setattr(cas, "all_indices", lambda: {"data": []})
    monkeypatch.setattr(cas, "cas_phase", lambda now: ("waiting:pre-open", 120, None, "Pre-open auction"))
    monkeypatch.setattr(market_data, "bse_live_quote", lambda _s: {})
    monkeypatch.setattr(market_data, "bse_raw_sensex", lambda: {})
    monkeypatch.setattr(auction, "nse_get", lambda path, params=None: {"advances": 7, "declines": 3, "unchanged": 1, "totalTradedValue": 5, "timestamp": "t"})
    d = get_json(client, "/api/cas")
    assert d["phase"] == "pre-open" and d["clockPhase"] == "waiting:pre-open"
    assert d["secondsRemaining"] is None                             # the countdown belonged to the clock's session, not NSE's
    assert d["breadth"] == {"advances": 7, "declines": 3, "unchanged": 1, "tradedValue": 5, "asOf": "t"}
    assert d["indicativeNifty"] == {"value": 22000}


def test_auction_breadth_is_only_fetched_during_an_auction(client, nse_quiet, monkeypatch):
    monkeypatch.setattr(cas, "all_indices", lambda: {"data": []})
    monkeypatch.setattr(market_data, "bse_live_quote", lambda _s: {})
    monkeypatch.setattr(market_data, "bse_raw_sensex", lambda: {})
    monkeypatch.setattr(cas, "cas_phase", lambda _now: ("waiting:pre-open", 3600, "", ""))   # not the real clock: it may be 09:00-09:15 IST
    monkeypatch.setattr(cas, "nse_session", lambda: (None, "", None))
    monkeypatch.setattr(auction, "nse_get", lambda *a, **k: pytest.fail("breadth fetched outside an auction"))
    assert get_json(client, "/api/cas")["breadth"] is None


# ---- /api/cas/feed -------------------------------------------------------------------------
def test_feed_key_must_be_fo_or_all(client):
    assert client.get("/api/cas/feed?key=BOGUS").status_code == 400


CAS_PAYLOAD = {"timestamp": "30-Sep-2026 15:20:00", "status": "OPEN", "symbols": ["A", "B", "C"], "totalQuantity": 10,
               "data": [{"symbol": "RELIANCE", "IEP": 1190.5, "refrencePrice": 1190.0, "perChange": 0.04,
                         "orderBook": [{"price": 1190.5, "buyQuantity": 100, "sellQuantity": 80, "flag": True}]}]}


def test_closing_auction_feed_lists_stocks_with_totals(client, monkeypatch):
    monkeypatch.setattr(cas, "nse_session", lambda: ("post-close", "Closing", None))
    monkeypatch.setattr(cas, "cas_payload", lambda: CAS_PAYLOAD)
    d = get_json(client, "/api/cas/feed")
    assert d["source"] == "cas" and d["live"] and d["eligible"] == 3
    assert [r["symbol"] for r in d["rows"]] == ["RELIANCE"] and d["rows"][0]["iep"] == 1190.5


def test_closing_auction_order_book_for_one_stock(client, monkeypatch):
    monkeypatch.setattr(cas, "nse_session", lambda: ("post-close", "Closing", None))
    monkeypatch.setattr(cas, "cas_payload", lambda: CAS_PAYLOAD)
    d = get_json(client, "/api/cas/feed?symbol=reliance")             # case-insensitive
    assert d["available"] and d["iep"] == 1190.5 and d["ladder"][0]["isIep"] is True
    missing = get_json(client, "/api/cas/feed?symbol=NOSUCH")
    assert missing["available"] is False and missing["ladder"] == []


PREOPEN_FEED = {"timestamp": "30-Sep-2026 09:08:00", "advances": 30, "declines": 20, "unchanged": 0, "totalTradedValue": 99,
                "data": [{"metadata": {"symbol": "TCS"}, "detail": {"preOpenMarket": {
                    "IEP": 2040.0, "prevClose": 2030.0, "Change": 10.0, "perChange": 0.49, "finalQuantity": 5,
                    "totalBuyQuantity": 50, "totalSellQuantity": 40, "atoBuyQty": 5, "atoSellQty": 4,
                    "preopen": [{"price": 2040.0, "buyQty": 50, "sellQty": 40, "iep": True}]}}},
                         {"metadata": {}, "detail": {}}]}


def test_preopen_feed_lists_stocks_and_skips_rows_without_a_symbol(client, monkeypatch):
    monkeypatch.setattr(cas, "nse_session", lambda: ("pre-open", "Pre Open", None))
    monkeypatch.setattr(cas, "cas_payload", lambda: {})
    monkeypatch.setattr(cas, "cas_feed_payload", lambda key: PREOPEN_FEED)
    d = get_json(client, "/api/cas/feed")
    assert d["source"] == "pre-open" and d["live"] is True and d["breadth"]["advances"] == 30
    assert [r["symbol"] for r in d["rows"]] == ["TCS"]


def test_preopen_order_book_for_one_stock(client, monkeypatch):
    monkeypatch.setattr(cas, "nse_session", lambda: ("pre-open", "Pre Open", None))
    monkeypatch.setattr(cas, "cas_payload", lambda: {})
    monkeypatch.setattr(cas, "cas_feed_payload", lambda key: PREOPEN_FEED)
    d = get_json(client, "/api/cas/feed?symbol=TCS")
    assert d["iep"] == 2040.0 and d["ladder"] == [{"price": 2040.0, "buyQty": 50, "sellQty": 40, "flag": None, "isIep": True}]
    assert get_json(client, "/api/cas/feed?symbol=NOSUCH")["available"] is False


def test_an_unreachable_preopen_feed_is_reported_not_raised(client, monkeypatch):
    monkeypatch.setattr(cas, "nse_session", lambda: ("pre-open", "Pre Open", None))
    monkeypatch.setattr(cas, "cas_payload", lambda: {})
    monkeypatch.setattr(cas, "cas_feed_payload", lambda key: None)
    d = get_json(client, "/api/cas/feed")
    assert d["available"] is False and d["rows"] == []


# ---- /api/cas/movement -------------------------------------------------------------------------
def test_movement_returns_each_index_series_with_its_reference(client, nse_quiet, monkeypatch):
    series = deque([(1000, 22000.0, None), (1003, 22005.0, 22010.0)])
    monkeypatch.setattr(cas, "nse_series", lambda alias: series if alias == "NIFTY" else deque())
    monkeypatch.setattr(cas, "nse_prev_close", lambda alias: 21950.0)
    monkeypatch.setattr(cas, "cas_reference", lambda alias, now, points: {"value": 22000.0} if alias == "NIFTY" else None)
    monkeypatch.setattr(cas, "cas_reference_epoch", lambda now: 1000)
    monkeypatch.setattr(market_data.bse_stream, "snapshot", lambda: None)
    monkeypatch.setattr(market_data.bse_stream, "series", lambda n: [])
    monkeypatch.setattr(market_data.bse_stream, "fresh", lambda: False)
    d = get_json(client, "/api/cas/movement")
    by = {i["alias"]: i for i in d["indices"]}
    assert list(by) == ["NIFTY", "BANKNIFTY", "NIFTYIT", "SENSEX"]
    assert by["NIFTY"]["available"] and by["NIFTY"]["last"] == 22005.0 and by["NIFTY"]["indicative"] == 22010.0
    assert by["NIFTY"]["reference"] == {"value": 22000.0} and by["NIFTY"]["prevClose"] == 21950.0
    assert by["BANKNIFTY"]["available"] is False and by["BANKNIFTY"]["points"] == []
    assert by["SENSEX"]["source"] == "BSE live stream" and by["SENSEX"]["live"] is False
    assert d["referenceAt"] == 1000 and "stream" in d
