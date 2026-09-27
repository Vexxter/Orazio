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
