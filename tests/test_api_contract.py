"""The HTTP contract, route by route: what the frontend can rely on.

Everything network-bound is replaced at the service module the route calls (orazio.fno.panel,
orazio.gift_nifty.quote, ...), so these tests exercise routing, validation, status codes and response
shapes — not NSE or Yahoo. They are also the safety net that lets the routes be reorganised.
"""
import pandas as pd
import pytest

from orazio import cas, constituents, fno, gift_nifty, global_movers, market_breadth, market_data, movers, names, news, stats
from orazio.constants import QUICK_INDICES, SYMBOL_ALIASES
from orazio.symbols import clean_symbol


def get_json(client, url, status=200):
    resp = client.get(url)
    assert resp.status_code == status, f"{url} -> {resp.status_code}: {resp.get_data(as_text=True)[:200]}"
    return resp.get_json()


# ---- static page + config -------------------------------------------------------
def test_the_app_serves_its_page(client):
    resp = client.get("/")
    assert resp.status_code == 200 and b"<title>Orazio</title>" in resp.data


def test_unknown_routes_are_404(client):
    assert client.get("/api/nope").status_code == 404


def test_rail_order_is_the_agreed_one(client):
    q = get_json(client, "/api/config")["quickIndices"]
    assert q[:5] == ["NIFTY", "SENSEX", "NIFTYIT", "BANKNIFTY", "GIFTNIFTY"]            # SENSEX under NIFTY; GIFT Nifty under India
    assert q.index("DOWJONES") < q.index("CRUDE") < q.index("KOSPI") < q.index("BTC")  # commodities: after US, before Asia; crypto last
    assert len(q) == len(set(q)), "duplicate rail entries"


def test_every_rail_alias_resolves_to_a_valid_chart_symbol():
    for _label, alias in QUICK_INDICES:
        assert clean_symbol(alias)                                    # aborts with 400 if it is invalid
        assert alias in SYMBOL_ALIASES or alias == "GIFTNIFTY"        # GIFT Nifty has no Yahoo ticker: its alias is itself


# ---- quote -------------------------------------------------------------------------
def test_quote_for_a_yahoo_symbol(client, monkeypatch):
    monkeypatch.setattr(market_data, "yahoo_live_quote", lambda s: {"price": 110.0, "prevClose": 100.0, "marketTime": 1790000000, "currency": "USD"})
    d = get_json(client, "/api/quote?symbol=AAPL")
    assert d["price"] == 110.0 and d["change"] == 10.0 and d["changePercent"] == pytest.approx(10.0)
    assert d["source"] == "yahoo" and d["symbol"] == "AAPL"


def test_quote_for_a_future_comes_from_nse_fno(client, monkeypatch):
    monkeypatch.setattr(fno, "quote", lambda s: {"price": 22815.0, "prevClose": 22865.7, "marketTime": 1790745277, "currency": "INR"})
    d = get_json(client, "/api/quote?symbol=NIFTY-FUT")
    assert d["source"] == "nse-fno" and d["symbol"] == "NIFTY-FUT" and d["change"] == pytest.approx(-50.7)


def test_quote_for_gift_nifty_comes_from_nse(client, monkeypatch):
    monkeypatch.setattr(gift_nifty, "quote", lambda: {"price": 22587.5, "prevClose": 22655.5, "marketTime": 1790821740, "currency": "INR"})
    d = get_json(client, "/api/quote?symbol=GIFTNIFTY")
    assert d["source"] == "nse-gift" and d["price"] == 22587.5


def test_quote_is_502_when_the_future_feed_is_down_and_never_falls_back_to_yahoo(client, monkeypatch):
    monkeypatch.setattr(fno, "quote", lambda s: None)
    monkeypatch.setattr(market_data, "yahoo_live_quote", lambda s: pytest.fail("a future must not be quoted from Yahoo"))
    assert client.get("/api/quote?symbol=RELIANCE-FUT").status_code == 502


def test_quote_rejects_symbols_that_could_smuggle_url_characters(client):
    assert client.get("/api/quote?symbol=../../etc").status_code == 400


# ---- candles -----------------------------------------------------------------------
def yahoo_frame():
    idx = pd.to_datetime(["2026-09-30 09:15", "2026-09-30 09:16"]).tz_localize("Asia/Kolkata")
    return pd.DataFrame({"Open": [1.0, 2.0], "High": [2.0, 3.0], "Low": [0.5, 1.5], "Close": [1.5, 2.5], "Volume": [100, 200]}, index=idx)


def test_candles_have_the_shape_the_chart_expects(client, monkeypatch):
    import yfinance
    monkeypatch.setattr(yfinance, "download", lambda *a, **k: yahoo_frame())
    d = get_json(client, "/api/candles?symbol=AAPL&interval=1m&range=1D")
    assert (d["symbol"], d["interval"], d["range"]) == ("AAPL", "1m", "1D")
    assert d["liveBars"] == 0 and len(d["candles"]) == 2
    first = d["candles"][0]
    assert set(first) == {"time", "open", "high", "low", "close", "volume"} and isinstance(first["time"], int)
    assert d["candles"][0]["time"] < d["candles"][1]["time"]


def test_a_range_yahoo_cannot_serve_at_the_requested_bar_size_escalates_and_says_so(client, monkeypatch):
    import yfinance
    seen = {}
    monkeypatch.setattr(yfinance, "download", lambda sym, period, interval, **k: seen.update(period=period, interval=interval) or yahoo_frame())
    d = get_json(client, "/api/candles?symbol=AAPL&interval=1m&range=1Y")
    assert d["interval"] == "1h" and seen == {"period": "1y", "interval": "1h"}           # 1m bars don't reach back a year


def test_future_candles_come_from_the_fno_module(client, monkeypatch):
    payload = {"symbol": "NIFTY-FUT", "interval": "1m", "range": "1D", "candles": [{"time": 1}], "liveBars": 0}
    monkeypatch.setattr(fno, "candles", lambda s, i, r: payload)
    assert get_json(client, "/api/candles?symbol=NIFTY-FUT&interval=1m&range=1D") == payload


def test_an_unknown_future_is_404_not_a_server_error(client, monkeypatch):
    monkeypatch.setattr(fno, "candles", lambda s, i, r: (_ for _ in ()).throw(ValueError("not an F&O symbol")))
    assert client.get("/api/candles?symbol=IWP-FUT").status_code == 404


def test_gift_nifty_chart_reports_the_interval_actually_served(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(gift_nifty, "chart", lambda interval, rng: seen.update(interval=interval, rng=rng) or ("1d", [{"time": 1}]))
    d = get_json(client, "/api/candles?symbol=GIFTNIFTY&interval=5m&range=1M")
    assert d["interval"] == "1d"                                    # escalated: no intraday history that far back
    assert d["candles"] == [{"time": 1}] and seen == {"interval": "5m", "rng": "1M"}


def test_lazy_history_has_nothing_older_for_futures_and_gift_nifty(client):
    for symbol in ("NIFTY-FUT", "GIFTNIFTY"):
        d = get_json(client, f"/api/candles/history?symbol={symbol}&interval=1m&before=1790000000")
        assert d["exhausted"] is True and d["candles"] == []


def test_lazy_history_requires_a_numeric_before(client):
    assert client.get("/api/candles/history?symbol=AAPL&interval=1m&before=abc").status_code == 400


# ---- movers --------------------------------------------------------------------------
def test_movers_for_a_global_universe_come_back_with_company_names(client, monkeypatch):
    monkeypatch.setattr(global_movers, "movers", lambda u: {"universe": u, "available": True, "asOf": None,
        "gainers": [{"symbol": "688185", "chartSymbol": "688185.SS", "perChange": 20.0}], "losers": []})
    monkeypatch.setattr(names, "english_name", lambda s: "CanSino Biologics Inc.")
    d = get_json(client, "/api/movers?universe=SSE")
    assert d["gainers"][0]["name"] == "CanSino Biologics Inc."


def test_movers_for_an_index_computed_from_constituents(client, monkeypatch):
    monkeypatch.setattr(constituents, "movers_for", lambda alias: {"gainers": [{"symbol": "005930", "chartSymbol": "005930.KS", "perChange": 2.0}], "losers": []})
    monkeypatch.setattr(names, "english_name", lambda s: "Samsung Electronics Co., Ltd.")
    d = get_json(client, "/api/movers?universe=KOSPI")
    assert d["available"] and d["gainers"][0]["name"] == "Samsung Electronics Co., Ltd."


def test_constituent_movers_not_ready_yet_is_unavailable_not_an_error(client, monkeypatch):
    monkeypatch.setattr(constituents, "movers_for", lambda alias: None)
    assert get_json(client, "/api/movers?universe=KOSPI") == {"available": False, "universe": "KOSPI", "gainers": [], "losers": []}


def test_movers_default_to_the_nse_whole_market(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(movers, "movers", lambda u: seen.setdefault("u", u) and {"available": True, "universe": u, "gainers": [], "losers": []})
    get_json(client, "/api/movers")
    assert seen["u"] == "allSec"


# ---- breadth -------------------------------------------------------------------------
def test_breadth_merges_nse_constituent_and_exchange_published_counts(client, monkeypatch):
    monkeypatch.setattr(cas, "all_indices", lambda: None)
    monkeypatch.setattr(cas, "breadth_rows", lambda: [{"alias": "NIFTY", "advances": 1, "declines": 2, "unchanged": 0}])
    monkeypatch.setattr(constituents, "breadth_rows", lambda: [{"alias": "CHINA", "advances": 3, "declines": 4, "unchanged": 0}])
    monkeypatch.setattr(market_breadth, "breadth_rows", lambda: [{"alias": "SSE", "advances": 5, "declines": 6, "unchanged": 0}])
    aliases = [r["alias"] for r in get_json(client, "/api/breadth")["indices"]]
    assert aliases == ["NIFTY", "CHINA", "SSE"]


# ---- F&O -----------------------------------------------------------------------------
def test_fno_panel_payload_is_passed_through(client, monkeypatch):
    monkeypatch.setattr(fno, "panel", lambda symbol, expiry=None: {"available": True, "symbol": symbol, "expiry": expiry})
    # aliases (NIFTY) are resolved to the chart symbol (^NSEI) before the F&O module sees them
    assert get_json(client, "/api/fno?symbol=NIFTY&expiry=06-Oct-2026") == {"available": True, "symbol": "^NSEI", "expiry": "06-Oct-2026"}


def test_fno_for_a_stock_without_contracts_explains_instead_of_failing(client, monkeypatch):
    monkeypatch.setattr(fno, "fno_stocks", lambda: {"RELIANCE": "Reliance"})
    d = get_json(client, "/api/fno?symbol=IWP.NS")
    assert d["available"] is False and "reason" in d


def test_fno_symbol_list_is_sorted(client, monkeypatch):
    monkeypatch.setattr(fno, "fno_stocks", lambda: {"TCS": "t", "ABB": "a", "INFY": "i"})
    assert get_json(client, "/api/fno/symbols") == {"stocks": ["ABB", "INFY", "TCS"]}


# ---- news / names / stats -----------------------------------------------------------------
def test_news_for_a_future_searches_the_underlying_spot(client, monkeypatch):
    monkeypatch.setattr(fno, "fno_stocks", lambda: {"RELIANCE": "Reliance"})
    asked = []
    monkeypatch.setattr(news, "headlines", lambda s: asked.append(s) or [{"title": "t", "publisher": "p", "url": "https://x", "time": 1}])
    monkeypatch.setattr(news, "query_for", lambda s: "q")
    d = get_json(client, "/api/news?symbol=RELIANCE-FUT")
    assert asked == ["RELIANCE.NS"] and d["symbol"] == "RELIANCE.NS" and d["available"] and len(d["items"]) == 1


def test_news_reports_an_unreachable_source_as_unavailable(client, monkeypatch):
    monkeypatch.setattr(news, "headlines", lambda s: None)
    monkeypatch.setattr(news, "query_for", lambda s: "q")
    d = get_json(client, "/api/news?symbol=AAPL")
    assert d["available"] is False and d["items"] == []


def test_name_for_a_future_describes_the_contract(client, monkeypatch):
    monkeypatch.setattr(fno, "fno_stocks", lambda: {"RELIANCE": "Reliance Industries Limited"})
    assert get_json(client, "/api/name?symbol=RELIANCE-FUT")["name"] == "Reliance Industries Limited — futures (front month)"


def test_name_for_a_plain_symbol_is_the_company_name(client, monkeypatch):
    monkeypatch.setattr(names, "english_name", lambda s: "Apple Inc.")
    assert get_json(client, "/api/name?symbol=AAPL") == {"symbol": "AAPL", "name": "Apple Inc."}


def test_stats_available_and_unavailable(client, monkeypatch):
    monkeypatch.setattr(stats, "stats_for", lambda s: {"volume": 5} if s == "^NSEI" else None)
    d = get_json(client, "/api/stats?symbol=NIFTY")
    assert d["available"] is True and d["volume"] == 5 and d["symbol"] == "^NSEI"
    assert get_json(client, "/api/stats?symbol=SPX") == {"available": False, "symbol": "^GSPC"}


def test_stats_include_live_volume_bars_only_for_tracked_indices(client, monkeypatch):
    from orazio import live_volume
    monkeypatch.setattr(stats, "stats_for", lambda s: {"volume": 5})
    monkeypatch.setattr(live_volume, "bucket_volumes", lambda s, step: {1790739900: 123.0})
    assert "volumeBars" in get_json(client, "/api/stats?symbol=NIFTY&interval=1m")
    assert "volumeBars" not in get_json(client, "/api/stats?symbol=RELIANCE.NS&interval=1m")


# ---- export (writes files: the part that must not be reachable from other websites) ------------------
def test_download_validation_errors_are_json_400s(client):
    d = get_json(client, "/api/export/download?symbol=NIFTY&universe=CURRENT&interval=1m&mode=day&day=2000-01-01", status=400)
    assert "only go back 7 days" in d["error"]


def test_export_options_describe_every_bar_size_with_its_limit(client):
    d = get_json(client, "/api/export/options?symbol=NIFTY")
    by = {i["value"]: i for i in d["intervals"]}
    assert by["1m"]["maxDays"] == 7 and by["1d"]["maxDays"] is None and by["1d"]["earliest"] is None
    assert {u["value"] for u in d["universes"]} >= {"CURRENT", "NIFTY", "BANKNIFTY", "NIFTYIT"}


def test_schedule_changes_from_another_website_are_refused(client):
    for url in ("/api/export/schedule", "/api/export/schedule/run"):
        resp = client.post(url, json={"enabled": False}, headers={"Origin": "https://evil.example"})
        assert resp.status_code == 403, url


def test_schedule_validation_errors_are_json_400s(client):
    resp = client.post("/api/export/schedule", json={"enabled": True, "time": "99:99"})
    assert resp.status_code == 400 and "HH:MM" in resp.get_json()["error"]


def test_schedule_can_be_saved_and_read_back_from_the_same_origin(client, isolated_state):
    body = {"enabled": True, "time": "15:45", "path": str(isolated_state / "exports"), "format": "csv", "interval": "5m", "universe": "BANKNIFTY"}
    resp = client.post("/api/export/schedule", json=body, headers={"Origin": "http://localhost"})
    assert resp.status_code == 200
    assert get_json(client, "/api/export/schedule")["universe"] == "BANKNIFTY"


# ---- search -----------------------------------------------------------------------------------
def test_search_shapes_yahoo_results_and_tolerates_failure(client, monkeypatch):
    class R:
        def raise_for_status(self): pass
        def json(self): return {"quotes": [{"symbol": "RELIANCE.NS", "shortname": "RELIANCE", "exchange": "NSI", "quoteType": "EQUITY"}, {"shortname": "no symbol"}]}
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    assert get_json(client, "/api/search?q=reli") == [{"symbol": "RELIANCE.NS", "name": "RELIANCE", "exchange": "NSI", "type": "EQUITY"}]
    assert get_json(client, "/api/search?q=") == []
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.RequestException("down")))
    assert get_json(client, "/api/search?q=reli") == []
