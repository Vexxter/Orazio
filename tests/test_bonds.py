"""Global bond yields (CNBC): the catalog, quote shaping, the background-refreshed snapshot, and charting
(CNBC bars, worldgovernmentbonds for the India 10Y's daily history)."""
from unittest.mock import MagicMock

from orazio import bonds


def _resp(payload=None):
    r = MagicMock()
    if payload is None:
        r.json.side_effect = ValueError("not json")
    else:
        r.json.return_value = payload
    return r


CNBC = {"FormattedQuoteResult": {"FormattedQuote": [
    {"symbol": "IN10Y-IN", "last": "7.357%", "change": "-0.02", "last_time": "2026-10-19T01:52:07.000-0400", "realTime": "true"},
    {"symbol": "US10Y", "last": "5.067%", "change": "-0.031", "last_time": "2026-10-19T01:49:02.000-0400", "realTime": "true"},
    {"symbol": "JP10Y-JP", "last": "2.91%", "change": "UNCH", "last_time": "2026-10-19T14:51:47.000+0900", "realTime": "false"},
    {"symbol": "XX10Y-XX", "last": "1%", "change": "0"},           # not in the catalog: ignored
    {"symbol": "UK2Y-GB", "last": "--", "change": "0"},            # no value: ignored
]}}


def test_catalog_covers_37_countries_and_161_yields_with_cnbc_symbols():
    assert len(bonds.CATALOG) == 37 and len(bonds.SYMBOLS) == 161
    assert bonds.SYMBOLS["US10Y"]["name"] == "United States"       # the US has no "-US" suffix
    assert bonds.SYMBOLS["UK10Y-GB"] == {"country": "GB", "name": "United Kingdom", "region": "Europe", "tenor": "10Y"}
    assert bonds.is_bond("JP30Y-JP") and not bonds.is_bond("JP99Y-JP")


def test_quotes_parse_percent_strings_into_yield_and_basis_points(monkeypatch):
    http = MagicMock()
    http.get.return_value = _resp(CNBC)
    monkeypatch.setattr(bonds, "cnbc_http", http)
    rows = {r["symbol"]: r for r in bonds._quotes(["IN10Y-IN", "US10Y", "JP10Y-JP"])}
    assert set(rows) == {"IN10Y-IN", "US10Y", "JP10Y-JP"}
    assert rows["IN10Y-IN"]["yield"] == 7.357 and rows["IN10Y-IN"]["changeBp"] == -2.0 and rows["IN10Y-IN"]["realTime"]
    assert rows["IN10Y-IN"]["label"] == "India 10Y" and rows["IN10Y-IN"]["region"] == "Asia-Pacific"
    assert rows["US10Y"]["changeBp"] == -3.1
    assert rows["JP10Y-JP"]["changeBp"] is None and not rows["JP10Y-JP"]["realTime"]


def test_global_yields_wait_only_for_the_first_load_then_serve_the_snapshot(monkeypatch):
    calls = []
    monkeypatch.setattr(bonds, "_global", {"at": 0.0, "rows": [], "busy": False})
    monkeypatch.setattr(bonds, "_quotes", lambda syms: calls.append(1) or [{"symbol": "US10Y", "yield": 5.0}])
    assert bonds.global_yields() == [{"symbol": "US10Y", "yield": 5.0}]
    assert bonds.global_yields() == [{"symbol": "US10Y", "yield": 5.0}]
    assert len(calls) == 1                                            # fresh: no second fetch


def test_global_yields_keep_the_last_snapshot_when_cnbc_fails(monkeypatch):
    monkeypatch.setattr(bonds, "_global", {"at": 0.0, "rows": [{"symbol": "US10Y"}], "busy": False})
    monkeypatch.setattr(bonds, "_quotes", lambda syms: (_ for _ in ()).throw(ConnectionError("down")))
    bonds._refresh_global()
    assert bonds._global["rows"] == [{"symbol": "US10Y"}] and not bonds._global["busy"]


def test_route_contract(client, monkeypatch):
    monkeypatch.setattr(bonds, "global_yields", lambda: [{"symbol": "US10Y"}])
    assert client.get("/api/bonds/global").get_json() == {"rows": [{"symbol": "US10Y"}]}


# ---------- charting ----------
def _r(t, o, h=None, l=None, c=None):
    return {"time": t, "open": o, "high": h if h is not None else o, "low": l if l is not None else o,
            "close": c if c is not None else o, "volume": 0}


def test_resample_builds_15_minute_bars_from_5_minute_ones():
    rows = [_r(0, 1, 2, 1, 2), _r(300, 2, 5, 2, 3), _r(600, 3, 3, 0.5, 1), _r(900, 9)]
    assert bonds.resample(rows, 900) == [_r(0, 1, 5, 0.5, 1), _r(900, 9)]


def test_last_session_stops_at_the_overnight_gap():
    rows = [_r(0, 1), _r(60, 1), _r(60 + 20 * 3600, 2), _r(60 + 20 * 3600 + 60, 3)]
    assert [r["close"] for r in bonds.last_session(rows)] == [2, 3]
    assert bonds.last_session([]) == []


def test_weekly_groups_by_iso_week():
    mon, fri, next_mon = 1792368000, 1792368000 + 4 * 86400, 1792368000 + 7 * 86400   # 2026-10-19 is a Monday
    rows = bonds.weekly([_r(mon, 7.30), _r(fri, 7.40, 7.45, 7.20, 7.35), _r(next_mon, 7.5)])
    assert rows == [_r(mon, 7.30, 7.45, 7.20, 7.35), _r(next_mon, 7.5)]


def test_wgb_points_drop_weekends_and_junk():
    payload = {"result": {"quote": {
        "1": {"DATA_VAL": "2026-10-16", "CLOSE_VAL": 7.371},   # Friday
        "2": {"DATA_VAL": "2026-10-17", "CLOSE_VAL": 7.382},   # Saturday: dropped
        "3": {"DATA_VAL": "2026-10-19", "CLOSE_VAL": 7.373},
        "4": {"DATA_VAL": "bad", "CLOSE_VAL": 1},
    }}}
    rows = bonds.wgb_points(payload)
    assert [(r["time"], r["close"]) for r in rows] == [(1792108800, 7.371), (1792368000, 7.373)]


def test_today_gets_its_own_daily_bar_instead_of_repainting_fridays():
    friday = [_r(1792108800, 5.098)]
    q = {"price": 5.067, "marketTime": 1792395000}                       # Monday 19 Oct
    assert bonds.with_today(friday, q, "1d")[-1] == _r(1792368000, 5.067)
    assert bonds.with_today(friday, q, "1wk")[-1]["close"] == 5.067     # a new ISO week too
    same_day = [_r(1792368000, 7.373)]
    assert bonds.with_today(same_day, {"price": 7.36, "marketTime": 1792395000}, "1d") == same_day
    assert bonds.with_today(friday, None, "1d") == friday


def test_candles_escalate_past_cnbcs_hourly_limit_and_use_wgb_for_india_daily(monkeypatch):
    calls = []
    monkeypatch.setattr(bonds, "_cnbc_bars", lambda sym, iv, start, end: calls.append((sym, iv)) or [_r(1792108800, 5.1)])
    monkeypatch.setattr(bonds, "_wgb_daily", lambda sym: calls.append((sym, "wgb")) or [_r(1792108800, 7.371)])
    monkeypatch.setattr(bonds, "quote", lambda sym: None)
    d = bonds.candles("US10Y", "1h", "1Y")
    assert d["interval"] == "1d" and d["decimals"] == 3 and calls[-1] == ("US10Y", "1D")
    d = bonds.candles("IN10Y-IN", "1d", "ALL")
    assert calls[-1] == ("IN10Y-IN", "wgb") and d["candles"][0]["close"] == 7.371
    bonds.candles("IN10Y-IN", "15m", "1M")
    assert calls[-1] == ("IN10Y-IN", "5M")                              # 15m is built from 5m


def test_only_indias_close_only_daily_series_asks_for_a_line(monkeypatch):
    monkeypatch.setattr(bonds, "_cnbc_bars", lambda sym, iv, start, end: [_r(1792108800, 5.1)])
    monkeypatch.setattr(bonds, "_wgb_daily", lambda sym: [_r(1792108800, 7.371)])
    monkeypatch.setattr(bonds, "quote", lambda sym: None)
    assert bonds.candles("IN10Y-IN", "1d", "1Y")["closeOnly"] is True
    assert bonds.candles("IN10Y-IN", "1wk", "5Y")["closeOnly"] is False    # weekly bars get a real high/low
    assert bonds.candles("US10Y", "1d", "1Y")["closeOnly"] is False


def test_quote_turns_a_yield_into_a_chart_quote(monkeypatch):
    monkeypatch.setattr(bonds, "_one_quote", lambda sym: {"symbol": sym, "yield": 7.357, "changeBp": -2.0,
                                                          "time": "2026-10-19T01:52:07.000-0400"} if sym == "IN10Y-IN" else None)
    q = bonds.quote("IN10Y-IN")
    assert q["price"] == 7.357 and round(q["prevClose"], 3) == 7.377 and q["marketTime"] == 1792389127
    assert bonds.quote("US10Y") is None


def test_candles_and_name_routes_dispatch_bonds(client, monkeypatch):
    monkeypatch.setattr(bonds, "candles", lambda s, i, r: {"symbol": s, "interval": i, "range": r, "candles": [], "decimals": 3})
    assert client.get("/api/candles?symbol=IN10Y-IN&interval=1d&range=1Y").get_json()["decimals"] == 3
    assert client.get("/api/name?symbol=US10Y").get_json()["name"] == "United States 10Y government bond yield (%)"
    assert client.get("/api/candles/history?symbol=US10Y&interval=1m&before=1").get_json()["exhausted"] is True
