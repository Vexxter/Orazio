"""Filings feed, keyword alerts and shareholding, against NSE's response shapes as measured on 2 Nov 2026."""
import io

import pytest
from pypdf import PdfWriter as filings_pdf_writer

from orazio import alerts, filings

RAW = {"an_dt": "02-Nov-2026 12:28:53", "attchmntFile": "https://nsearchives.nseindia.com/corporate/X.pdf", "attchmntText": "Press release on Financial Results for the quarter",
       "desc": "Press Release", "fileSize": "620.67 KB", "hasXbrl": True, "seq_id": "1", "sm_name": "Capillary Technologies", "sort_date": "2026-11-02 12:28:53", "symbol": "CAPILLARY"}


def row(**k):
    return {**filings.shape(RAW), **k}


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(alerts, "STORE", tmp_path / "alerts.json")


def test_shape_keeps_the_filing_link():
    r = filings.shape(RAW)
    assert r["id"] == "1" and r["chartSymbol"] == "CAPILLARY.NS" and r["pdf"].endswith("X.pdf") and r["category"] == "Press Release"


def test_recent_handles_nse_being_down(monkeypatch):
    monkeypatch.setattr(filings, "nse_get", lambda *a, **k: None)
    assert filings.query() == {"available": False, "rows": []}


def test_query_is_one_market_wide_call_filtered_locally(monkeypatch):
    calls = []
    other = {**RAW, "symbol": "RELIANCE", "seq_id": "2", "attchmntText": "Transcript of the analyst call", "desc": "Analysts/Institutional Investor Meet", "sort_date": "2026-11-02 13:00:00"}

    def get(path, params):
        calls.append(params)
        return [RAW, other]
    monkeypatch.setattr(filings, "nse_get", get)
    assert [r["symbol"] for r in filings.query()["rows"]] == ["RELIANCE", "CAPILLARY"]          # newest first
    assert [r["symbol"] for r in filings.query(["RELIANCE.NS"])["rows"]] == ["RELIANCE"]
    assert [r["symbol"] for r in filings.query(q="results, nothing")["rows"]] == ["CAPILLARY"]
    assert len(calls) == 1 and "symbol" not in calls[0]


def test_matching_is_case_insensitive_and_scoped_to_symbols():
    r = row()
    assert filings.matches(r, ["financial results"], set()) and filings.matches(r, [], {"CAPILLARY"})
    assert not filings.matches(r, ["merger"], set()) and not filings.matches(r, ["results"], {"TCS"})


def test_watch_stays_quiet_on_first_run_then_sends_only_new_matches(monkeypatch):
    alerts.set_filing_watch(["results"], [])
    rows = [row()]
    monkeypatch.setattr(filings, "recent", lambda: rows)
    sent = []
    filings.check_watch(lambda t, b: sent.append(t))
    assert sent == []                                                         # first run: just remembers what's there
    rows.insert(0, row(id="9", symbol="TCS"))
    rows.insert(0, row(id="10", symbol="INFY", text="Board meeting", category="Board"))   # new, but no keyword
    filings.check_watch(lambda t, b: sent.append(t))
    filings.check_watch(lambda t, b: sent.append(t))
    assert sent == ["Filing: TCS · Press Release"]
    assert alerts.read()["log"][0]["kind"] == "filing"


def test_shareholding_is_oldest_first_with_the_quarterly_change(monkeypatch):
    raw = [{"date": "30-SEP-2026", "pr_and_prgrp": "50.44", "public_val": "49.56", "employeeTrusts": "0", "broadcastDate": "21-OCT-2026 16:25:15"},
           {"date": "30-JUN-2026", "pr_and_prgrp": "50.48", "public_val": "49.52", "employeeTrusts": "0", "broadcastDate": "16-JUL-2026 19:24:44"},
           {"date": "not a date"}]
    monkeypatch.setattr(filings, "nse_get", lambda *a, **k: raw)
    d = filings.shareholding("RELIANCE.NS")
    assert d["symbol"] == "RELIANCE" and d["asOf"] == "2026-09-30" and [r["period"] for r in d["rows"]] == ["2026-06-30", "2026-09-30"]
    assert d["rows"][1]["promoterChange"] == -0.04 and "promoterChange" not in d["rows"][0]


def test_routes_carry_provenance(client, monkeypatch):
    monkeypatch.setattr(filings, "recent", lambda: [row()])
    d = client.get("/api/filings?symbols=CAPILLARY.NS&q=results").get_json()
    assert d["rows"][0]["symbol"] == "CAPILLARY" and d["provenance"]["feed"] == "filings"


# ---- reading one filing -----------------------------------------------------------
@pytest.mark.parametrize("url", ["http://nsearchives.nseindia.com/a.pdf", "https://evil.example/a.pdf", "https://nsearchives.nseindia.com.evil.example/a.pdf",
                                 "https://nsearchives.nseindia.com/a.exe", "file:///etc/passwd", "https://127.0.0.1/a.pdf", "", None])
def test_only_pdfs_on_nse_are_ever_fetched(url, monkeypatch):
    monkeypatch.setattr(filings.nse_http, "get", lambda *a, **k: pytest.fail("fetched a URL it should have refused"))
    with pytest.raises(ValueError):
        filings.filing_text(url)


def test_a_broken_or_textless_pdf_says_so():
    with pytest.raises(ValueError):
        filings.pdf_pages(b"not a pdf")
    writer = filings_pdf_writer()
    writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)
    assert filings.pdf_pages(buf.getvalue()) == []


def test_the_text_route_is_for_this_machine_and_a_bad_link_does_not_mark_the_feed_failing(client):
    from orazio import provenance
    provenance._health.clear()
    assert client.get("/api/filings/text?url=x", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/filings/text?url=https://evil.example/a.pdf").status_code == 400
    assert "filings" not in provenance._health
