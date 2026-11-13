"""Real-time CAS rebuild: recovering an index's composition, reading BSE's frames, and the estimate itself."""
from datetime import datetime

import numpy as np

from orazio import cas_rebuild
from orazio.constants import IST


def test_fit_composition_recovers_exact_weights_and_never_goes_negative():
    rng = np.random.default_rng(0)
    prices = 100 + rng.normal(0, 1, (400, 4)).cumsum(axis=0)
    true_k = np.array([0.5, 0.3, 0.2, 0.0])          # the 4th stock isn't in the index
    index = prices @ true_k + rng.normal(0, 0.01, 400)
    k = cas_rebuild.fit_composition(prices, index)
    assert np.allclose(k[:3], true_k[:3], atol=0.01)
    assert (k >= 0).all() and k[3] < 0.01


def test_parse_eq_frame_reads_bse_field_order_and_treats_dash_as_unchanged():
    frame = "500325|EQ|2020|7|1168.25|5120|-|-|-|-|-|1166.70|-|-"
    assert cas_rebuild.parse_eq_frame(frame) == ("500325", 1168.25, 1166.70)
    assert cas_rebuild.parse_eq_frame("500325|EQ|2020|3|-|-|-|-|-|-|-|-|-") == ("500325", None, None)
    assert cas_rebuild.parse_eq_frame("garbage") is None


def test_board_rows_maps_scrip_names_and_ignores_zero_auction_price():
    page = [{"ScripName": "RELIANCE", "Symbol": "500325", "IndEq_Price": "0.00", "Price": 1166.7, "MCapFF": "11667"},
            {"ScripName": "TCS", "Symbol": "532540", "IndEq_Price": "3010.50", "Price": 3000.0},
            {"ScripName": "BAD", "Symbol": "1", "IndEq_Price": "x", "Price": 1}]
    rows = cas_rebuild.board_rows([page])
    assert rows["RELIANCE"] == {"code": "500325", "iep": None, "price": 1166.7, "ffShares": 10.0}
    assert rows["TCS"]["iep"] == 3010.5 and "BAD" not in rows








def test_cap_weights_applies_nse_sector_caps():
    w = cas_rebuild.cap_weights([50, 25, 15, 5, 5])
    assert abs(w.sum() - 1) < 1e-9
    assert w.max() <= 0.33 + 1e-9 and np.sort(w)[-3:].sum() <= 0.62 + 1e-9


def test_fit_with_prior_keeps_every_stock_and_tracks_the_index():
    rng = np.random.default_rng(1)
    prices = 100 + rng.normal(0, 1, (500, 3)).cumsum(axis=0)
    true_k = np.array([0.5, 0.3, 0.2])
    index = prices @ true_k + rng.normal(0, 0.05, 500)
    k = cas_rebuild.fit_with_prior(prices, index, prior=np.array([0.4, 0.4, 0.2]), alpha_rel=1e-4)
    assert (k > 0).all()
    assert np.sqrt(((prices @ k - index) ** 2).mean()) < 0.2




def test_anchor_only_fit_keeps_nse_weights_and_fits_just_the_divisor():
    prices = np.array([[100.0, 50.0], [110.0, 50.0], [100.0, 60.0]])
    index = prices @ np.array([2.0, 4.0])                        # true shares 1:2, divisor 0.5
    k = cas_rebuild.fit_with_prior(prices, index, prior=np.array([1.0, 2.0]), alpha_rel=None)
    assert np.allclose(k, [2.0, 4.0])


def test_nse_shares_turn_ffmc_into_free_float_share_counts(monkeypatch):
    rows = [{"symbol": "NIFTY 50", "priority": 1, "ffmc": None, "lastPrice": 22700},
            {"symbol": "HDFCBANK", "priority": 0, "ffmc": 7_000_000.0, "lastPrice": 700.0},
            {"symbol": "NOFFMC", "priority": 0, "ffmc": None, "lastPrice": 10.0}]
    monkeypatch.setattr(cas_rebuild, "nse_get", lambda path, params=None: {"data": rows})
    assert cas_rebuild.nse_shares("NIFTY") == {"HDFCBANK": 10_000.0}


# ---- the estimate: NSE first, BSE between NSE prints ----------------------------------------------
def fresh_day():
    return {"date": "d", "base": {}, "bse_base": {}, "anchors": {}}


def test_bases_are_snapshotted_once_and_never_overwritten_at_the_cross():
    day = fresh_day()
    cas_rebuild.snapshot_bases(day, {"A": {"px": None, "ltp": 100.0}}, {"A": {"iep": None, "price": 101.0}})
    cas_rebuild.snapshot_bases(day, {"A": {"px": 110.0, "ltp": 110.0}}, {"A": {"iep": 111.0, "price": 111.0}})  # exchanges overwrite LTP at the cross
    assert day["base"]["A"] == 100.0 and day["bse_base"]["A"] == 101.0


def test_nse_print_is_carried_forward_by_bse_move_since_it():
    day = fresh_day()
    day["base"]["A"] = 100.0
    assert cas_rebuild.stock_price("A", day, nse_px=102.0, bse_now=204.0) == (102.0, True)   # NSE prints; BSE level ignored
    px, live = cas_rebuild.stock_price("A", day, nse_px=102.0, bse_now=206.04)                 # BSE +1% ... too big: guarded
    assert px == 102.0
    px, _ = cas_rebuild.stock_price("A", day, nse_px=102.0, bse_now=205.0)                     # BSE +0.49% since NSE's print
    assert round(px, 4) == round(102.0 * 205.0 / 204.0, 4)
    px, _ = cas_rebuild.stock_price("A", day, nse_px=103.0, bse_now=205.0)                     # NSE prints again: re-anchor
    assert px == 103.0


def test_bse_alone_when_nse_has_nothing_and_unpriced_stocks_stay_put():
    day = fresh_day()
    day["base"].update(A=100.0, B=50.0)
    day["bse_base"]["A"] = 200.0
    assert cas_rebuild.stock_price("A", day, None, 202.0) == (101.0, True)
    assert cas_rebuild.stock_price("B", day, None, None) == (50.0, False)


def test_blend_moves_the_reference_by_the_weighted_move_and_reports_coverage():
    day = fresh_day()
    day["base"].update(A=100.0, B=100.0)
    k = {"A": 2.0, "B": 1.0}                       # index = 2A + B, 300 at 15:15
    value, coverage = cas_rebuild.blend(k, day, {"A": {"px": 110.0}}, {}, ref_value=300.0)
    assert value == 320.0 and round(coverage, 3) == round(200 / 300, 3)


def test_blend_refuses_until_nine_tenths_of_the_stocks_have_a_base():
    day = fresh_day()
    day["base"].update({s: 10.0 for s in "ABCDEFGH"})
    assert cas_rebuild.blend({s: 1.0 for s in "ABCDEFGHIJ"}, day, {}, {}, 100.0) is None


def test_tick_records_a_point_per_index_with_a_fit_and_reference(monkeypatch):
    monkeypatch.setitem(cas_rebuild._fits, "NIFTY", {"k": {"A": 1.0}, "rmse": 1, "date": "x"})
    monkeypatch.setattr(cas_rebuild, "board", lambda: {"A": {"code": "1", "iep": None, "price": 100.0}})
    monkeypatch.setitem(cas_rebuild._day, "date", None)
    cas_rebuild._series["NIFTY"].clear()
    now = datetime(2026, 10, 14, 15, 20, tzinfo=IST)
    assert cas_rebuild.in_window(now) and not cas_rebuild.in_window(now.replace(hour=15, minute=41))
    cas_rebuild.tick(now, {"NIFTY": {"value": 50.0}, "BANKNIFTY": None}, {}, nse={"A": {"px": 105.0, "ltp": 100.0}})
    snap = cas_rebuild.snapshot("NIFTY")
    assert snap["value"] == 52.5 and snap["coverage"] == 1.0
    assert cas_rebuild.snapshot("BANKNIFTY") is None
    cas_rebuild._series["NIFTY"].clear()


def test_reanchor_lands_on_nse_prints_and_carries_the_move_between_them():
    day = {"nse_index": {}}
    assert cas_rebuild.reanchor(day, "NIFTY", 100.0, None) == 100.0          # no NSE print yet: raw rebuild
    assert cas_rebuild.reanchor(day, "NIFTY", 100.0, 98.0) == 98.0           # NSE prints: exact, offset gone
    assert cas_rebuild.reanchor(day, "NIFTY", 101.0, 98.0) == 98.0 * 1.01    # same print, rebuild moved +1%
    assert cas_rebuild.reanchor(day, "NIFTY", 101.0, 99.5) == 99.5           # next print: snap again
