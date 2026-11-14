"""Chart events: corporate-action subjects map to marker kinds; big FII days mark index charts."""
from orazio import chart_events


def test_action_kind_from_nse_subject():
    assert chart_events.action_kind("Dividend - Rs 6 Per Share") == "dividend"
    assert chart_events.action_kind("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share") == "split"
    assert chart_events.action_kind("Bonus 1:1") == "bonus"
    assert chart_events.action_kind("Annual General Meeting") is None


def test_index_events_keep_only_big_fii_days(monkeypatch):
    monkeypatch.setattr(chart_events.flows, "fii_dii", lambda: [
        {"date": "2026-10-28", "fii": {"net": -6200.5}}, {"date": "2026-10-29", "fii": {"net": -943.6}}])
    assert chart_events.events("NIFTY") == [{"date": "2026-10-28", "kind": "fii", "text": "FII net -6,200 Cr"}]
    assert chart_events.events("SPX") == []
