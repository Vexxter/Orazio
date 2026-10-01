"""Commodities: real-time Binance perpetuals for the live price and intraday charts, Yahoo's CME
history for everything longer, and a clean fallback to Yahoo when Binance is unreachable."""
import pandas as pd
import pytest

from orazio import commodities, market_data
from orazio.constants import QUICK_INDICES, SYMBOL_ALIASES

KLINES = [  # [open time ms, open, high, low, close, volume, ...]
    [1_790_000_000_000, "100.0", "101.0", "99.5", "100.5", "12.5", 0],
    [1_790_000_060_000, "100.5", "102.0", "100.0", "101.5", "7.0", 0],
    [1_790_000_120_000, "101.5", "101.8", "101.0", "101.2", "0", 0],
]


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise commodities.requests.RequestException(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


# ---- which bar sizes Binance should serve --------------------------------------------------
@pytest.mark.parametrize("requested,rng,expected", [
    ("1m", "1D", "1m"),      # 1440 bars: fits one request
    ("1m", "5D", "5m"),      # 7200 one-minute bars would not fit: step up to 5m (1440)
    ("1m", "1M", "1h"),      # 5m = 8928, 15m = 2976 — only 1h (744) fits
    ("5m", "1M", "1h"),
    ("1h", "1M", "1h"),
    ("15m", "5D", "15m"),
    ("1m", "3M", None),      # long ranges stay on Yahoo's multi-year CME history
    ("1d", "1D", None),      # daily bars: Binance only has ~10 months, Yahoo has decades
    ("2m", "1D", None),
    ("1m", "ALL", None),
])
def test_pick_interval_serves_intraday_and_steps_up_to_fit_one_request(requested, rng, expected):
    assert commodities.pick_interval(requested, rng) == expected


# ---- parsing --------------------------------------------------------------------------------
def test_klines_become_chart_rows_with_epoch_seconds_and_float_prices():
    rows = commodities.parse_klines(KLINES)
    assert rows[0] == {"time": 1_790_000_000, "open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5, "volume": 12.5}
    assert [r["time"] for r in rows] == [1_790_000_000, 1_790_000_060, 1_790_000_120]


def test_ticker_gives_price_a_24h_previous_close_and_the_trade_time():
    q = commodities.parse_ticker({"lastPrice": "4167.40", "priceChange": "-21.10", "closeTime": 1_790_823_773_123})
    assert q["price"] == 4167.4 and q["prevClose"] == pytest.approx(4188.5)
    assert q["marketTime"] == 1_790_823_773 and q["currency"] == "USD"


# ---- live quote --------------------------------------------------------------------------------
def test_quote_asks_binance_for_the_mapped_perpetual(monkeypatch):
    seen = {}
    monkeypatch.setattr(commodities.requests, "get", lambda url, params=None, **k: seen.update(url=url, params=params) or FakeResponse(
        {"lastPrice": "4167.4", "priceChange": "1.0", "closeTime": 1_790_823_773_000}))
    q = commodities.quote("GC=F")
    assert q["price"] == 4167.4 and seen["params"] == {"symbol": "XAUUSDT"} and seen["url"].endswith("/ticker/24hr")


def test_quote_is_none_when_binance_is_down_or_blocked_so_the_caller_can_fall_back(monkeypatch):
    monkeypatch.setattr(commodities.requests, "get", lambda *a, **k: FakeResponse(status=451))   # Binance geo-blocks some regions
    assert commodities.quote("GC=F") is None
    commodities.cached.__globals__["_store"].clear()
    monkeypatch.setattr(commodities.requests, "get", lambda *a, **k: (_ for _ in ()).throw(commodities.requests.RequestException("down")))
    assert commodities.quote("GC=F") is None
    commodities.cached.__globals__["_store"].clear()
    monkeypatch.setattr(commodities.requests, "get", lambda *a, **k: FakeResponse({"unexpected": "shape"}))
    assert commodities.quote("GC=F") is None


def test_quote_ignores_symbols_binance_does_not_list():
    assert commodities.quote("AAPL") is None and commodities.is_commodity("CL=F") and not commodities.is_commodity("AAPL")


def test_quotes_are_cached_for_a_moment_so_polling_does_not_hammer_binance(monkeypatch):
    calls = []
    monkeypatch.setattr(commodities.requests, "get", lambda *a, **k: calls.append(1) or FakeResponse(
        {"lastPrice": "1", "priceChange": "0", "closeTime": 1000}))
    commodities.quote("CL=F")
    commodities.quote("CL=F")
    assert len(calls) == 1


# ---- candles + scroll-back --------------------------------------------------------------------
def test_candles_use_the_stepped_up_interval_and_only_keep_the_requested_window(monkeypatch):
    asked = {}
    monkeypatch.setattr(commodities.requests, "get", lambda url, params=None, **k: asked.update(params=params) or FakeResponse(KLINES))
    served = commodities.candles("GC=F", "1m", "1D")
    assert served[0] == "1m" and len(served[1]) == 3
    assert asked["params"]["symbol"] == "XAUUSDT" and asked["params"]["limit"] == 1500


def test_candles_drop_bars_older_than_the_range_window(monkeypatch):
    old = [[1_790_000_000_000 - 3 * 86400 * 1000, "1", "1", "1", "1", "1", 0]] + KLINES      # one bar 3 days older than the rest
    monkeypatch.setattr(commodities.requests, "get", lambda *a, **k: FakeResponse(old))
    _interval, rows = commodities.candles("GC=F", "1m", "1D")
    assert len(rows) == 3 and rows[0]["time"] == 1_790_000_000


def test_candles_are_none_when_binance_should_not_or_cannot_serve(monkeypatch):
    monkeypatch.setattr(commodities.requests, "get", lambda *a, **k: pytest.fail("a long range must not touch Binance"))
    assert commodities.candles("GC=F", "1m", "3M") is None
    assert commodities.candles("AAPL", "1m", "1D") is None
    monkeypatch.setattr(commodities.requests, "get", lambda *a, **k: FakeResponse(status=500))
    assert commodities.candles("GC=F", "1m", "1D") is None


def test_history_returns_only_bars_older_than_before_and_asks_binance_for_exactly_that_window(monkeypatch):
    asked = {}
    monkeypatch.setattr(commodities.requests, "get", lambda url, params=None, **k: asked.update(params=params) or FakeResponse(KLINES))
    rows = commodities.history("GC=F", "1m", before=1_790_000_060)
    assert [r["time"] for r in rows] == [1_790_000_000]                     # strictly older
    assert asked["params"]["endTime"] == 1_790_000_060 * 1000 - 1
    assert commodities.history("AAPL", "1m", 1) == [] and commodities.history("GC=F", "1d", 1) == []


# ---- the rail and the mapping must agree -----------------------------------------------------------
def test_every_commodity_in_the_rail_has_a_binance_perpetual():
    rail_commodities = [alias for _label, alias in QUICK_INDICES if alias in ("CRUDE", "BRENT", "GOLD", "SILVER", "NATGAS", "COPPER")]
    assert len(rail_commodities) == 6
    for alias in rail_commodities:
        assert SYMBOL_ALIASES[alias] in commodities.SYMBOLS, f"{alias} ({SYMBOL_ALIASES[alias]}) has no Binance mapping"


# ---- routes -----------------------------------------------------------------------------------------
def get_json(client, url, status=200):
    resp = client.get(url)
    assert resp.status_code == status, f"{url} -> {resp.status_code}: {resp.get_data(as_text=True)[:200]}"
    return resp.get_json()


def test_gold_quote_comes_from_binance_when_it_is_up(client, monkeypatch):
    monkeypatch.setattr(commodities, "quote", lambda s: {"price": 4167.4, "prevClose": 4188.5, "marketTime": 1_790_823_773, "currency": "USD"})
    monkeypatch.setattr(market_data, "yahoo_live_quote", lambda s: pytest.fail("Yahoo's delayed CME feed must not be consulted"))
    d = get_json(client, "/api/quote?symbol=GOLD")
    assert d["source"] == "binance" and d["price"] == 4167.4 and d["change"] == pytest.approx(-21.1)


def test_gold_quote_falls_back_to_yahoo_when_binance_is_unreachable(client, monkeypatch):
    monkeypatch.setattr(commodities, "quote", lambda s: None)
    monkeypatch.setattr(market_data, "yahoo_live_quote", lambda s: {"price": 4188.3, "prevClose": 4170.0, "marketTime": 1_790_823_000, "currency": "USD"})
    d = get_json(client, "/api/quote?symbol=GOLD")
    assert d["source"] == "yahoo" and d["price"] == 4188.3


def test_intraday_commodity_charts_are_real_time_binance_bars(client, monkeypatch):
    rows = [{"time": 1, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 3.0}]
    monkeypatch.setattr(commodities, "candles", lambda s, i, r: ("5m", rows))
    d = get_json(client, "/api/candles?symbol=CRUDE&interval=1m&range=5D")
    assert d["source"] == "binance" and d["interval"] == "5m" and d["candles"] == rows
    assert "liveFold" not in d                                              # same instrument as the quote: fold ticks as usual


def frame():
    idx = pd.to_datetime(["2026-09-30 09:15", "2026-09-30 09:16"]).tz_localize("America/New_York")
    return pd.DataFrame({"Open": [1.0, 2.0], "High": [2.0, 3.0], "Low": [0.5, 1.5], "Close": [1.5, 2.5], "Volume": [100, 200]}, index=idx)


def test_long_ranges_stay_on_yahoos_cme_history_and_tell_the_page_not_to_fold_live_ticks(client, monkeypatch):
    import yfinance
    monkeypatch.setattr(commodities, "candles", lambda s, i, r: None)       # Binance declines (long range)
    monkeypatch.setattr(yfinance, "download", lambda *a, **k: frame())
    d = get_json(client, "/api/candles?symbol=GOLD&interval=1d&range=1Y")
    assert d["liveFold"] is False and "source" not in d and len(d["candles"]) == 2


def test_non_commodity_charts_never_carry_the_fold_flag(client, monkeypatch):
    import yfinance
    monkeypatch.setattr(yfinance, "download", lambda *a, **k: frame())
    assert "liveFold" not in get_json(client, "/api/candles?symbol=AAPL&interval=1d&range=1Y")


def test_scroll_back_stays_on_binance_when_the_chart_on_screen_is_binances(client, monkeypatch):
    monkeypatch.setattr(commodities, "history", lambda s, i, before: [{"time": before - 60, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}])
    d = get_json(client, "/api/candles/history?symbol=GOLD&interval=1m&before=1790000000&source=binance")
    assert d["candles"][0]["time"] == 1_789_999_940 and d["exhausted"] is False
    monkeypatch.setattr(commodities, "history", lambda s, i, before: [])
    assert get_json(client, "/api/candles/history?symbol=GOLD&interval=1m&before=1790000000&source=binance")["exhausted"] is True
