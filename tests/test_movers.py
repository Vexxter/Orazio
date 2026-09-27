import pytest
from unittest.mock import patch

from orazio.movers import _mover_row, movers


@pytest.fixture(autouse=True)
def clear_cache():
    # movers() goes through the shared TTL cache keyed by direction only; without
    # clearing it, back-to-back tests within the TTL window would read each other's
    # mocked responses instead of their own.
    from orazio import cache
    cache._store.clear()
    yield
    cache._store.clear()


def test_mover_row_shapes_nse_fields():
    raw = {"symbol": "BAJFINANCE", "open_price": 1034.7, "high_price": 1041, "low_price": 1022,
           "ltp": 1034.9, "prev_price": 1008.8, "perChange": 2.59, "trade_quantity": 4496724}
    assert _mover_row(raw) == {
        "symbol": "BAJFINANCE", "ltp": 1034.9, "perChange": 2.59,
        "open": 1034.7, "high": 1041, "low": 1022, "volume": 4496724,
    }


def test_movers_sorts_gainers_desc_and_losers_asc_and_falls_back_to_allsec():
    def fake_nse_get(path, params=None):
        direction = params["index"]
        if direction == "gainers":
            return {"allSec": {"data": [
                {"symbol": "A", "perChange": 1.0}, {"symbol": "B", "perChange": 3.0},
            ]}}
        return {"allSec": {"data": [
            {"symbol": "C", "perChange": -1.0}, {"symbol": "D", "perChange": -4.0},
        ]}}

    with patch("orazio.movers.nse_get", side_effect=fake_nse_get):
        result = movers("bogus-universe")

    assert result["universe"] == "allSec"
    assert result["available"] is True
    assert [r["symbol"] for r in result["gainers"]] == ["B", "A"]
    assert [r["symbol"] for r in result["losers"]] == ["D", "C"]


def test_movers_unavailable_when_nse_has_nothing():
    with patch("orazio.movers.nse_get", return_value=None):
        result = movers("NIFTY")
    assert result == {"available": False, "universe": "NIFTY", "gainers": [], "losers": []}
