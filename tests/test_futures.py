"""The Futures feed: Hyperliquid's oracle for oil, gas and copper (most accurate, measured), Binance for gold and
silver, and the fallbacks between them."""
import pytest

from orazio import commodities, futures, quotes

CTX = {"oraclePx": "99.33", "markPx": "99.296", "prevDayPx": "98.56", "midPx": "99.306"}
RAW = [{"t": 1792549560000, "T": 1792549619999, "s": "xyz:CL", "i": "1m", "o": "99.20", "c": "99.30", "h": "99.31",
        "l": "99.18", "v": "120.5", "n": 40}]
BINANCE_Q = {"price": 4128.0, "prevClose": 4100.0, "marketTime": 1792549000, "currency": "USD"}


def test_the_live_price_is_the_oracle_against_the_price_24h_ago():
    assert futures.parse_ctx(CTX, 1792549879.4) == {"price": 99.33, "prevClose": 98.56, "marketTime": 1792549879, "currency": "USD"}


def test_candles_become_chart_rows():
    assert futures.parse_candles(RAW) == [{"time": 1792549560, "open": 99.2, "high": 99.31, "low": 99.18, "close": 99.3, "volume": 120.5}]


def test_oil_gas_copper_are_hyperliquid_gold_silver_are_not():
    assert all(futures.is_hl(s) for s in ("CL=F", "BZ=F", "NG=F", "HG=F"))
    assert not futures.is_hl("GC=F") and not futures.is_hl("SI=F")


def test_quote_picks_the_market_and_survives_an_outage(monkeypatch):
    monkeypatch.setattr(futures, "_contexts", lambda: {"xyz:CL": CTX})
    assert futures.quote("CL=F")["price"] == 99.33
    assert futures.quote("BZ=F") is None                                   # market missing from the reply
    assert futures.quote("GC=F") is None                                   # not a Hyperliquid symbol
    from orazio import cache
    cache._store.clear()
    monkeypatch.setattr(futures, "_contexts", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    assert futures.quote("CL=F") is None


def test_history_pages_forward_until_the_end(monkeypatch):
    calls = []

    def fake(body):
        calls.append(body["req"]["startTime"])
        start = body["req"]["startTime"] // 1000
        n = 3 if len(calls) < 2 else 1
        return [{"t": (start + 60 * k) * 1000, "o": 1, "c": 1, "h": 1, "l": 1, "v": 0} for k in range(n)]
    monkeypatch.setattr(futures, "_post", fake)
    monkeypatch.setattr(futures, "PAGE", 3)
    rows = futures.history("CL=F", "1m", 1_800_000_000, 1_800_000_000 + 3600)
    assert len(calls) == 2 and [r["time"] for r in rows] == sorted({r["time"] for r in rows}) and len(rows) == 4


def test_long_ranges_are_left_to_the_cme_fallback(monkeypatch):
    monkeypatch.setattr(futures, "history", lambda *a: [{"time": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}])
    assert futures.candles("CL=F", "1d", "5Y") is None and futures.candles("CL=F", "1d", "ALL") is None
    d = futures.candles("CL=F", "1m", "1D")
    assert d["source"] == "hyperliquid" and d["feed"] == "futures"
    assert futures.candles("CL=F", "1h", "6M")["interval"] == "1h"
    assert futures.candles("GC=F", "1m", "1D") is None


def test_futures_quote_mix_and_fallbacks(monkeypatch):
    monkeypatch.setattr(futures, "quote", lambda s: {"price": 99.33, "prevClose": 98.56, "marketTime": 1, "currency": "USD"} if s == "CL=F" else None)
    monkeypatch.setattr(commodities, "quote", lambda s: BINANCE_Q)
    assert quotes.pick_quote("CL=F", "futures")[0] == "hyperliquid"
    assert quotes.pick_quote("GC=F", "futures") == ("binance", BINANCE_Q)
    assert quotes.pick_quote("BZ=F", "futures") == ("binance", BINANCE_Q)  # Hyperliquid has no answer: Binance


def test_routes_serve_hyperliquid_for_oil_and_binance_for_gold(client, monkeypatch):
    monkeypatch.setattr(futures, "candles", lambda s, i, r: {"symbol": s, "candles": [], "source": "hyperliquid", "feed": "futures"} if futures.is_hl(s) else None)
    monkeypatch.setattr(commodities, "candles", lambda s, i, r: ("1m", []))
    assert client.get("/api/candles?symbol=CRUDE&interval=1m&range=1D&feed=futures").get_json()["source"] == "hyperliquid"
    assert client.get("/api/candles?symbol=GOLD&interval=1m&range=1D&feed=futures").get_json()["source"] == "binance"
    assert client.get("/api/candles?symbol=CRUDE&interval=1m&range=1D&feed=binance").get_json()["source"] == "hyperliquid"   # old name


def test_scroll_back_on_a_hyperliquid_chart(client, monkeypatch):
    monkeypatch.setattr(futures, "older", lambda s, i, before: [{"time": before - 60, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}])
    d = client.get("/api/candles/history?symbol=CRUDE&interval=1m&before=1790000000&source=hyperliquid").get_json()
    assert d["candles"][0]["time"] == 1_789_999_940


def test_binance_websocket_only_streams_gold_and_silver(monkeypatch):
    from orazio import binance_stream, poller
    started = {}
    monkeypatch.setattr(binance_stream, "start", lambda syms: started.update(syms))
    for name in ("bse_stream",):
        monkeypatch.setattr(poller.market_data, name, type("S", (), {"start": staticmethod(lambda: None)}))
    for fn in ("start_live_bar_poller",):
        monkeypatch.setattr(poller.market_data, fn, lambda: None)
    for mod, fn in ((poller.cas, "start_seed_loop"), (poller.cas, "ensure_nse_poller"), (poller.constituents, "start_constituent_poller"),
                    (poller.live_volume, "start"), (poller.gift_nifty, "start"), (poller.market_breadth, "start"),
                    (poller.exports, "start_scheduler"), (poller.gsec, "start"), (poller.cas_rebuild, "start")):
        monkeypatch.setattr(mod, fn, lambda *a, **k: None)
    monkeypatch.setattr(poller, "_started", False)
    poller.ensure_poller()
    assert set(started) == {"GC=F", "SI=F"}
