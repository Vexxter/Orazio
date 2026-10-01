"""GIFT Nifty daily history: NSE IX's official bhavcopy, parsed, cached, and merged with our own bars."""
from datetime import date, datetime, timedelta

from orazio import gift_nifty
from orazio.constants import IST

BHAV = """CONTRACT_D,PREVIOUS_S,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,CLOSE_PRIC,SETTLEMENT,NET_CHANGE,OI_NO_CON,TRADED_QUA,TRD_NO_CON,TRADED_VAL
FUTCURAUDUSD19-OCT-2026,.6985,0,0,0,,.6975,-.14,0,0,0,0
FUTIDXBANKNIFTY27-OCT-2026,54000,54100,54500,53900,54200,54200,.5,,100,100,999
FUTIDXNIFTY27-OCT-2026,22837,22819,22892,22650,22659.5,22659.5,-.77,,58838,58838,2679517422
FUTIDXNIFTY23-NOV-2026,22903,22858,22943,22858,22908,22725,-.77,,7,7,320470
FUTIDXNIFTY29-DEC-2026,22991,0,0,0,,22812.5,-.77,,0,0,0
"""


def ist(text):
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=IST).timestamp())


def contracts(*expiries):
    return [{"expiry": e, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "settle": 1.5, "volume": 10} for e in expiries]


def minute_bars(start, closes):
    return {start + i * 60: [c, c, c, c] for i, c in enumerate(closes)}


# ---- parsing -------------------------------------------------------------------------
def test_parse_bhavcopy_keeps_only_traded_gift_nifty_contracts():
    got = gift_nifty.parse_bhavcopy(BHAV)
    assert [c["expiry"] for c in got] == ["2026-10-27", "2026-11-23"]      # no currencies, no Bank Nifty, no zero-volume Dec contract
    first = got[0]
    assert (first["open"], first["high"], first["low"], first["close"], first["volume"]) == (22819.0, 22892.0, 22650.0, 22659.5, 58838)


def test_parse_bhavcopy_falls_back_to_the_settlement_price_when_close_is_blank():
    text = "H\nFUTIDXNIFTY27-OCT-2026,22837,22819,22892,22650,,22700,-.77,,5,5,1\n"
    assert gift_nifty.parse_bhavcopy(text)[0]["close"] == 22700.0


def test_parse_bhavcopy_survives_garbage():
    assert gift_nifty.parse_bhavcopy("") == []
    junk = "H\nFUTIDXNIFTY27-OCT-2026,not,numbers\nFUTIDXNIFTY99-XXX-2026,1,1,1,1,1,1,1,,1,1,1\n"
    assert gift_nifty.parse_bhavcopy(junk) == []


# ---- picking the contract and building the bar ----------------------------------------------
def test_front_contract_is_the_nearest_expiry_that_has_not_passed():
    cs = contracts("2026-10-27", "2026-11-23")
    assert gift_nifty.front_contract(cs, date(2026, 10, 1))["expiry"] == "2026-10-27"
    assert gift_nifty.front_contract(cs, date(2026, 10, 27))["expiry"] == "2026-10-27"   # expiry day still trades the expiring contract
    assert gift_nifty.front_contract(cs, date(2026, 10, 28))["expiry"] == "2026-11-23"   # rolled
    assert gift_nifty.front_contract(cs, date(2027, 1, 1)) is None


def test_daily_bar_uses_the_cumulative_session_two_file_and_falls_back_to_session_one():
    day = date(2026, 9, 30)
    s1 = [dict(contracts("2026-10-27")[0], low=22650.0, volume=58838)]
    s2 = [dict(contracts("2026-10-27")[0], low=22563.5, volume=70296)]    # the whole trading day: lower low, more volume
    assert gift_nifty.daily_bar(day, s1, s2)["low"] == 22563.5
    assert gift_nifty.daily_bar(day, s1, s2)["volume"] == 70296
    assert gift_nifty.daily_bar(day, s1, [])["low"] == 22650.0            # session 2 not published yet
    assert gift_nifty.daily_bar(day, [], []) is None


def test_daily_bar_time_is_ist_midnight_so_it_lines_up_with_our_own_daily_bars():
    assert gift_nifty.day_slot(date(2026, 10, 1)) == ist("2026-10-01 00:00")


# ---- download + cache -------------------------------------------------------------------------
class Resp:
    def __init__(self, status=200, text=BHAV):
        self.status_code, self.content = status, text.encode()


def test_a_downloaded_day_is_cached_and_never_fetched_twice(isolated_state, monkeypatch):
    calls = []
    monkeypatch.setattr(gift_nifty.requests, "get", lambda *a, **k: calls.append(1) or Resp())
    day = date.today() - timedelta(days=10)
    first = gift_nifty._fetch_day(day)
    assert first["s2"] and len(calls) == 2                                # one request per session file
    assert gift_nifty._fetch_day(day) == first and len(calls) == 2        # second time: straight from disk


def test_a_recent_day_without_its_session_two_file_is_not_frozen_into_the_cache(isolated_state, monkeypatch):
    monkeypatch.setattr(gift_nifty.requests, "get", lambda url, **k: Resp() if "G_T_" in url else Resp(404, ""))
    recent = date.today() - timedelta(days=1)
    result = gift_nifty._fetch_day(recent)
    assert result["s1"] and result["s2"] == []                            # usable now...
    assert gift_nifty._read_day(recent) is None                           # ...but retried later when session 2 is published


def test_a_long_past_day_with_no_files_is_remembered_as_a_holiday(isolated_state, monkeypatch):
    monkeypatch.setattr(gift_nifty.requests, "get", lambda *a, **k: Resp(404, ""))
    old = date.today() - timedelta(days=30)
    assert gift_nifty._fetch_day(old) == {"s1": [], "s2": []}
    assert gift_nifty._read_day(old) == {"s1": [], "s2": []}


def test_a_network_failure_is_not_cached(isolated_state, monkeypatch):
    def boom(*a, **k):
        raise gift_nifty.requests.RequestException("down")
    monkeypatch.setattr(gift_nifty.requests, "get", boom)
    day = date.today() - timedelta(days=10)
    assert gift_nifty._fetch_day(day) is None and gift_nifty._read_day(day) is None


def test_daily_history_covers_weekdays_only_and_never_today(monkeypatch):
    asked = []
    monkeypatch.setattr(gift_nifty, "_ensure_days", lambda days: asked.extend(days) or {})
    gift_nifty.daily_history(30)
    assert asked and all(d.weekday() < 5 for d in asked) and date.today() not in asked


def test_daily_history_builds_one_bar_per_available_day(monkeypatch):
    s2 = gift_nifty.parse_bhavcopy(BHAV)
    monkeypatch.setattr(gift_nifty, "_ensure_days", lambda days: {d: {"s1": [], "s2": s2} for d in days})
    bars = gift_nifty.daily_history(10)
    assert bars and all(b["close"] == 22659.5 for b in bars)
    assert [b["time"] for b in bars] == sorted(b["time"] for b in bars)


# ---- merging and the chart decision --------------------------------------------------------------
def test_history_wins_over_our_own_bars_for_the_same_day():
    history = [{"time": 100, "close": 1.0}]
    own = [{"time": 100, "close": 9.0}, {"time": 200, "close": 2.0}]      # 200 = today, not in the archive yet
    assert [b["close"] for b in gift_nifty.merge_daily(history, own)] == [1.0, 2.0]


def test_chart_serves_todays_intraday_bars_while_they_cover_the_range():
    bars = minute_bars(ist("2026-10-01 08:00"), [100.0, 101.0, 102.0])
    used, rows = gift_nifty.chart("1m", "1D", bars)
    assert used == "1m" and len(rows) == 3


def test_chart_escalates_to_official_daily_history_when_intraday_cannot_cover_the_range(monkeypatch):
    bars = minute_bars(ist("2026-10-01 08:00"), [100.0, 101.0])           # only minutes of intraday exist
    history = [{"time": ist("2026-09-29 00:00"), "open": 1, "high": 2, "low": 0, "close": 1, "volume": 5},
               {"time": ist("2026-09-30 00:00"), "open": 1, "high": 2, "low": 0, "close": 2, "volume": 5}]
    monkeypatch.setattr(gift_nifty, "daily_history", lambda days: history)
    used, rows = gift_nifty.chart("1m", "1M", bars)
    assert used == "1d"                                                    # the caller reports 1D, not 1m
    assert [r["close"] for r in rows] == [1, 2, 101.0]                     # two official days + today from our own bars


def test_chart_with_no_intraday_bars_at_all_still_shows_history(monkeypatch):
    monkeypatch.setattr(gift_nifty, "daily_history", lambda days: [{"time": 5, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}])
    used, rows = gift_nifty.chart("1m", "1D", {})
    assert used == "1d" and len(rows) == 1


def test_a_daily_request_is_always_served_from_history(monkeypatch):
    monkeypatch.setattr(gift_nifty, "daily_history", lambda days: [{"time": 5, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}])
    bars = minute_bars(ist("2026-10-01 08:00"), [100.0])
    used, _rows = gift_nifty.chart("1d", "1Y", bars)
    assert used == "1d"
