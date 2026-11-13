"""Insider trades (SEBI PIT), against NSE /api/corporates-pit's shape as measured on 13 Nov 2026."""
from datetime import date

from orazio import cache, chart_events, insider

RAW = {"acqMode": "Market Purchase", "acqName": "A PROMOTER", "acqfromDt": "13-Feb-2026", "acqtoDt": "13-Feb-2026", "company": "Reliance Industries Limited",
       "intimDt": "16-Feb-2026", "personCategory": "Promoter Group", "secAcq": "2320", "secType": "Equity Shares", "secVal": "32941680",
       "symbol": "RELIANCE", "tdpTransactionType": "Buy"}


def setup_function():
    cache._store.clear()


def test_shape_keeps_open_market_trades_only():
    r = insider.shape(RAW)
    assert r == {"symbol": "RELIANCE", "chartSymbol": "RELIANCE.NS", "company": "Reliance Industries Limited", "name": "A PROMOTER",
                 "category": "Promoter Group", "senior": True, "side": "buy", "qty": 2320.0, "valueCr": 3.2942, "date": "2026-02-13", "filed": "2026-02-16"}
    for mode in ("ESOP", "Off Market", "Pledge Creation", "-"):
        assert insider.shape({**RAW, "acqMode": mode}) is None
    assert insider.shape({**RAW, "secType": "Warrants"}) is None
    assert insider.shape({**RAW, "acqMode": "Market Sale"})["side"] == "sell"
    assert not insider.shape({**RAW, "personCategory": "Employees/Designated Employees"})["senior"]


def test_by_company_nets_buys_against_sells_and_counts_people():
    rows = [insider.shape(RAW), insider.shape({**RAW, "acqName": "B", "secVal": "10000000"}),
            insider.shape({**RAW, "acqMode": "Market Sale", "secVal": "50000000", "acqtoDt": "20-Feb-2026"}),
            insider.shape({**RAW, "symbol": "TCS", "secVal": "20000000"})]
    tcs, rel = insider.by_company(rows)
    assert (tcs["symbol"], tcs["netCr"]) == ("TCS", 2.0)
    assert (rel["buyCr"], rel["sellCr"], rel["netCr"], rel["buyers"], rel["sellers"], rel["last"]) == (4.29, 5.0, -0.71, 2, 1, "2026-02-20")


def test_recent_widens_the_window_and_filters_to_senior_insiders(monkeypatch):
    calls = []

    def get(path, params):
        calls.append(params)
        return {"data": [] if len(calls) == 1 else [RAW, {**RAW, "personCategory": "Other", "acqName": "C"}]}
    monkeypatch.setattr(insider, "nse_get", get)
    d = insider.recent(today=date(2026, 3, 1))
    assert [c["from_date"] for c in calls] == ["30-01-2026", "01-11-2025"]
    assert d["available"] and d["days"] == 120 and [r["name"] for r in d["rows"]] == ["A PROMOTER"] and d["latest"] == "2026-02-13"
    assert len(insider.recent(senior_only=False, today=date(2026, 3, 1))["rows"]) == 2      # same cached fetch


def test_recent_reports_nse_down(monkeypatch):
    monkeypatch.setattr(insider, "nse_get", lambda *a, **k: None)
    assert insider.recent(today=date(2026, 3, 1)) == {"available": False, "rows": [], "companies": []}


def test_chart_events_mark_senior_insider_trades(monkeypatch):
    monkeypatch.setattr(chart_events.corporate_actions, "_fetch_actions", lambda s: [])
    monkeypatch.setattr(chart_events, "nse_get", lambda *a, **k: None)
    monkeypatch.setattr(insider, "nse_get", lambda *a, **k: {"data": [RAW, {**RAW, "personCategory": "Other"}]})
    ev = chart_events.stock_events("RELIANCE")
    assert [(e["kind"], e["date"]) for e in ev] == [("insider-buy", "2026-02-13")]
    assert "₹3.29 Cr" in ev[0]["text"]
