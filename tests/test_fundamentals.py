"""Fundamentals: statements from yfinance frames, TTM and YoY rules, computed ratios, peers, currency conversion."""
import pandas as pd

from orazio import fundamentals as f

Q = [{"period": "2025-09-30", "revenue": 100.0, "netIncome": 10.0, "eps": 2.0, "ebitda": 20.0},
     {"period": "2025-12-31", "revenue": 110.0, "netIncome": 11.0, "eps": 2.2, "ebitda": 22.0},
     {"period": "2026-03-31", "revenue": 120.0, "netIncome": 12.0, "eps": 2.4, "ebitda": 24.0},
     {"period": "2026-06-30", "revenue": 125.0, "netIncome": 12.5, "eps": 2.5, "ebitda": 25.0},
     {"period": "2026-09-30", "revenue": 130.0, "netIncome": 13.0, "eps": 2.6, "ebitda": 26.0}]
A = [{"period": "2025-03-31", "revenue": 380.0, "netIncome": 38.0, "eps": 7.6, "ebitda": 76.0},
     {"period": "2026-03-31", "revenue": 440.0, "netIncome": 44.0, "eps": 8.8, "ebitda": 88.0}]
B = [{"period": "2026-03-31", "equity": 200.0, "totalDebt": 50.0, "cash": 30.0, "totalAssets": 400.0}]


def test_statement_reads_a_yfinance_frame_oldest_first_in_crore():
    df = pd.DataFrame({pd.Timestamp("2026-09-30"): [7.3e11, 38.37], pd.Timestamp("2026-06-30"): [7.2e11, None]},
                      index=["Total Revenue", "Diluted EPS"])
    assert f.statement(df, (("Total Revenue", "revenue"), ("Diluted EPS", "eps"))) == [
        {"period": "2026-06-30", "revenue": 72000.0, "eps": None}, {"period": "2026-09-30", "revenue": 73000.0, "eps": 38.37}]
    assert f.statement(None, f.INCOME) == []


def test_ttm_uses_four_consecutive_quarters_else_the_last_year():
    assert f.ttm(Q, A, "eps") == 2.2 + 2.4 + 2.5 + 2.6
    gappy = [Q[0], Q[1], Q[3], Q[4]]                       # Yahoo skips a quarter: span > 290 days
    assert f.ttm(gappy, A, "eps") == 8.8


def test_yoy_matches_the_same_quarter_a_year_earlier():
    assert f.yoy(Q, A) == 30.0                             # 130 vs 100
    assert f.yoy(Q[1:], A) == round((440 / 380 - 1) * 100, 2)   # no year-ago quarter: annual


def test_ratios_from_statements_with_info_only_filling_gaps():
    # price 100, 10 Cr shares -> market cap ₹1,000 Cr; TTM EPS 9.7, net income 48.5, revenue 485, EBITDA 97
    r = f.ratios(Q, A, B, 100.0, 1e8, {"beta": 0.8, "trailingPE": 999})
    assert r["marketCapCr"] == 1000 and r["pe"] == round(100 / 9.7, 2) and r["pb"] == 5.0
    assert r["roe"] == round(48.5 / 200 * 100, 2) and r["margin"] == 10.0
    assert r["evEbitda"] == round((1000 + 50 - 30) / 97, 2) and r["debtToEquity"] == 0.25 and r["revenueGrowth"] == 30.0
    assert r["beta"] == 0.8 and r["bookValue"] == 20.0
    loss = [{**p, "eps": -1.0} for p in Q]
    assert f.ratios(loss, A, B, 100.0, 1e8, {"trailingPE": 12.0})["pe"] == 12.0   # no P/E on a loss: info's, if any


def test_convert_multiplies_amounts_but_not_the_period():
    assert f.convert([{"period": "2026-09-30", "revenue": 10.0, "eps": 0.2, "x": None}], 94.0) == [
        {"period": "2026-09-30", "revenue": 940.0, "eps": 18.8, "x": None}]


def test_parse_list_and_pick_peers_nearest_in_size():
    text = "﻿Company Name,Industry,Symbol,Series,ISIN Code\nA Ltd,IT,AAA,EQ,X\nB Ltd,IT,BBB,EQ,X\nC Ltd,IT,CCC,EQ,X\nD Ltd,Banks,DDD,EQ,X\n"
    listing = f.parse_list(text)
    assert listing["AAA"] == ("A Ltd", "IT") and len(listing) == 4
    assert f.pick_peers("AAA", listing, {"AAA": 100, "BBB": 1000, "CCC": 120}) == ["CCC", "BBB"]
    assert f.pick_peers("ZZZ", listing, {}) == []


def test_failed_fetches_are_not_cached(monkeypatch):
    calls = []

    class Boom:
        def __init__(self, s):
            calls.append(s)

        @property
        def info(self):
            raise RuntimeError("429")
    monkeypatch.setattr(f.yf, "Ticker", Boom)
    assert f._info("TCS.NS") == {} and f._info("TCS.NS") == {}
    assert len(calls) == 2                                 # retried, not pinned for six hours
