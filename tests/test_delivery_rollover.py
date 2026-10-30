"""Delivery % against a stock's own average, and futures rollover lined up by sessions before expiry."""
from orazio import delivery, rollover

BHAV = """SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER
AAA, EQ, 29-Oct-2026, 100, 100, 110, 99, 109, 110, 105, 1000, 1000.00, 10, 600, 60.00
AAA, BE, 29-Oct-2026, 100, 100, 110, 99, 109, 110, 105, 5, 1.00, 1, 5, 100.00
BBB, EQ, 29-Oct-2026, 50, 50, 50, 50, 50, 50, 50, 10, 0.05, 1, -, -
"""


def test_bhav_keeps_eq_series_and_tolerates_missing_delivery():
    rows = delivery.parse_bhav(BHAV)
    assert rows["AAA"] == [110.0, 100.0, 1000, 600, 10.0]
    assert rows["BBB"][3] == 0
    assert delivery.parse_bhav("<html>") is None


def test_rank_compares_with_own_average_and_drops_illiquid():
    days = [("d1", {"AAA": [100, 100, 1000, 200, 10.0]}), ("d2", {"AAA": [100, 100, 1000, 400, 10.0]}),
            ("d3", {"AAA": [110, 100, 1000, 900, 10.0], "TINY": [1, 1, 10, 10, 0.1]})]
    [row] = delivery.rank(days)
    assert row["symbol"] == "AAA" and row["delivPct"] == 90.0 and row["avgDelivPct"] == 30.0
    assert row["delivX"] == 3.0 and row["pChange"] == 10.0


def test_day_stats_rollover_and_spread():
    rows = [["NIFTY", "2026-10-27", 0, 0, 0, 100.0, 20, 0], ["NIFTY", "2026-11-23", 0, 0, 0, 101.0, 70, 0],
            ["NIFTY", "2026-12-29", 0, 0, 0, 102.0, 10, 0]]
    s = rollover.day_stats(rows, "2026-10-27")["NIFTY"]
    assert s["near"] == "2026-10-27" and s["rollPct"] == 80.0 and s["spreadPct"] == 1.0
    assert "NIFTY" in rollover.day_stats(rows, "2026-10-28")          # Oct expiry gone: Nov is near now


def test_previous_series_point_by_sessions_left():
    assert rollover.sessions_left("2026-10-29", "2026-11-03") == 3      # Fri, Mon, Tue
    prev = [{"rollPct": v} for v in (5, 10, 40, 80)]                     # last = expiry day
    assert rollover.same_point(prev, 0)["rollPct"] == 80
    assert rollover.same_point(prev, 2)["rollPct"] == 10
    assert rollover.same_point(prev, 9) is None
