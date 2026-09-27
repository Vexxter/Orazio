from datetime import datetime

from orazio.cas import cas_phase, normalise_cas_book, normalise_cas_rows
from orazio.constants import IST


def _ist(h, m, s=0, weekday_date="2026-09-21"):  # a Monday
    y, mo, d = (int(x) for x in weekday_date.split("-"))
    return datetime(y, mo, d, h, m, s, tzinfo=IST)


def test_cas_phase_during_pre_open():
    phase, seconds, stage, label = cas_phase(_ist(9, 3))
    assert phase == "pre-open"
    assert stage == "Order entry — market & limit"
    assert label == "Pre-open auction"
    assert seconds == (9 * 60 + 15 - (9 * 60 + 3)) * 60


def test_cas_phase_during_closing_auction_matching_stage():
    phase, seconds, stage, _label = cas_phase(_ist(15, 32))
    assert phase == "closing-auction"
    assert stage == "Matching, confirmation & closing price"
    assert seconds == 3 * 60


def test_cas_phase_between_sessions_reports_waiting_and_next_label():
    phase, seconds, stage, label = cas_phase(_ist(12, 0))
    assert phase == "waiting:closing-auction"
    assert stage is None
    assert label == "Closing auction (CAS)"
    assert seconds is not None and seconds > 0


def test_cas_phase_on_weekend_always_waits_for_pre_open():
    saturday = _ist(9, 3, weekday_date="2026-09-19")
    phase, _seconds, _stage, label = cas_phase(saturday)
    assert phase == "waiting:pre-open"
    assert label == "Pre-open auction"


def test_normalise_cas_rows_maps_nse_field_names():
    payload = {"data": [{
        "symbol": "RELIANCE", "refrencePrice": 1400.0, "IEP": 1402.5, "finalPrice": 0,
        "change": 2.5, "perChange": 0.18, "iiqAtEP": 500, "iiqAtMO": -200,
        "totalBuyQuantity": 1000, "totalSellQuantity": 800,
        "atoBuyQuantity": 10, "atoSellQuantity": 5, "lastTradedPrice": 1400.0,
        "upperBand": 1500.0, "lowerBand": 1300.0,
        "bestBidPrice": 1401.0, "bestBidQty": 50, "bestAskPrice": 1403.0, "bestAskQty": 40,
        "totTradedQty": 900, "finalQuantity": 0, "finalValue": 0, "orderBook": [],
    }, {"symbol": None}, "not-a-dict"]}
    rows = normalise_cas_rows(payload)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "RELIANCE"
    assert rows[0]["refPrice"] == 1400.0
    assert rows[0]["iep"] == 1402.5
    assert rows[0]["imbalanceMO"] == -200


def test_normalise_cas_rows_handles_empty_payload():
    assert normalise_cas_rows(None) == []
    assert normalise_cas_rows({}) == []


def test_normalise_cas_book_flags_the_equilibrium_rung():
    book = [
        {"price": 100.0, "buyQuantity": 10, "sellQuantity": 0, "flag": False},
        {"price": 101.0, "buyQuantity": 5, "sellQuantity": 5, "flag": True},
        "not-a-dict",
    ]
    rungs = normalise_cas_book(book)
    assert len(rungs) == 2
    assert rungs[0]["isIep"] is False
    assert rungs[1]["isIep"] is True


def test_normalise_cas_book_handles_non_list_input():
    assert normalise_cas_book(None) == []
