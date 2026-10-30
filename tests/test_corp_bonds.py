"""NSE-listed corporate bonds: row shaping, the approximate yield to maturity, and the route."""
from datetime import date
from unittest.mock import patch

import pytest

from orazio import corp_bonds

TODAY = date(2026, 10, 19)
NSE_ROW = {"bYield": "0", "close": "1007.77", "coupr": "9.6", "credit_rating": "AA/Negative, AA/Stable",
           "face_value": "1000", "high": "1007.77", "isin": "INE530B08102", "low": "1001.75", "ltP": "1002",
           "maturity_date": "24-Jun-2028", "per": "-0.57", "qty": "4408", "rating_agency": "CRISIL",
           "series": "NF", "symbol": "96IIFL28A", "trdVal": "4418402.88"}


def test_ytm_of_a_par_bond_on_its_coupon_date_is_its_coupon():
    assert corp_bonds.approx_ytm(1000, 8, 1000, date(2031, 10, 19), TODAY) == 8.0


def test_ytm_counts_accrued_interest_on_the_clean_price():
    # 9.6% coupon, ~4 months since the last coupon, clean price 1002: the yield sits just under the coupon,
    # not at the 11.5% that treating 1002 as the dirty price gives.
    assert corp_bonds.approx_ytm(1002, 9.6, 1000, date(2028, 6, 24), TODAY) == pytest.approx(9.4, abs=0.1)


def test_ytm_rises_when_the_price_falls():
    assert corp_bonds.approx_ytm(950, 8, 1000, date(2031, 10, 19), TODAY) > 9


def test_ytm_gives_up_on_matured_or_unpriced_bonds():
    assert corp_bonds.approx_ytm(1000, 8, 1000, date(2026, 1, 1), TODAY) is None
    assert corp_bonds.approx_ytm(None, 8, 1000, date(2031, 1, 1), TODAY) is None
    assert corp_bonds.approx_ytm(5, 8, 1000, date(2031, 1, 1), TODAY) is None     # outside any sane yield


def test_corp_row_shapes_nse_fields():
    r = corp_bonds.corp_row(NSE_ROW, TODAY)
    assert r["symbol"] == "96IIFL28A" and r["rating"] == "AA/Negative" and r["agency"] == "CRISIL"
    assert r["coupon"] == 9.6 and r["maturity"] == "2028-06-24" and r["ltPrice"] == 1002.0
    assert r["tradedLakh"] == 44.18 and r["ytmApprox"] and r["ytm"] == pytest.approx(9.4, abs=0.1)


def test_nses_own_yield_wins_when_it_has_one():
    r = corp_bonds.corp_row({**NSE_ROW, "bYield": "9.85"}, TODAY)
    assert r["ytm"] == 9.85 and not r["ytmApprox"]


def test_untraded_bonds_have_no_price_or_yield():
    r = corp_bonds.corp_row({**NSE_ROW, "trdVal": "0"}, TODAY)
    assert r["ltPrice"] is None and r["ytm"] is None and r["tradedLakh"] == 0


def test_corporate_sorted_by_traded_value_and_down_means_unavailable():
    rows = [{**NSE_ROW, "symbol": "A", "trdVal": "100"}, {**NSE_ROW, "symbol": "B", "trdVal": "900"}]
    with patch("orazio.corp_bonds.nse_get", return_value={"data": rows}):
        assert [r["symbol"] for r in corp_bonds.corporate()["rows"]] == ["B", "A"]
    from orazio import cache
    cache._store.clear()
    with patch("orazio.corp_bonds.nse_get", side_effect=ConnectionError("down")):
        assert corp_bonds.corporate() == {"segment": "corp", "available": False, "open": None, "rows": []}


def test_route(client):
    with patch("orazio.corp_bonds.nse_get", return_value={"data": [NSE_ROW]}):
        d = client.get("/api/bonds/india?segment=corp").get_json()
    assert d["segment"] == "corp" and d["rows"][0]["symbol"] == "96IIFL28A"
