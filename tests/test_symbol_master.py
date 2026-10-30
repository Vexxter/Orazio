"""The search box's local symbol list: NSE stocks, F&O futures, rail aliases with synonyms, bonds."""
from orazio import symbol_master

CSV = (
    "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
    "RELIANCE,Reliance Industries Limited,EQ,29-NOV-1995,10,1,INE002A01018,10\n"
    "M&M,Mahindra & Mahindra Limited,EQ,01-JAN-1990,5,1,INE101A01026,5\n"
    "OBSCURE,Obscure Limited,BE,01-JAN-2000,10,1,INE000000000,10\n"
    "SKIPPED,Skipped Limited,GB,01-JAN-2000,10,1,INE000000001,10\n"
)


def by_symbol(items):
    return {it["symbol"]: it for it in items}


def test_parse_equity_csv_reads_padded_headers():
    assert symbol_master.parse_equity_csv(CSV)[:2] == [
        ("RELIANCE", "Reliance Industries Limited", "EQ"), ("M&M", "Mahindra & Mahindra Limited", "EQ")]
    assert symbol_master.parse_equity_csv("garbage\n1,2") == []


def test_build_ranks_fno_stocks_above_plain_and_adds_their_futures():
    items = by_symbol(symbol_master.build(CSV, {"RELIANCE": "RELIANCE INDUSTRIES LTD"}))
    rel = items["RELIANCE.NS"]
    assert (rel["ticker"], rel["exch"], rel["type"], rel["pop"], rel["fno"]) == ("RELIANCE", "NSE", "stock", 7, True)
    assert items["M&M.NS"]["pop"] == 5 and "fno" not in items["M&M.NS"]
    assert items["OBSCURE.NS"]["pop"] == 2
    ranked = by_symbol(symbol_master.build(CSV, {"RELIANCE": "x"}, nifty50={"RELIANCE"}, nifty500={"M&M"}))
    assert ranked["RELIANCE.NS"]["pop"] == 8 and ranked["M&M.NS"]["pop"] == 6
    assert "SKIPPED.NS" not in items
    assert items["RELIANCE-FUT"]["name"] == "Reliance Industries Limited Futures"   # CSV name, not NSE's caps
    assert items["RELIANCE-FUT"]["type"] == "future"


def test_aliases_carry_their_synonyms_and_bonds_are_listed():
    items = by_symbol(symbol_master.build("", {}))
    assert {"CL=F", "WTI", "USOIL"} <= set(items["CRUDE"]["alt"])
    assert {"^NSEI", "NIFTY50"} <= set(items["NIFTY"]["alt"])
    assert items["NIFTY"]["type"] == "index" and items["GOLD"]["type"] == "commodity"
    assert items["NIFTY-FUT"]["type"] == "future"
    assert items["IN10Y-IN"]["ticker"] == "IN10Y" and items["US10Y"]["type"] == "bond"


def test_partial_master_is_served_but_not_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(symbol_master, "_equity_text", lambda: calls.append(1) or "")
    monkeypatch.setattr(symbol_master.fno, "fno_stocks", lambda: {})
    monkeypatch.setattr(symbol_master, "_members", lambda name: set())
    first = symbol_master.master()
    symbol_master.master()
    assert "NIFTY" in by_symbol(first) and len(calls) == 2


def test_symbols_route(client, monkeypatch):
    monkeypatch.setattr(symbol_master, "master", lambda: [{"symbol": "NIFTY"}])
    assert client.get("/api/symbols").get_json() == [{"symbol": "NIFTY"}]
