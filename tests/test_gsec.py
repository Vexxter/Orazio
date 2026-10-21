"""Indian G-secs from CCIL NDS-OM: swapped fields (G-secs, SDLs) vs. straight ones (T-bills), the Akamai cookie
warm-up and retry, segments, and the trade recorder that makes each security chartable."""
import json
from unittest.mock import MagicMock

import pytest

from orazio import cache, gsec

# Real NDS-OM rows (19 Oct 2026), trimmed.
CCIL_ROWS = [
    {"ismt_idnt": "07.38 GS 2027            ", "mrty_date": "20/06/2027", "a": "0.0000", "b": "0.0000", "c": "0.0000",
     "f": "10.0000", "e": "6.51530000", "d": "100.54000000", "lty": "100.51250000", "tta": "380.0000",
     "lta": "90.0000", "ltp": "6.55800000"},
    {"ismt_idnt": "06.94 GS 2036            ", "mrty_date": "11/05/2036", "a": "10.0000", "b": "7.35780000",
     "c": "97.16250000", "f": "10.0000", "e": "7.35590000", "d": "97.17500000", "lty": "97.16500000",
     "tta": "13255.0000", "lta": "10.0000", "ltp": "7.35740000"},
    {"ismt_idnt": "07.10 GS 2034            ", "mrty_date": "08/04/2034", "a": "0", "b": "0", "c": "0", "f": "0",
     "e": "0", "d": "0", "lty": "0", "tta": "0", "lta": "0", "ltp": "0"},
]
TBILL = {"ismt_idnt": "091 DTB 14012027         ", "mrty_date": "14/01/2027", "a": "0", "b": "0", "c": "0",
         "f": "25.0000", "e": "5.76500000", "d": "98.67530000", "lty": "5.75000000", "ltp": "98.67870000",
         "tta": "40.0000", "lta": "30.0000"}


def test_gsec_row_reads_ccils_swapped_yield_and_price_fields():
    row = gsec.gsec_row(CCIL_ROWS[1])
    assert row["security"] == "06.94 GS 2036" and row["id"] == "NDS_0694_GS_2036"
    assert row["maturity"] == "2036-05-11"
    assert row["ltYield"] == 7.3574 and row["ltPrice"] == 97.165
    assert (row["bidYield"], row["bidPrice"], row["askYield"], row["askPrice"]) == (7.3578, 97.1625, 7.3559, 97.175)
    assert row["traded"] == 13255.0


def test_tbills_are_not_swapped():
    row = gsec.gsec_row(TBILL, swapped=False)
    assert row["ltYield"] == 5.75 and row["ltPrice"] == 98.6787 and row["id"] == "NDS_091_DTB_14012027"
    assert row["askYield"] == 5.765 and row["bidYield"] is None


def test_an_empty_side_or_no_trades_reads_as_null_not_zero():
    no_bid = gsec.gsec_row(CCIL_ROWS[0])
    assert no_bid["bidYield"] is None and no_bid["bidAmt"] is None and no_bid["askYield"] == 6.5153
    untraded = gsec.gsec_row(CCIL_ROWS[2])
    assert untraded["ltYield"] is None and untraded["ltPrice"] is None and untraded["traded"] == 0.0


def test_chart_ids_fit_the_symbol_rules():
    from orazio.symbols import SYMBOL_RE
    for name in ["06.57 GS 2033 17 AUG", "07.50 GOI SGRB 2056", "GS19JUL2027C", "07.23 KA SDL 2028", "GOI FRB 2028"]:
        cid = gsec.chart_id(name)
        assert SYMBOL_RE.match(cid) and gsec.is_gsec(cid), cid
    assert gsec.chart_id("06.57 GS 2033 17 AUG") == "NDS_0657_GS_2033_17_AUG"


def _resp(payload=None):
    r = MagicMock()
    if payload is None:
        r.json.side_effect = ValueError("not json")
    else:
        r.json.return_value = payload
    return r


@pytest.fixture
def ccil(monkeypatch):
    http = MagicMock()
    monkeypatch.setattr(gsec, "ccil_http", http)
    monkeypatch.setattr(gsec, "_warm", False)
    return http


def test_segment_sorted_by_traded_amount_with_market_status(ccil):
    def post(url, timeout):
        return _resp({"resultMarketOpenClose": "Y"}) if "resource_id=ticker" in url else _resp({"result1": json.dumps(CCIL_ROWS)})
    ccil.post.side_effect = post
    d = gsec.segment("cg")
    assert d["available"] and d["open"] is True and d["segment"] == "cg"
    assert [r["security"] for r in d["rows"]] == ["06.94 GS 2036", "07.38 GS 2027", "07.10 GS 2034"]
    assert ccil.get.call_count == 1          # warmed up once, not per call


def test_tbill_segment_uses_its_resource_and_straight_fields(ccil):
    seen = []
    def post(url, timeout):
        seen.append(url)
        return _resp({"resultMarketOpenClose": "Y"}) if "resource_id=ticker" in url else _resp({"result1": json.dumps([TBILL])})
    ccil.post.side_effect = post
    assert gsec.segment("tbill")["rows"][0]["ltYield"] == 5.75
    assert any("resource_id=NDSOM_TBILL" in u for u in seen)


def test_when_issued_rows_may_sit_under_result2(ccil):
    ccil.post.side_effect = lambda url, timeout: (_resp({"resultMarketOpenClose": "Y"}) if "ticker" in url
                                                  else _resp({"result1": "[]", "result2": json.dumps(CCIL_ROWS[:1])}))
    assert len(gsec.segment("wi")["rows"]) == 1


def test_a_non_json_reply_rewarms_the_cookies_and_retries_once(ccil):
    replies = iter([_resp(None), _resp({"result1": json.dumps(CCIL_ROWS[:1])}), _resp({"resultMarketOpenClose": "N"})])
    ccil.post.side_effect = lambda url, timeout: next(replies)
    d = gsec.segment("cg")
    assert d["available"] and d["open"] is False and len(d["rows"]) == 1
    assert ccil.get.call_count == 2


def test_ccil_blocked_or_down_means_unavailable(ccil):
    ccil.post.side_effect = lambda url, timeout: _resp(None)
    assert gsec.segment("cg") == {"segment": "cg", "available": False, "open": False, "rows": []}
    ccil.get.side_effect = ConnectionError("down")
    cache._store.clear()
    assert gsec.segment("cg") == {"segment": "cg", "available": False, "open": None, "rows": []}


# ---------- recorder ----------
T0 = 1792386000          # 19 Oct 2026, 10:30 IST


def _row(traded, yld, sid="NDS_0694_GS_2036"):
    return {"id": sid, "traded": traded, "ltYield": yld, "ltPrice": 97.0}


@pytest.fixture
def fresh_ticks(isolated_state, monkeypatch):
    monkeypatch.setattr(gsec, "_ticks", {})
    return isolated_state


def test_record_adds_a_tick_only_when_the_traded_amount_grows(fresh_ticks):
    assert gsec.record([_row(100, 7.35), _row(0, None, "NDS_X")], T0) == 1
    assert gsec.record([_row(100, 7.35)], T0 + 20) == 0                 # nothing new traded
    assert gsec.record([_row(110, 7.36)], T0 + 40) == 1
    assert gsec.ticks_for("NDS_0694_GS_2036", T0 - 1) == [(T0, 7.35), (T0 + 40, 7.36)]


def test_ticks_survive_a_restart(fresh_ticks, monkeypatch):
    gsec.record([_row(100, 7.35)], T0)
    monkeypatch.setattr(gsec, "_ticks", {})                           # a new process: memory is empty
    assert gsec.ticks_for("NDS_0694_GS_2036", T0 - 1) == [(T0, 7.35)]


def test_session_hours_are_weekdays_0900_to_1715_ist():
    assert gsec.in_session(T0)
    assert not gsec.in_session(T0 + 8 * 3600)                           # 18:30 IST
    assert not gsec.in_session(T0 - 2 * 86400)                          # Saturday


def test_ticks_make_intraday_and_daily_bars():
    ticks = [(T0, 7.35), (T0 + 30, 7.37), (T0 + 61, 7.34), (T0 + 86400, 7.30)]
    one_min = gsec.bars(ticks, 60)
    assert [(b["open"], b["high"], b["low"], b["close"]) for b in one_min[:2]] == [(7.35, 7.37, 7.35, 7.37), (7.34, 7.34, 7.34, 7.34)]
    daily = gsec.bars(ticks, 86400)
    assert [b["time"] for b in daily] == [1792368000, 1792454400] and daily[0]["high"] == 7.37


def test_quote_uses_the_last_trade_and_yesterdays_last_tick_as_previous_close(fresh_ticks, monkeypatch):
    gsec.record([_row(100, 7.40)], T0 - 86400)                          # Sunday's file stands in for "yesterday"
    gsec.record([_row(100, 7.35)], T0)
    monkeypatch.setattr(gsec, "find", lambda s: {"ltYield": 7.35, "bidYield": None, "askYield": None})
    q = gsec.quote("NDS_0694_GS_2036", now=T0 + 60)
    assert q == {"price": 7.35, "prevClose": 7.40, "marketTime": T0, "currency": "%"}


def test_routes(client, monkeypatch):
    monkeypatch.setattr(gsec, "segment", lambda seg: {"segment": seg, "available": True, "open": True, "rows": []})
    assert client.get("/api/bonds/india?segment=sdl").get_json()["segment"] == "sdl"
    monkeypatch.setattr(gsec, "candles", lambda s, i, r: {"symbol": s, "candles": [], "decimals": 4})
    assert client.get("/api/candles?symbol=NDS_0657_GS_2033_17_AUG&interval=1m&range=1D").get_json()["decimals"] == 4
