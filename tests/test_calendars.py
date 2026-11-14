"""Results calendar, IPOs and corporate actions ahead, against NSE's shapes as measured on 13 Nov 2026."""
from datetime import date

from orazio import corp_calendar, earnings

EVENT = {"symbol": "TCS", "company": "Tata Consultancy Services", "purpose": "Financial Results",
         "bm_desc": "To consider the financial results", "date": "14-Nov-2026"}


def test_calendar_keeps_upcoming_results_meetings_and_filters_to_symbols(monkeypatch):
    rows = [EVENT, {**EVENT, "symbol": "INFY", "date": "20-Nov-2026"}, {**EVENT, "symbol": "OLD", "date": "01-Nov-2026"},
            {**EVENT, "symbol": "FUND", "purpose": "Fund Raising", "bm_desc": "To raise funds"}]
    monkeypatch.setattr(earnings, "nse_get", lambda *a, **k: rows)
    got = earnings.calendar(today=date(2026, 11, 13))
    assert [r["symbol"] for r in got["rows"]] == ["TCS", "INFY"] and got["rows"][0]["chartSymbol"] == "TCS.NS"
    assert [r["symbol"] for r in earnings.calendar(["infy.ns"], today=date(2026, 11, 13))["rows"]] == ["INFY"]


def test_calendar_reports_nse_down(monkeypatch):
    monkeypatch.setattr(earnings, "nse_get", lambda *a, **k: None)
    assert earnings.calendar() == {"available": False, "rows": []}


def test_ipos_shape_open_issues_and_recent_listings(monkeypatch):
    cur = [{"symbol": "NEWCO", "companyName": "New Co Ltd", "series": "EQ", "issueStartDate": "12-Nov-2026", "issueEndDate": "14-Nov-2026",
            "issuePrice": "Rs.100 to Rs.105", "noOfTime": "3.52", "lotSize": "142"}]
    past = [{"symbol": "OLDA", "companyName": "Old A", "issuePrice": "94", "listingDate": "09-NOV-2026", "securityType": "SME"},
            {"symbol": "OLDB", "companyName": "Old B", "issuePrice": "120", "listingDate": "12-NOV-2026", "securityType": "EQ"}]
    pages = {"/api/ipo-current-issue": cur, "/api/public-past-issues": past}
    monkeypatch.setattr(corp_calendar, "nse_get", lambda path, params=None: pages.get(path, []))
    d = corp_calendar.ipos()
    assert d["issues"] == [{"symbol": "NEWCO", "company": "New Co Ltd", "status": "open", "kind": "EQ", "open": "2026-11-12", "close": "2026-11-14",
                            "priceBand": "Rs.100 to Rs.105", "sizeText": None, "subscribed": 3.52, "lotSize": 142.0}]
    assert [r["symbol"] for r in d["listings"]] == ["OLDB", "OLDA"] and d["listings"][0]["issuePrice"] == 120.0


def test_actions_ahead_keep_equities_and_name_the_kind(monkeypatch):
    rows = [{"symbol": "ASTRAL", "series": "EQ", "comp": "Astral", "exDate": "13-Nov-2026", "recDate": "13-Nov-2026",
             "subject": "Interim Dividend - Rs 1.50 Per Share"},
            {"symbol": "X", "series": "EQ", "comp": "X", "exDate": "20-Nov-2026", "recDate": "-", "subject": "Buy Back"},
            {"symbol": "679GS2027", "series": "GS", "comp": "GOI", "exDate": "13-Nov-2026", "subject": "Interest Payment"}]
    monkeypatch.setattr(corp_calendar, "nse_get", lambda *a, **k: rows)
    d = corp_calendar.actions(today=date(2026, 11, 13))
    assert [(r["symbol"], r["kind"]) for r in d["rows"]] == [("ASTRAL", "dividend"), ("X", "buyback")] and d["rows"][1]["record"] is None
    assert corp_calendar.action_kind("Bonus 3:2") == "bonus" and corp_calendar.action_kind("Face Value Split (Sub-Division)") == "split"
