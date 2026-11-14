"""Implied policy path from bill curves: interpolation, forwards, the basis rule, T-bill points."""
from datetime import date

from orazio import rate_path


def test_interpolate_is_linear_and_flat_beyond_the_ends():
    pts = [(0.25, 5.0), (0.5, 6.0)]
    assert rate_path.interpolate(pts, 0.375) == 5.5 and rate_path.interpolate(pts, 0.1) == 5.0 and rate_path.interpolate(pts, 1) == 6.0


def test_flat_curve_at_the_anchor_prices_nothing():
    p = rate_path.path([(1 / 12, 4.0), (0.25, 4.0), (0.5, 4.0), (1.0, 4.0)], 4.0)
    assert all(w["vsAnchorBp"] == 0 for w in p["windows"]) and p["verdict"] == "no change priced"


def test_forwards_and_the_one_month_basis():
    # Bills 15 bp over the anchor at 1M, then rising: forward 6M-12M = (4.65*1 - 4.45*0.5)/0.5 = 4.85
    p = rate_path.path([(1 / 12, 4.03), (0.25, 4.25), (0.5, 4.45), (1.0, 4.65)], 3.88)
    assert p["basisBp"] == 15.0
    last = p["windows"][-1]
    assert last["label"] == "6M–12M" and last["forward"] == 4.85 and last["vsAnchorBp"] == round((4.85 - 3.88 - 0.15) * 100, 1)
    assert p["windows"][0]["vsAnchorBp"] == 0.0 and "hikes" in p["verdict"]


def test_no_basis_without_a_short_bill_unless_asked():
    pts = [(0.25, 5.8), (0.5, 5.7), (1.0, 5.6)]
    assert rate_path.path(pts, 5.35)["basisBp"] == 0.0
    p = rate_path.path(pts, 5.35, always_basis=True)
    assert p["basisBp"] == 45.0 and "cuts" in p["verdict"]


def test_tbill_points_skip_one_sided_quotes():
    rows = [{"maturity": "2027-02-11", "ltYield": 5.6}, {"maturity": "2027-05-13", "bidYield": 5.7, "askYield": 5.66},
            {"maturity": "2027-08-12", "askYield": 5.9}, {"maturity": "2026-11-01", "ltYield": 5.0}]
    pts = rate_path.tbill_points(rows, date(2026, 11, 13))
    assert [round(y, 2) for _, y in pts] == [5.6, 5.68] and round(pts[0][0] * 365) == 90


def test_india_waits_for_enough_priced_bills(monkeypatch):
    monkeypatch.setattr(rate_path.gsec, "segment", lambda seg: {"rows": [{"maturity": "2027-02-11", "askYield": 5.75}]})
    monkeypatch.setattr(rate_path.macro, "liquidity", lambda: [{"date": "2026-11-12", "treps": 5.35}])
    d = rate_path.india(date(2026, 11, 13))
    assert not d["available"] and "0 of 3" in d["reason"]


def test_india_fills_thin_mornings_with_recorded_bill_trades(monkeypatch):
    days = {"2026-11-12": {"NDS_91_DTB_12022027": [[0, 5.6, 98.6, 25.0]], "NDS_182_DTB_14052027": [[0, 5.7, 97.2, 10.0]],
                           "NDS_0694_GS_2036": [[0, 7.3, 97.5, 5.0]]},
            "2026-11-13": {"NDS_364_DTB_11112027": [[0, 5.8, 94.5, 5.0]]}}
    monkeypatch.setattr(rate_path.gsec, "_load_day", lambda day: days.get(day, {}))
    got = rate_path.recorded_bills(date(2026, 11, 13))
    assert sorted(got) == ["NDS_182_DTB_14052027", "NDS_364_DTB_11112027", "NDS_91_DTB_12022027"]   # G-secs skipped
    assert got["NDS_91_DTB_12022027"]["maturity"] == "2027-02-12"
    monkeypatch.setattr(rate_path.gsec, "segment", lambda seg: {"rows": [{"id": "NDS_91_DTB_12022027", "maturity": "2027-02-12", "ltYield": 5.55}]})
    monkeypatch.setattr(rate_path.macro, "liquidity", lambda: [{"date": "2026-11-12", "treps": 5.35}])
    d = rate_path.india(date(2026, 11, 13))
    assert d["available"] and d["olderBills"] == 2 and d["windows"][0]["billYield"] == 5.55   # live price beats the recorded one
