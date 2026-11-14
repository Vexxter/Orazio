from orazio.candles import drop_spurious_flat_rows


def _row(o, h, l, c, v):
    return {"time": 0, "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_drops_zero_volume_flat_rows():
    rows = [_row(100, 100, 100, 100, 0)]
    assert drop_spurious_flat_rows(rows) == []


def test_keeps_a_real_quiet_session_with_actual_volume():
    rows = [_row(100, 100, 100, 100, 500)]
    assert drop_spurious_flat_rows(rows) == rows


def test_keeps_rows_with_real_range():
    rows = [_row(100, 105, 99, 103, 0)]
    assert drop_spurious_flat_rows(rows) == rows


def test_resample_weekly_groups_monday_to_sunday_ist():
    from datetime import datetime

    from orazio.candles import resample_weekly
    from orazio.constants import IST
    day = lambda d: int(datetime(2026, 10, d, 9, 15, tzinfo=IST).timestamp())
    daily = [{"time": day(d), "open": d, "high": d + 10, "low": d - 1, "close": d + 1, "volume": 1}
             for d in (12, 13, 16, 19)]   # Mon, Tue, Fri, next Mon
    weeks = resample_weekly(daily)
    assert len(weeks) == 2
    assert weeks[0] == {"time": day(12), "open": 12, "high": 26, "low": 11, "close": 17, "volume": 3}
    assert weeks[1]["time"] == day(19)


def test_old_5d_range_is_served_as_the_7_day_week():
    from orazio.symbols import resolve_interval_range
    assert resolve_interval_range("1m", "5D") == ("1m", "1W")
    assert resolve_interval_range("1wk", "1Y") == ("1wk", "1Y")
