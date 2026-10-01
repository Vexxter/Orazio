"""Download dialog + end-of-day export: validation, file contents, and the schedule."""
import io
import zipfile
from datetime import datetime, timedelta

import pandas as pd
import pytest

from orazio import exports
from orazio.constants import IST

TODAY = datetime.now(IST).date()


# ---- build_window: what the dialog is allowed to ask for -----------------------
def test_one_day_window_is_end_exclusive_so_yahoo_returns_exactly_that_day():
    w = exports.build_window("5m", "day", day=TODAY.isoformat())
    assert w["start"] == TODAY.isoformat() and w["end"] == (TODAY + timedelta(days=1)).isoformat()
    assert w["label"] == TODAY.isoformat()


def test_range_window_labels_both_ends():
    a, b = TODAY - timedelta(days=3), TODAY - timedelta(days=1)
    w = exports.build_window("1h", "range", date_from=a.isoformat(), date_to=b.isoformat())
    assert w["label"] == f"{a}_to_{b}"


def test_all_mode_needs_no_dates():
    assert exports.build_window("1d", "all") == {"mode": "all", "label": "all"}


def test_intraday_windows_are_limited_to_what_yahoo_still_serves():
    too_old = (TODAY - timedelta(days=30)).isoformat()
    with pytest.raises(ValueError, match="only go back 7 days"):
        exports.build_window("1m", "day", day=too_old)
    exports.build_window("5m", "day", day=too_old)               # 5m reaches back 60 days: fine
    exports.build_window("1d", "day", day="2010-01-04")         # daily has full history


def test_the_earliest_allowed_day_is_inclusive_and_matches_the_dialog_hint():
    assert exports.earliest_date("1m") == TODAY - timedelta(days=6)         # 7 days including today
    exports.build_window("1m", "day", day=exports.earliest_date("1m").isoformat())
    assert exports.earliest_date("1d") is None


@pytest.mark.parametrize("kwargs,message", [
    (dict(interval="1m", mode="day", day="not-a-date"), "dates must look like"),
    (dict(interval="1m", mode="day", day=(TODAY + timedelta(days=2)).isoformat()), "future"),
    (dict(interval="1m", mode="range", date_from=TODAY.isoformat(), date_to=(TODAY - timedelta(days=1)).isoformat()), "after the end"),
    (dict(interval="2m", mode="day", day=TODAY.isoformat()), "unknown bar size"),
    (dict(interval="1m", mode="weekly"), "unknown range mode"),
])
def test_invalid_requests_are_rejected_with_a_readable_message(kwargs, message):
    with pytest.raises(ValueError, match=message):
        exports.build_window(**kwargs)


# ---- file contents ---------------------------------------------------------------
ROWS = [{"time": 1790653500, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0},
        {"time": 1790653560, "open": 1.5, "high": 1.6, "low": 1.4, "close": 1.55, "volume": 0.0}]


def test_rows_frame_has_symbol_ist_time_and_epoch_columns():
    df = exports.rows_frame("^NSEI", ROWS)
    assert list(df.columns) == ["symbol", "datetime_ist", "timestamp", "open", "high", "low", "close", "volume"]
    assert df.loc[0, "datetime_ist"] == "2026-09-29T09:15:00+05:30"
    assert df.loc[0, "symbol"] == "^NSEI" and df.loc[1, "timestamp"] == 1790653560


def test_empty_rows_still_give_a_well_formed_frame():
    assert list(exports.rows_frame("X", []).columns)[0] == "symbol"


def test_csv_and_parquet_round_trip():
    df = exports.rows_frame("^NSEI", ROWS)
    back_csv = pd.read_csv(io.BytesIO(exports.encode(df, "csv")))
    assert back_csv["close"].tolist() == [1.5, 1.55]
    back_pq = pd.read_parquet(io.BytesIO(exports.encode(df, "parquet")))
    assert back_pq["volume"].tolist() == [10.0, 0.0]
    with pytest.raises(ValueError):
        exports.encode(df, "xlsx")


def test_safe_name_strips_characters_that_are_unsafe_in_filenames():
    assert exports.safe_name("^NSEI") == "NSEI"
    assert exports.safe_name("RELIANCE.NS") == "RELIANCE.NS"
    assert exports.safe_name("../../etc/passwd") == "....etcpasswd"       # separators removed: no path escape
    assert exports.safe_name("^^^") == "symbol"


def test_index_volume_is_filled_from_the_constituents_only_where_it_is_zero():
    data = {
        "^NSEI": [{"time": 1, "volume": 0.0}, {"time": 2, "volume": 99.0}, {"time": 3, "volume": 0.0}],
        "A.NS": [{"time": 1, "volume": 10.0}, {"time": 2, "volume": 10.0}],
        "B.NS": [{"time": 1, "volume": 5.0}],
    }
    exports.fill_index_volume("NIFTY", data)
    assert [r["volume"] for r in data["^NSEI"]] == [15.0, 99.0, 0.0]     # real volume kept; no constituents at t=3 -> stays 0
    exports.fill_index_volume("CURRENT", data)                           # non-index universes are left alone


def test_universe_symbols_put_the_index_first_then_constituents(monkeypatch):
    monkeypatch.setattr(exports, "constituent_symbols", lambda name: ["A.NS", "B.NS"])
    assert exports.universe_symbols("NIFTY", None) == ["^NSEI", "A.NS", "B.NS"]
    assert exports.universe_symbols("CURRENT", "RELIANCE.NS") == ["RELIANCE.NS"]
    with pytest.raises(ValueError):
        exports.universe_symbols("MARS", None)


def test_a_single_symbol_downloads_as_a_file_and_many_as_a_zip(monkeypatch):
    window_rows = {"^NSEI": ROWS, "A.NS": ROWS, "EMPTY.NS": []}
    monkeypatch.setattr(exports, "fetch_rows", lambda symbols, interval, window: {s: window_rows[s] for s in symbols})
    monkeypatch.setattr(exports, "universe_symbols", lambda u, cur: [cur] if u == "CURRENT" else list(window_rows))
    name, mime, payload = exports.build_download("^NSEI", "CURRENT", "1m", "day", TODAY.isoformat(), None, None, "csv")
    assert name == f"NSEI_1m_{TODAY}.csv" and mime == "text/csv" and b"symbol,datetime_ist" in payload
    name, mime, payload = exports.build_download("^NSEI", "NIFTY", "1m", "day", TODAY.isoformat(), None, None, "csv")
    assert mime == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(payload)).namelist()
    assert sorted(names) == sorted([f"NSEI_1m_{TODAY}.csv", f"A.NS_1m_{TODAY}.csv"])   # symbols with no bars are skipped


def test_an_export_with_no_bars_says_so_instead_of_sending_an_empty_file(monkeypatch):
    monkeypatch.setattr(exports, "fetch_rows", lambda symbols, interval, window: {s: [] for s in symbols})
    with pytest.raises(ValueError, match="No bars"):
        exports.build_download("^NSEI", "CURRENT", "1m", "day", TODAY.isoformat(), None, None, "csv")


# ---- the end-of-day schedule ---------------------------------------------------
def good_schedule(path):
    return {"enabled": True, "time": "15:31", "path": str(path), "format": "csv", "interval": "1m", "universe": "NIFTY"}


def test_saving_a_valid_schedule_creates_the_folder_and_persists(isolated_state):
    target = isolated_state / "exports" / "nested"
    cfg = exports.save_schedule(good_schedule(target))
    assert target.is_dir() and cfg["time"] == "15:31"
    assert exports.load_schedule()["universe"] == "NIFTY"


@pytest.mark.parametrize("patch,message", [
    ({"time": "25:00"}, "HH:MM"), ({"time": "3:31"}, "HH:MM"), ({"path": "relative/dir"}, "full path"), ({"path": ""}, "full path"),
    ({"format": "xlsx"}, "csv or parquet"), ({"interval": "2m"}, "bar size"), ({"universe": "MARS"}, "universe"),
])
def test_invalid_schedules_are_rejected_before_they_can_fail_silently_at_3_31pm(isolated_state, patch, message):
    with pytest.raises(ValueError, match=message):
        exports.save_schedule({**good_schedule(isolated_state / "ok"), **patch})


def test_an_unwritable_folder_is_caught_at_save_time(isolated_state):
    blocker = isolated_state / "a_file"
    blocker.write_text("x")                                     # a FILE where a folder is needed
    with pytest.raises(ValueError, match="can't write"):
        exports.save_schedule(good_schedule(blocker / "sub"))


def test_disabling_keeps_the_rest_of_the_saved_settings(isolated_state):
    exports.save_schedule(good_schedule(isolated_state / "ok"))
    cfg = exports.save_schedule({"enabled": False})
    assert cfg["enabled"] is False and cfg["time"] == "15:31"


def test_run_job_writes_one_file_per_symbol_into_a_dated_folder(isolated_state, monkeypatch):
    monkeypatch.setattr(exports, "universe_symbols", lambda u, cur: ["^NSEI", "A.NS", "EMPTY.NS"])
    monkeypatch.setattr(exports, "fetch_rows", lambda symbols, interval, window: {"^NSEI": ROWS, "A.NS": ROWS, "EMPTY.NS": []})
    cfg = good_schedule(isolated_state / "out")
    record = exports.run_job(cfg)
    folder = isolated_state / "out" / TODAY.isoformat()
    assert record["ok"] and record["files"] == 2 and record["skipped"] == 1
    assert sorted(p.name for p in folder.iterdir()) == ["A.NS_1m.csv", "NSEI_1m.csv"]
    assert record["attempts"] == 1


def test_run_job_reports_a_holiday_as_not_ok_without_raising(isolated_state, monkeypatch):
    monkeypatch.setattr(exports, "universe_symbols", lambda u, cur: ["^NSEI"])
    monkeypatch.setattr(exports, "fetch_rows", lambda *a: {"^NSEI": []})
    record = exports.run_job(good_schedule(isolated_state / "out"))
    assert record["ok"] is False and "holiday" in record["message"]


def test_run_job_turns_a_crash_into_a_failed_record(isolated_state, monkeypatch):
    monkeypatch.setattr(exports, "universe_symbols", lambda *a: (_ for _ in ()).throw(RuntimeError("NSE down")))
    record = exports.run_job(good_schedule(isolated_state / "out"))
    assert record["ok"] is False and "NSE down" in record["message"]
