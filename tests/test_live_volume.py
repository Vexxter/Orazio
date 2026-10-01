"""Live index volume: NSE's running total + Yahoo's constituent minutes -> per-bar volume bars."""
from datetime import datetime

import pytest

from orazio import live_volume as lv
from orazio.constants import IST

SYM = "^NSEI"
# Today's 09:15 IST — the code under test deliberately anchors the opening bar to the current day.
OPEN = int(datetime.now(IST).replace(hour=9, minute=15, second=0, microsecond=0).timestamp())


@pytest.fixture(autouse=True)
def clean_state():
    lv._samples[SYM].clear()
    lv._hist[SYM] = {}
    yield
    lv._samples[SYM].clear()
    lv._hist[SYM] = {}


def minutes(result, base=OPEN):
    return {(k - base) // 60: round(v) for k, v in result.items()}


# ---- record ----------------------------------------------------------------
def test_unchanged_totals_are_not_stored_twice():
    lv.record(SYM, 1000, OPEN + 10)
    lv.record(SYM, 1000, OPEN + 20)
    assert len(lv._samples[SYM]) == 1


def test_a_reset_seen_at_the_open_counts_everything_so_far_as_opening_volume():
    lv.record(SYM, 900_000_000, OPEN - 600)          # yesterday's final total, pre-market
    lv.record(SYM, 500_000, OPEN + 5)                # total fell: a new session has just opened
    assert list(lv._samples[SYM])[0][1] == 0.0       # baseline 0
    assert lv.bucket_volumes(SYM, 60) == {OPEN: 500_000.0}


def test_a_reset_seen_mid_session_must_not_dump_the_whole_day_into_one_bar():
    lv.record(SYM, 900_000_000, OPEN - 600)
    lv.record(SYM, 19_000_000, OPEN + 7 * 60)        # app (re)started 7 minutes in, over a stale seed
    assert [v for _t, v in lv._samples[SYM]] == [19_000_000.0]     # baselined at the current total, no 0 baseline
    assert lv.bucket_volumes(SYM, 60) == {}


# ---- bucket_volumes --------------------------------------------------------
def test_sampled_deltas_land_in_the_minute_they_arrived():
    lv.record(SYM, 1000, OPEN + 5)
    lv.record(SYM, 1800, OPEN + 20)
    lv.record(SYM, 2100, OPEN + 70)
    assert lv.bucket_volumes(SYM, 60) == {OPEN: 800.0, OPEN + 60: 300.0}


def test_yahoo_history_calibrates_to_nse_level_and_the_open_bar_gets_the_remainder():
    # Yahoo undercounts by 20% (800 where NSE says 1000) and reports the 09:15 bar as 0.
    lv._hist[SYM] = {OPEN: 0.0, **{OPEN + 60 * i: 800.0 for i in range(1, 10)}}
    start = OPEN + 300                                # sampling starts 09:20:00
    total = 100_000.0
    lv.record(SYM, total, start)
    for i in range(1, 6):                             # NSE adds 1000 shares a minute for five minutes
        total += 1000
        lv.record(SYM, total, start + 60 * i - 1)
    got = minutes(lv.bucket_volumes(SYM, 60))
    assert got[2] == 1000 and got[3] == 1000          # Yahoo's 800 scaled up by 1.25 to NSE's level
    assert got[0] == 96_000                           # open bar = NSE's running total minus every later bar
    assert sum(got.values()) == total                 # and the bars add up to NSE's total exactly


def test_without_overlapping_samples_yahoo_is_used_as_is():
    lv._hist[SYM] = {OPEN + 60 * i: 800.0 for i in range(1, 6)}
    lv.record(SYM, 5000, OPEN + 600)                  # sampling began long after: no overlap to calibrate on
    assert minutes(lv.bucket_volumes(SYM, 60))[1] == 800


def test_five_minute_bars_are_the_sum_of_their_minutes():
    lv._hist[SYM] = {OPEN: 0.0, **{OPEN + 60 * i: 1000.0 for i in range(1, 5)}}
    lv.record(SYM, 20_000, OPEN + 250)
    lv.record(SYM, 20_500, OPEN + 262)
    five = lv.bucket_volumes(SYM, 300)
    assert list(five) == [OPEN] and five[OPEN] == pytest.approx(20_500)


def test_daily_bar_is_simply_the_latest_running_total():
    lv.record(SYM, 1000, OPEN + 5)
    lv.record(SYM, 4500, OPEN + 500)
    assert list(lv.bucket_volumes(SYM, 86400).values()) == [4500.0]


def test_untracked_symbols_have_no_volume_bars():
    assert lv.bucket_volumes("^GSPC", 60) == {}


# ---- apply -----------------------------------------------------------------
def test_apply_fills_only_zero_volume_rows():
    lv.record(SYM, 1000, OPEN + 5)
    lv.record(SYM, 1800, OPEN + 20)
    rows = [{"time": OPEN, "volume": 0.0}, {"time": OPEN + 60, "volume": 0.0}, {"time": OPEN - 60, "volume": 42.0}]
    lv.apply(SYM, rows, 60)
    assert [r["volume"] for r in rows] == [800.0, 0.0, 42.0]       # real Yahoo volume (42) is never overwritten


def test_apply_ignores_untracked_symbols_and_missing_steps():
    rows = [{"time": OPEN, "volume": 0.0}]
    assert lv.apply("^GSPC", rows, 60) is rows and rows[0]["volume"] == 0.0
    assert lv.apply(SYM, rows, None) is rows


# ---- persistence -----------------------------------------------------------
def test_samples_survive_a_restart_but_only_on_the_same_day(isolated_state):
    lv.record(SYM, 1000, OPEN + 5)
    lv._save()
    lv._samples[SYM].clear()
    lv.load_seed()
    assert len(lv._samples[SYM]) == 1
    lv._samples[SYM].clear()
    import json
    seed = json.loads(open(lv.SEED_FILE).read())
    seed["date"] = "2001-01-01"
    open(lv.SEED_FILE, "w").write(json.dumps(seed))
    lv.load_seed()
    assert len(lv._samples[SYM]) == 0                    # yesterday's seed is ignored
