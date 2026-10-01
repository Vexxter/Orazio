"""Up/down counts (NASDAQ, TAIEX, SSE) and the movers tables for markets NSE doesn't cover."""
import pytest

from orazio import global_movers as gm
from orazio import market_breadth as mb


# ---- market_breadth parsers --------------------------------------------------
def test_nasdaq100_counts_up_down_and_unchanged():
    rows = [{"deltaIndicator": "up"}] * 3 + [{"deltaIndicator": "down"}] * 2 + [{"deltaIndicator": "none"}, {}]
    assert mb.parse_nasdaq100({"data": {"data": {"rows": rows}}}) == {"advances": 3, "declines": 2, "unchanged": 2}


def test_nasdaq100_without_rows_is_unusable():
    assert mb.parse_nasdaq100({"data": {"data": {"rows": []}}}) is None


def test_twse_reads_the_stocks_column_ignoring_limit_up_brackets_and_thousands_commas():
    payload = {"tables": [
        {"fields": ["Other"], "data": []},
        {"fields": ["Type", "Overall Market", "Stocks"], "data": [
            ["Up (Limit Up)", "6,223(55)", "1,374(24)"], ["Down (Limit Down)", "6,793(74)", "586(0)"], ["Unchanged", "939", "112"]]}]}
    assert mb.parse_twse(payload) == {"advances": 1374, "declines": 586, "unchanged": 112}


def test_twse_is_none_when_a_required_row_is_missing():
    payload = {"tables": [{"fields": ["Type", "Stocks"], "data": [["Up", "5"], ["Down", "6"]]}]}
    assert mb.parse_twse(payload) is None
    assert mb.parse_twse({}) is None


def test_breadth_rows_expose_whatever_the_pollers_stored():
    with mb._lock:
        mb._rows.clear()
        mb._rows["SSE"] = {"advances": 1, "declines": 2, "unchanged": 3}
    assert mb.breadth_rows() == [{"alias": "SSE", "advances": 1, "declines": 2, "unchanged": 3}]
    mb._rows.clear()


# ---- global_movers helpers ----------------------------------------------------
@pytest.mark.parametrize("raw,expected", [("$329.40", 329.4), ("-2.66%", -2.66), ("1,234.5", 1234.5), (7, 7.0), (None, None), ("n/a", None)])
def test_num_parses_exchange_formatted_numbers(raw, expected):
    assert gm._num(raw) == expected


def test_rank_orders_gainers_and_losers_and_ignores_rows_without_a_change():
    rows = [{"symbol": s, "perChange": p} for s, p in (("A", 1.0), ("B", 5.0), ("C", -2.0), ("D", -7.0), ("E", None))]
    out = gm._rank(rows, "as of now")
    assert [r["symbol"] for r in out["gainers"]][:2] == ["B", "A"]
    assert [r["symbol"] for r in out["losers"]][:2] == ["D", "C"]
    assert out["available"] and out["asOf"] == "as of now"
    assert gm._rank([])["available"] is False


def test_rank_returns_at_most_top_n_each_way():
    rows = [{"symbol": str(i), "perChange": float(i - 50)} for i in range(100)]
    out = gm._rank(rows)
    assert len(out["gainers"]) == len(out["losers"]) == gm.TOP_N


def test_roc_date_converts_the_taiwanese_calendar():
    assert gm._roc_date("1150929") == "29 Sep 2026"
    assert gm._roc_date("garbage") is None and gm._roc_date(None) is None


# ---- Sina (Shanghai) -----------------------------------------------------------
class FakeResp:
    def __init__(self, payload=None, text="", status=200):
        self._p, self.text, self.status_code = payload, text, status

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise gm.requests.RequestException("boom")


def sina_row(code, pct, price="10.0", name="名称"):
    return {"code": code, "name": name, "trade": price, "changepercent": pct, "open": "9.5", "high": "10.5", "low": "9.0", "volume": 1000}


def test_sina_page_maps_rows_and_skips_suspended_stocks(monkeypatch):
    monkeypatch.setattr(gm.requests, "get", lambda *a, **k: FakeResp([sina_row("600519", 2.5), sina_row("600000", 0, price="0.000")]))
    rows = gm._sina_page(1, 0)
    assert len(rows) == 1                                        # trade 0 = suspended
    assert rows[0]["symbol"] == "600519" and rows[0]["chartSymbol"] == "600519.SS"
    assert rows[0]["perChange"] == 2.5 and rows[0]["localName"] == "名称"


def test_sina_page_is_none_on_network_failure(monkeypatch):
    monkeypatch.setattr(gm.requests, "get", lambda *a, **k: FakeResp(status=502))
    assert gm._sina_page(1, 0) is None


def test_sse_breadth_sweeps_every_page_and_counts_each_stock_once(monkeypatch):
    pages = {1: [sina_row("1", 1.0), sina_row("2", -1.0)],
             2: [sina_row("2", -1.0), sina_row("3", 0.0, price="5"), sina_row("4", 2.0)]}   # "2" repeats: the order shifted between calls
    monkeypatch.setattr(gm.requests, "get", lambda *a, **k: FakeResp(text='"4"'))
    monkeypatch.setattr(gm, "_sina_page", lambda page, asc: [dict(symbol=r["code"], perChange=r["changepercent"]) for r in pages[page]])
    monkeypatch.setattr(gm.math, "ceil", lambda x: 2)               # 4 stocks -> pretend 2 pages of 2
    assert gm.sse_breadth() == {"advances": 2, "declines": 1, "unchanged": 1}


def test_sse_breadth_refuses_to_report_a_skewed_partial_sweep(monkeypatch):
    monkeypatch.setattr(gm.requests, "get", lambda *a, **k: FakeResp(text='"300"'))
    monkeypatch.setattr(gm, "_sina_page", lambda page, asc: None)   # every page failed
    assert gm.sse_breadth() is None


def test_nasdaq_movers_come_from_the_nasdaq_100_rows(monkeypatch):
    rows = [{"symbol": "AAPL", "chartSymbol": "AAPL", "perChange": -2.66}, {"symbol": "LITE", "chartSymbol": "LITE", "perChange": 5.66}]
    monkeypatch.setattr(gm, "_nasdaq_rows", lambda: rows)
    out = gm.movers("NASDAQ")
    assert out["universe"] == "NASDAQ" and out["gainers"][0]["symbol"] == "LITE" and out["losers"][0]["symbol"] == "AAPL"


def test_taiex_movers_compute_percent_from_price_change_and_label_the_session(monkeypatch):
    snap = {"day": "1150929", "rows": [{"symbol": "3518", "perChange": 10.0}, {"symbol": "6908", "perChange": -9.8}]}
    monkeypatch.setattr(gm, "_twse_rows", lambda: snap)
    out = gm.movers("TAIEX")
    assert out["asOf"] == "last close 29 Sep 2026"


def test_unknown_universe_is_unavailable_not_an_error():
    assert gm.movers("MARS")["available"] is False
