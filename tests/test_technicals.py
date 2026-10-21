"""Screener technicals: Wilder RSI, SMAs, 50/200 crosses, the once-a-day refresh rule, and never
counting today's bar twice."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from orazio import technicals as tech

# StockCharts' published Wilder RSI example: the first RSI (after 14 changes) is 70.53, then 66.32,
# 66.55, 69.41, 66.36 as each next close arrives. Their sheet rounds the averages (0.24 / 0.10), which
# puts every value ~0.07 above the unrounded maths — hence the 0.1 tolerance.
CLOSES = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28,
          46.28, 46.00, 46.03, 46.41, 46.22]


@pytest.mark.parametrize("upto, expected", [(15, 70.53), (16, 66.32), (17, 66.55), (18, 69.41), (19, 66.36)])
def test_rsi_matches_the_published_wilder_example(upto, expected):
    assert tech.rsi(CLOSES[:upto]) == pytest.approx(expected, abs=0.1)


def test_rsi_needs_more_than_n_closes_and_handles_flat_and_one_way_series():
    assert tech.rsi(CLOSES[:14]) is None
    assert tech.rsi([10.0] * 20) == 50.0
    assert tech.rsi(list(range(20))) == 100.0


def test_sma():
    assert tech.sma([1, 2, 3, 4], 2) == 3.5
    assert tech.sma([1, 2], 3) is None


def test_golden_and_death_cross_within_five_sessions():
    flat = [100.0] * 210
    assert tech.cross_within(flat + [101.0] * 3) == "golden"      # fast average just moved above slow
    assert tech.cross_within(flat + [99.0] * 3) == "death"
    assert tech.cross_within([100.0] * 250) is None
    assert tech.cross_within([100.0] * 100) is None                # not enough history


def test_metrics_append_the_live_price_as_todays_close():
    closes = [100.0] * 210
    m = tech.metrics(closes, 110.0)
    assert m["vsSma200"] == pytest.approx((110 - (100 * 199 + 110) / 200) / ((100 * 199 + 110) / 200) * 100)
    assert m["rsi"] == 100.0
    assert m["cross"] == "golden"


def test_metrics_with_short_history_leave_the_long_averages_empty():
    m = tech.metrics([100.0] * 30, 100.0)
    assert m["vsSma200"] is None and m["vsSma50"] is None and m["rsi"] == 50.0


def _ist(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=tech.IST).astimezone(timezone.utc)


def test_staleness_cutoff_is_the_latest_1545_ist():
    fetched_morning = _ist(2026, 10, 19, 9, 0).timestamp()
    assert not tech.is_stale(fetched_morning, _ist(2026, 10, 19, 15, 0))   # still before today's cutoff
    assert tech.is_stale(fetched_morning, _ist(2026, 10, 19, 16, 0))       # today's close is now settled
    fetched_evening = _ist(2026, 10, 19, 16, 5).timestamp()
    assert not tech.is_stale(fetched_evening, _ist(2026, 10, 20, 11, 0))
    assert tech.is_stale(None, _ist(2026, 10, 20, 11, 0))


def test_bars_on_or_after_the_trade_date_are_dropped():
    bars = [["2026-10-16", 1.0], ["2026-10-17", 2.0], ["2026-10-19", 3.0]]
    assert tech.closes_before(bars, "2026-10-19") == [1.0, 2.0]   # today's partial Yahoo bar goes
    assert tech.closes_before(bars, "2026-10-17") == [1.0]        # weekend: Friday's close isn't doubled


def test_for_symbol_uses_saved_closes_and_live_price(monkeypatch):
    monkeypatch.setattr(tech, "_data", {"fetchedAt": 1, "closes": {"ABC": [[f"2026-01-{i:02d}", 100.0] for i in range(1, 29)]}})
    assert tech.for_symbol("ABC", 100.0, "2026-02-01")["rsi"] == 50.0
    assert tech.for_symbol("NOPE", 100.0, "2026-02-01") is None
    assert tech.for_symbol("ABC", None, "2026-02-01") is None


def test_ensure_fresh_starts_one_background_download_and_reports_status(isolated_state, monkeypatch):
    monkeypatch.setattr(tech, "_data", None)
    monkeypatch.setattr(tech, "_loaded", False)
    monkeypatch.setattr(tech, "_running", False)
    monkeypatch.setattr(tech, "_last_attempt", 0.0)
    started = []
    with patch.object(tech.threading, "Thread") as T:
        T.return_value.start.side_effect = lambda: started.append(1)
        assert tech.ensure_fresh() == "loading"
        assert tech.ensure_fresh() == "loading"     # already running: no second download
    assert len(started) == 1


def test_refresh_saves_and_reloads_closes(isolated_state, monkeypatch):
    data = {"fetchedAt": 123.0, "closes": {"ABC": [["2026-10-16", 10.0]]}}
    monkeypatch.setattr(tech, "_download", lambda: data)
    monkeypatch.setattr(tech, "_running", True)
    tech._refresh()
    assert not tech._running
    monkeypatch.setattr(tech, "_data", None)
    tech._load()
    assert tech._data == data


def test_a_failed_download_keeps_the_old_closes(isolated_state, monkeypatch):
    old = {"fetchedAt": 1.0, "closes": {"ABC": [["2026-10-16", 10.0]]}}
    monkeypatch.setattr(tech, "_data", old)
    monkeypatch.setattr(tech, "_download", lambda: (_ for _ in ()).throw(RuntimeError("rate limited")))
    tech._refresh()
    assert tech._data is old
