"""Live push: Binance websocket ticks, the shared quote builder, and the server-sent-events stream."""
import json

import pytest

from orazio import binance_stream, commodities, quotes
from orazio.routes import stream

MAP = {"XAUUSDT": "GC=F", "CLUSDT": "CL=F"}


@pytest.fixture(autouse=True)
def clean_stream_state():
    binance_stream._last.clear()
    binance_stream.state.update(connected=False, error=None, messages=0)
    yield
    binance_stream._last.clear()


# ---- Binance websocket messages ------------------------------------------------------------
def msg(symbol="XAUUSDT", bid="4167.30", ask="4167.50", ms=1_790_823_773_123, event="bookTicker"):
    return json.dumps({"stream": f"{symbol.lower()}@bookTicker",
                       "data": {"e": event, "s": symbol, "b": bid, "B": "1.5", "a": ask, "A": "2.0", "T": ms, "E": ms}})


def test_a_best_bid_ask_update_becomes_chart_symbol_mid_price_and_event_time():
    assert binance_stream.parse_message(msg(), MAP) == ("GC=F", pytest.approx(4167.4), 1_790_823_773_123)


def test_a_bare_unwrapped_message_is_understood_too():
    raw = json.dumps({"e": "bookTicker", "s": "CLUSDT", "b": "89.60", "a": "89.80", "E": 5})
    assert binance_stream.parse_message(raw, MAP) == ("CL=F", pytest.approx(89.7), 5)


@pytest.mark.parametrize("raw", [
    msg(event="aggTrade"),                 # the stream type that is empty for these contracts: not what we subscribe to
    msg(symbol="BTCUSDT"),                 # a symbol we don't follow
    msg(bid="4167.50", ask="4167.30"),     # crossed book: not a price
    msg(bid="0", ask="0"),                 # empty book
    "not json at all",
    json.dumps({"data": {"e": "bookTicker", "s": "XAUUSDT"}}),    # prices missing
    json.dumps({"data": {"e": "bookTicker", "s": "XAUUSDT", "b": "abc", "a": "1", "T": 1}}),
    json.dumps(None), "[]",
])
def test_anything_else_is_ignored_rather_than_raised(raw):
    assert binance_stream.parse_message(raw, MAP) is None


# ---- freshness --------------------------------------------------------------------------------
def test_a_recent_price_is_live_and_an_old_one_is_not():
    binance_stream.record("GC=F", 4167.4, 1_790_823_773_123, received=1000.0)
    assert binance_stream.latest("GC=F", now=1003.0)["price"] == 4167.4
    assert binance_stream.latest("GC=F", now=1000.0 + binance_stream.FRESH_SEC + 1) is None      # stale: callers use REST
    assert binance_stream.latest("CL=F", now=1001.0) is None                                     # never seen
    assert binance_stream.state["messages"] == 1


def test_is_streaming_reflects_freshness():
    assert not binance_stream.is_streaming("GC=F")
    binance_stream.record("GC=F", 1.0, 1)
    assert binance_stream.is_streaming("GC=F")


def test_reconnect_backoff_doubles_to_a_ceiling():
    steps, b = [], 1
    for _ in range(8):
        b = binance_stream.next_backoff(b)
        steps.append(b)
    assert steps == [2, 4, 8, 16, 30, 30, 30, 30]


# ---- overlaying the live trade on the REST quote -----------------------------------------------------
REST = {"price": 4160.0, "prevClose": 4188.5, "marketTime": 1_790_823_700, "currency": "USD"}


def test_a_newer_websocket_price_replaces_rests_price_and_time_but_keeps_its_prev_close():
    q = commodities.with_live_trade(REST, {"price": 4167.4, "time": 1_790_823_773_123})
    assert q == {"price": 4167.4, "prevClose": 4188.5, "marketTime": 1_790_823_773, "currency": "USD"}


def test_an_older_price_or_none_leaves_the_rest_quote_alone():
    assert commodities.with_live_trade(REST, {"price": 1.0, "time": 1_790_823_000_000}) is REST
    assert commodities.with_live_trade(REST, None) is REST


def test_commodity_quote_uses_the_websocket_price_when_it_is_fresh(monkeypatch):
    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"lastPrice": "4160.0", "priceChange": "-28.5", "closeTime": 1_790_823_700_000}
    monkeypatch.setattr(commodities.requests, "get", lambda *a, **k: R())
    binance_stream.record("GC=F", 4167.4, 1_790_823_773_123)
    q = commodities.quote("GC=F")
    assert q["price"] == 4167.4 and q["prevClose"] == pytest.approx(4188.5)


# ---- the shared quote builder -----------------------------------------------------------------------------
def test_quote_payload_has_the_shape_the_page_and_the_stream_share(monkeypatch):
    monkeypatch.setattr(quotes, "pick_quote", lambda s, f=None: ("yahoo", {"price": 110.0, "prevClose": 100.0, "marketTime": 1_790_000_000, "currency": "USD"}))
    p = quotes.quote_payload("AAPL", now=1_790_000_005)
    assert p == {"symbol": "AAPL", "price": 110.0, "time": 1_790_000_005, "marketTime": 1_790_000_000, "delaySec": 5,
                 "change": 10.0, "changePercent": pytest.approx(10.0), "currency": "USD", "source": "yahoo"}


def test_quote_payload_is_none_when_no_source_has_a_quote(monkeypatch):
    monkeypatch.setattr(quotes, "pick_quote", lambda s, f=None: ("yahoo", None))
    assert quotes.quote_payload("AAPL") is None


def test_only_in_memory_push_feeds_are_re_read_several_times_a_second():
    assert quotes.is_pushed("^BSESN") is True and quotes.is_pushed("AAPL") is False
    binance_stream.record("GC=F", 1.0, 1)
    assert quotes.is_pushed("GC=F") is True


# ---- server-sent events ------------------------------------------------------------------------------------------
def test_an_event_frame_is_compact_json_between_blank_lines():
    assert stream.sse("quote", {"price": 1.5, "a": [1, 2]}) == 'event: quote\ndata: {"price":1.5,"a":[1,2]}\n\n'


class Clock:
    """A fake clock whose sleep() advances time, so the generator can be driven without waiting."""
    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


def run_events(prices, pushed=False, steps=None, keep=None):
    """Drive quote_events over a scripted series of build() results; returns (frames, clock)."""
    clock, it = Clock(), iter(prices)
    steps = steps if steps is not None else len(prices)
    count = {"n": 0}

    def build(symbol):
        count["n"] += 1
        value = next(it)
        if isinstance(value, Exception):
            raise value
        return value

    frames = list(stream.quote_events("X", build=build, pushed=lambda s: pushed, sleep=clock.sleep, clock=clock.now,
                                      keep_going=lambda: count["n"] < steps))
    return frames, clock


def q(price, mt=1):
    return {"price": price, "marketTime": mt}


def test_a_quote_event_is_sent_for_every_change_and_not_for_repeats():
    frames, _ = run_events([q(1.0), q(1.0), q(2.0), q(2.0), q(2.0, mt=9)])
    prices = [json.loads(f.split("data: ")[1])["price"] for f in frames if f.startswith("event: quote")]
    assert prices == [1.0, 2.0, 2.0]                          # the last one only because marketTime moved


def test_a_failing_source_neither_ends_the_stream_nor_emits_garbage():
    frames, _ = run_events([RuntimeError("NSE down"), None, q(1.0)])
    assert len(frames) == 1 and frames[0].startswith("event: quote")


def test_a_ping_is_sent_while_nothing_changes_so_the_page_can_tell_idle_from_dead():
    frames, clock = run_events([q(1.0)] * 40)                 # 40 s of an unchanging quote at 1 s ticks
    pings = [f for f in frames if f.startswith("event: ping")]
    assert len(pings) >= 2 and clock.t >= 39


def test_pushed_sources_are_re_read_four_times_a_second_and_network_ones_once():
    _frames, fast = run_events([q(1.0)] * 3, pushed=True)
    _frames, slow = run_events([q(1.0)] * 3, pushed=False)
    assert set(fast.sleeps) == {stream.PUSHED_TICK_SEC} and set(slow.sleeps) == {stream.POLLED_TICK_SEC}


def test_the_stream_stops_when_asked_to():
    frames, _ = run_events([q(1.0), q(2.0)], steps=1)
    assert len(frames) == 1


def test_the_route_streams_text_event_stream_with_no_buffering(client, monkeypatch):
    monkeypatch.setattr(stream, "quote_events", lambda symbol, feed=None: iter([stream.sse("quote", {"symbol": symbol, "price": 1.0})]))
    resp = client.get("/api/stream/quote?symbol=GOLD")
    assert resp.mimetype == "text/event-stream"
    assert resp.headers["Cache-Control"] == "no-cache" and resp.headers["X-Accel-Buffering"] == "no"
    assert resp.get_data(as_text=True).startswith("event: quote\ndata: ")
    assert '"symbol":"GC=F"' in resp.get_data(as_text=True)          # the alias was resolved before streaming


def test_the_stream_rejects_an_unsafe_symbol(client):
    assert client.get("/api/stream/quote?symbol=../../etc").status_code == 400


# ---- commodity source switch: Binance (default) or Yahoo's delayed CME futures --------------------------------------
YAHOO_Q = {"price": 4194.0, "prevClose": 4188.5, "marketTime": 1_790_823_100, "currency": "USD"}
BINANCE_Q = {"price": 4168.7, "prevClose": 4188.5, "marketTime": 1_790_823_700, "currency": "USD"}


@pytest.fixture
def both_sources(monkeypatch):
    monkeypatch.setattr(commodities, "quote", lambda s: BINANCE_Q)
    monkeypatch.setattr(quotes.market_data, "yahoo_live_quote", lambda s: YAHOO_Q)


def test_a_commodity_uses_binance_by_default_and_yahoo_cme_when_asked(both_sources):
    assert quotes.pick_quote("GC=F") == ("binance", BINANCE_Q)
    assert quotes.pick_quote("GC=F", "binance") == ("binance", BINANCE_Q)
    assert quotes.pick_quote("GC=F", "yahoo") == ("yahoo-cme", YAHOO_Q)


def test_the_feed_choice_changes_nothing_for_other_symbols(monkeypatch):
    monkeypatch.setattr(quotes.market_data, "yahoo_live_quote", lambda s: YAHOO_Q)
    assert quotes.pick_quote("AAPL", "yahoo") == quotes.pick_quote("AAPL") == ("yahoo", YAHOO_Q)


def test_an_unknown_feed_value_means_the_default():
    assert quotes.clean_feed("yahoo") == "yahoo" and quotes.clean_feed("binance") == "binance"
    assert quotes.clean_feed("bogus") is None and quotes.clean_feed(None) is None


def test_the_yahoo_feed_is_never_treated_as_a_push_feed():
    binance_stream.record("GC=F", 1.0, 1)
    assert quotes.is_pushed("GC=F") is True
    assert quotes.is_pushed("GC=F", "yahoo") is False


def test_quote_api_honours_the_feed_parameter(client, both_sources):
    assert client.get("/api/quote?symbol=GOLD").get_json()["source"] == "binance"
    d = client.get("/api/quote?symbol=GOLD&feed=yahoo").get_json()
    assert d["source"] == "yahoo-cme" and d["price"] == 4194.0


def test_candles_api_serves_yahoo_bars_for_the_yahoo_feed_and_marks_both(client, monkeypatch):
    from orazio.routes import charts
    monkeypatch.setattr(commodities, "candles", lambda s, i, r: ("1m", [{"time": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}]))
    monkeypatch.setattr(charts, "_yahoo_candles", lambda s, i, r, feed=None: charts.jsonify({"symbol": s, "candles": [], "feedChoice": True, "feed": "yahoo"}))
    b = client.get("/api/candles?symbol=GOLD&interval=1m&range=1D").get_json()
    assert b["source"] == "binance" and b["feedChoice"] is True and b["feed"] == "binance"
    y = client.get("/api/candles?symbol=GOLD&interval=1m&range=1D&feed=yahoo").get_json()
    assert y["feed"] == "yahoo" and "source" not in y


def test_config_lists_the_commodities_that_have_a_source_switch(client):
    d = client.get("/api/config").get_json()["commodities"]
    assert {"GOLD", "GC=F", "CRUDE", "CL=F"} <= set(d) and "BTC" not in d and "NIFTY" not in d
