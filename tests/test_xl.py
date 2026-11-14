"""Spreadsheet links: one value as bare text for =WEBSERVICE, tables as CSV, formula-looking text defused."""
from orazio.routes import xl


def test_safe_cell_defuses_formulas_but_keeps_negative_numbers():
    assert xl.safe_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)" and xl.safe_cell("@x") == "'@x" and xl.safe_cell("-cmd") == "'-cmd"
    assert xl.safe_cell("-1.5") == "-1.5" and xl.safe_cell(None) == "" and xl.safe_cell(2415.7) == "2415.7"


def test_quote_returns_one_bare_value_or_a_csv(client, monkeypatch):
    monkeypatch.setattr(xl, "_get", lambda path: {"price": 2415.7, "changePercent": -1.09, "symbol": path.split("=")[1]})
    assert client.get("/xl/quote?s=TCS.NS&f=price").get_data(as_text=True) == "2415.7"
    body = client.get("/xl/quote?s=TCS.NS,INFY.NS&f=symbol,price").get_data(as_text=True)
    assert body == "symbol,price\nTCS.NS,2415.7\nINFY.NS,2415.7\n"
    assert client.get("/xl/quote").status_code == 400


def test_history_is_dated_csv(client, monkeypatch):
    monkeypatch.setattr(xl, "_get", lambda path: {"candles": [{"time": 1794470400, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}]})
    assert client.get("/xl/history?s=NIFTY").get_data(as_text=True) == "date,open,high,low,close,volume\n2026-11-12,1,2,0.5,1.5,10\n"
