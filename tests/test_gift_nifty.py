"""GIFT Nifty: turning NSE's once-a-minute readings into a chart we can draw."""
from datetime import datetime

from orazio import gift_nifty
from orazio.constants import IST

PAYLOAD = {"data": {"giftNifty": {
    "lastprice": 22587.5, "daychange": -68, "perchange": -0.3, "contractstraded": 1221,
    "timestmp": "01-Oct-2026 07:59", "expirydate": "27-Oct-2026",
}}}


def ist(text):
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=IST).timestamp())


# ---- parse_reading ---------------------------------------------------------
def test_parse_reading_extracts_price_prev_close_and_ist_timestamp():
    r = gift_nifty.parse_reading(PAYLOAD)
    assert r["price"] == 22587.5
    assert r["prevClose"] == 22587.5 + 68          # prev close = last - day change
    assert r["marketTime"] == ist("2026-10-01 07:59")
    assert r["contracts"] == 1221 and r["expiry"] == "27-Oct-2026"


def test_parse_reading_rejects_unusable_payloads():
    for bad in (None, {}, {"data": {}}, {"data": {"giftNifty": {}}},
                {"data": {"giftNifty": {"lastprice": None, "timestmp": "01-Oct-2026 07:59"}}},
                {"data": {"giftNifty": {"lastprice": 1, "timestmp": "not a date"}}},
                {"data": {"giftNifty": {"lastprice": "abc", "timestmp": "01-Oct-2026 07:59"}}}):
        assert gift_nifty.parse_reading(bad) is None


# ---- fold_reading ----------------------------------------------------------
def test_first_reading_opens_flat_then_next_minute_opens_at_previous_close():
    bars = {}
    t0 = ist("2026-10-01 08:00")
    gift_nifty.fold_reading(bars, t0 + 20, 100.0)
    assert bars[t0] == [100.0, 100.0, 100.0, 100.0]
    gift_nifty.fold_reading(bars, t0 + 60 + 5, 103.0)
    # the new minute opens where the last one closed, so candles join up instead of every one being flat
    assert bars[t0 + 60] == [100.0, 103.0, 100.0, 103.0]


def test_readings_in_the_same_minute_widen_high_low_and_move_the_close():
    bars = {}
    t0 = ist("2026-10-01 08:00")
    for dt, price in ((5, 100.0), (20, 104.0), (40, 98.0), (55, 101.0)):
        gift_nifty.fold_reading(bars, t0 + dt, price)
    assert bars[t0] == [100.0, 104.0, 98.0, 101.0]


# ---- rebucket / rows_for ---------------------------------------------------
def minute_bars(start, closes):
    return {start + i * 60: [c, c, c, c] for i, c in enumerate(closes)}


def test_rebucket_to_five_minutes_merges_ohlc():
    t0 = ist("2026-10-01 08:00")
    bars = {t0 + i * 60: [10 + i, 20 + i, 5 + i, 15 + i] for i in range(5)}
    rows = gift_nifty.rebucket(bars, 300)
    assert len(rows) == 1
    assert rows[0] == {"time": t0, "open": 10, "high": 24, "low": 5, "close": 19, "volume": 0}


def test_rebucket_daily_groups_by_indian_day_not_utc_day():
    # 00:30 IST on 2 Oct is still 1 Oct in UTC; it must NOT be glued to the 1 Oct IST day
    late = ist("2026-10-01 23:50")
    after_midnight = ist("2026-10-02 00:30")
    rows = gift_nifty.rebucket({late: [1, 1, 1, 1], after_midnight: [2, 2, 2, 2]}, 86400)
    assert len(rows) == 2
    assert [r["close"] for r in rows] == [1, 2]
    assert rows[0]["time"] == ist("2026-10-01 00:00")


def test_rows_for_keeps_only_the_requested_window_before_the_newest_bar():
    t0 = ist("2026-09-28 10:00")
    bars = {t0 + d * 86400: [d, d, d, d] for d in range(5)}   # five daily points
    assert len(gift_nifty.rows_for(bars, 60, "1D")) == 1
    assert len(gift_nifty.rows_for(bars, 60, "5D")) == 5
    assert gift_nifty.rows_for({}, 60, "1D") == []


# ---- persistence + chart route ---------------------------------------------
def test_bars_survive_a_restart(isolated_state):
    t0 = ist("2026-10-01 08:00")
    import time
    now = int(time.time())
    with gift_nifty._lock:
        gift_nifty._bars.clear()
        gift_nifty._bars[now - now % 60] = [1.0, 2.0, 0.5, 1.5]
    gift_nifty._save()
    with gift_nifty._lock:
        gift_nifty._bars.clear()
    gift_nifty.load()
    assert gift_nifty._bars[now - now % 60] == [1.0, 2.0, 0.5, 1.5]
    gift_nifty._bars.clear()


def test_load_drops_bars_older_than_retention(isolated_state):
    import json, time
    ancient = int(time.time()) - 30 * 86400
    gift_nifty.STORE.parent.mkdir(parents=True, exist_ok=True)
    gift_nifty.STORE.write_text(json.dumps({str(ancient): [1, 1, 1, 1]}))
    gift_nifty._bars.clear()
    gift_nifty.load()
    assert gift_nifty._bars == {}


def test_poll_skips_a_reading_nse_has_not_refreshed(isolated_state, monkeypatch):
    gift_nifty._bars.clear()
    gift_nifty._last_stamp = None
    reading = gift_nifty.parse_reading(PAYLOAD)
    monkeypatch.setattr(gift_nifty, "quote", lambda: reading)
    gift_nifty._poll_once()
    gift_nifty._poll_once()                       # same NSE timestamp again: nothing new to fold
    assert len(gift_nifty._bars) == 1
    gift_nifty._bars.clear()
    gift_nifty._last_stamp = None
