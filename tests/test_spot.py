"""Spot commodities: Swissquote's live price, Dukascopy's history, the day's change, the WTI caveat (futures
history, spot price), and the routes picking spot by default."""
import pytest

from orazio import commodities, quotes, spot

SQ = [{"topo": {"platform": "SwissquoteLtd"}, "spreadProfilePrices": [{"spreadProfile": "prime", "bid": 100.36, "ask": 100.58}],
       "ts": 1792549879000}]
DUKA = "_cb([[1792549620000,99.04,99.07,99.02,99.06,0.1],[1792549560000,99.00,99.05,98.99,99.04,0.2]]);"


def test_swissquote_mid_and_time():
    assert spot.parse_sq(SQ) == (pytest.approx(100.47), 1792549879.0)


def test_dukascopy_jsonp_newest_first_becomes_oldest_first_rows():
    rows = spot.parse_duka(DUKA)
    assert [r["time"] for r in rows] == [1792549560, 1792549620]
    assert rows[1] == {"time": 1792549620, "open": 99.04, "high": 99.07, "low": 99.02, "close": 99.06, "volume": 0}
    assert spot.parse_duka("Error 500") == []


def test_quote_is_the_live_spot_price_against_yesterdays_close(monkeypatch):
    monkeypatch.setattr(spot, "_live", lambda s: (99.29, 1792549879.0))
    monkeypatch.setattr(spot, "_prev_close", lambda s: 98.36)
    q = spot.quote("CL=F")
    assert q == {"price": 99.29, "prevClose": 98.36, "marketTime": 1792549879, "currency": "USD"}
    assert spot.quote("AAPL") is None                                          # not a commodity


def test_quote_without_history_still_gives_the_price(monkeypatch):
    monkeypatch.setattr(spot, "_live", lambda s: (4117.3, 1792549889.0))
    monkeypatch.setattr(spot, "_prev_close", lambda s: (_ for _ in ()).throw(ConnectionError("dukascopy down")))
    assert spot.quote("GC=F")["prevClose"] == 4117.3


def test_history_pages_back_until_the_range_is_covered(monkeypatch):
    calls = []

    def fake(inst, interval, limit, before_ms):
        calls.append((limit, before_ms))
        end = before_ms // 1000
        return [{"time": end - 60 * k, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0} for k in range(limit)][::-1]
    monkeypatch.setattr(spot, "_duka", fake)
    monkeypatch.setattr(spot, "MAX_BARS", 100)
    rows = spot.history("GC=F", "1m", 250 * 60, now=1_800_000_000)
    assert len(calls) == 3 and calls[0] == (100, 1_800_000_000_000)
    assert [r["time"] for r in rows] == sorted({r["time"] for r in rows})       # ordered, no duplicates
    assert rows[0]["time"] >= 1_800_000_000 - 250 * 60


def test_spot_charts_are_one_instrument_with_their_live_price(monkeypatch):
    monkeypatch.setattr(spot, "history", lambda s, i, sec: [{"time": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}])
    crude = spot.candles("CL=F", "1m", "1D")
    assert crude["feed"] == "spot" and crude["source"] == "dukascopy"
    assert "liveFold" not in crude and "note" not in crude                  # live spot ticks fold onto spot bars
    assert spot.candles("GC=F", "1m", "1M")["interval"] == "5m"                 # 1-min over a month: too many calls


def test_effective_feed():
    assert quotes.effective_feed("CL=F", None) == "spot"
    assert quotes.effective_feed("BZ=F", None) == "spot"                      # Brent spot: Dukascopy
    assert quotes.effective_feed("NG=F", None) == "spot"                      # gas spot: Dukascopy


def test_a_commodity_without_a_spot_feed_uses_the_perpetual(monkeypatch):
    monkeypatch.setattr(spot, "SPOT", {k: v for k, v in spot.SPOT.items() if k != "NG=F"})
    assert quotes.effective_feed("NG=F", None) == "futures"
    assert quotes.effective_feed("CL=F", "futures") == "futures"


def test_routes_default_to_spot_and_fall_back_to_binance(client, monkeypatch):
    monkeypatch.setattr(spot, "candles", lambda s, i, r: {"symbol": s, "candles": [], "source": "dukascopy", "feed": "spot"})
    monkeypatch.setattr(spot, "quote", lambda s: {"price": 100.47, "prevClose": 99.57, "marketTime": 1792549879, "currency": "USD"})
    assert client.get("/api/candles?symbol=CRUDE&interval=1m&range=1D").get_json()["source"] == "dukascopy"
    assert client.get("/api/quote?symbol=CRUDE").get_json()["source"] == "dukascopy"
    assert client.get("/api/quote?symbol=GOLD").get_json()["source"] == "swissquote"
    monkeypatch.setattr(spot, "candles", lambda s, i, r: None)                 # Dukascopy down
    monkeypatch.setattr(commodities, "candles", lambda s, i, r: ("1m", []))
    from orazio import futures
    monkeypatch.setattr(futures, "candles", lambda s, i, r: None)               # Hyperliquid down too
    assert client.get("/api/candles?symbol=CRUDE&interval=1m&range=1D").get_json()["source"] == "binance"


def test_scroll_back_on_a_spot_chart_stays_on_dukascopy(client, monkeypatch):
    monkeypatch.setattr(spot, "older", lambda s, i, before: [{"time": before - 60, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}])
    d = client.get("/api/candles/history?symbol=GOLD&interval=1m&before=1790000000&source=dukascopy").get_json()
    assert d["candles"][0]["time"] == 1_789_999_940 and d["exhausted"] is False


def test_config_lists_the_spot_commodities(client):
    d = client.get("/api/config").get_json()["spotCommodities"]
    assert {"CRUDE", "CL=F", "BRENT", "BZ=F", "GOLD", "GC=F", "SILVER", "SI=F", "NATGAS", "NG=F", "COPPER", "HG=F"} <= set(d)


def test_crude_live_price_is_dukascopys_one_second_bar_not_swissquotes(monkeypatch):
    # Swissquote's OIL/USD ran $1.4 above every other WTI quote; Dukascopy matched TradingView's FX:USOIL.
    seen = []
    monkeypatch.setattr(spot, "_duka", lambda inst, iv, limit, before: seen.append((inst, iv)) or [{"time": 1792549879, "close": 99.29}])
    monkeypatch.setattr(spot.requests, "get", lambda *a, **k: pytest.fail("crude must not ask Swissquote"))
    assert spot._live("CL=F") == (99.29, 1792549879) and seen == [("LIGHT.CMD/USD", "1s")]


def test_wti_and_usoil_mean_crude(client, monkeypatch):
    from orazio.symbols import clean_symbol
    assert clean_symbol("WTI") == clean_symbol("USOIL") == clean_symbol("CRUDE") == "CL=F"
