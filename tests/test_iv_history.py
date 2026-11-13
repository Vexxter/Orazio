"""IV30 interpolation, the local IV history store, and IV rank / percentile."""
from datetime import datetime

from orazio import iv_history
from orazio.constants import IST


def test_iv30_interpolates_between_the_expiries_around_30_days():
    term = [{"days": 7, "atmIv": 12.0}, {"days": 21, "atmIv": 13.0}, {"days": 49, "atmIv": 15.0}, {"days": 80, "atmIv": None}]
    assert iv30(term) == 13.64                                        # 13 + 2 * 9/28
    assert iv30([{"days": 40, "atmIv": 14.0}, {"days": 70, "atmIv": 16.0}]) == 14.0   # all beyond 30: nearest
    assert iv30([{"days": 3, "atmIv": 11.0}, {"days": 10, "atmIv": 12.0}]) == 12.0
    assert iv30([]) is None


def iv30(term):
    return iv_history.iv30(term)


def test_stats_rank_and_percentile_need_twenty_days():
    assert iv_history.stats([15.0] * 19, 15.0)["rank"] is None
    vals = [10.0 + i for i in range(21)]                              # 10 .. 30
    s = iv_history.stats(vals, 15.0)
    assert (s["rank"], s["percentile"], s["low"], s["high"], s["days"]) == (25.0, 23.8, 10.0, 30.0, 21)   # 5 of 21 below
    assert iv_history.stats([12.0] * 25, 12.0)["rank"] == 50.0        # flat history: middle, not a divide by zero


def test_summary_records_one_reading_per_day_and_trims_old_days(monkeypatch):
    monkeypatch.setattr(iv_history, "KEEP_DAYS", 3)
    term = lambda v: [{"days": 30, "atmIv": v}]
    for day, v in [(1, 11.0), (2, 12.0), (2, 12.5), (3, 13.0), (4, 14.0)]:
        out = iv_history.summary("NIFTY", term(v), datetime(2026, 11, day, 12, 0, tzinfo=IST))
    assert [h["date"] for h in out["history"]] == ["2026-11-02", "2026-11-03", "2026-11-04"]
    assert out["history"][0]["iv"] == 12.5 and out["iv30"] == 14.0 and out["days"] == 3


def test_market_hours():
    assert iv_history.market_open(datetime(2026, 11, 13, 10, 0))
    assert not iv_history.market_open(datetime(2026, 11, 14, 10, 0))   # Saturday
    assert not iv_history.market_open(datetime(2026, 11, 13, 16, 0))
