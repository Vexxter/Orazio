"""Corporate-action gap-fill, company names, and the NSE stats shown in the legend."""
from datetime import datetime

import pytest

from orazio import corporate_actions as ca
from orazio import names, stats
from orazio.constants import IST


# ---- corporate actions ---------------------------------------------------------
def ex_epoch(day):
    return int(datetime.strptime(day, "%d-%b-%Y").replace(tzinfo=IST).timestamp())


def test_split_ratio_is_old_face_value_over_new():
    assert ca._extract_split_ratio("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share") == 5.0
    assert ca._extract_split_ratio("Face Value Split - From Rs 5/- To Rs 1/-") == 5.0
    assert ca._extract_split_ratio("Dividend - Rs 5 Per Share") is None


def test_bonus_ratio_is_the_new_holding_multiple():
    assert ca._extract_bonus_ratio("Bonus Issue 1:1") == 2.0
    assert ca._extract_bonus_ratio("Bonus issue 1:2") == 1.5
    assert ca._extract_bonus_ratio("Bonus issue 4:1") == 5.0
    assert ca._extract_bonus_ratio("Bonus Issue") is None


def test_factors_keep_bonus_and_split_and_skip_preference_shares_and_junk(monkeypatch):
    monkeypatch.setattr(ca, "_fetch_actions", lambda sym: [
        {"subject": "Bonus Issue 1:1", "exDate": "28-Oct-2024"},
        {"subject": "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share", "exDate": "01-Jun-2020"},
        {"subject": "Bonus issue of NCRPS 1:1", "exDate": "02-Jan-2022"},        # preference shares: not a price event
        {"subject": "Dividend - Rs 10", "exDate": "03-Mar-2023"},
        {"subject": "Bonus Issue 1:1", "exDate": "not a date"},
        {"subject": "", "exDate": "03-Mar-2023"},
    ])
    f = ca.factors_for("X")
    assert [x["kind"] for x in f] == ["Split", "Bonus"]                    # oldest first
    assert f[0]["priceFactor"] == pytest.approx(0.2) and f[0]["volumeFactor"] == 5.0
    assert f[1]["priceFactor"] == pytest.approx(0.5) and f[1]["volumeFactor"] == 2.0


def test_adjust_rows_scales_only_bars_before_the_ex_date_and_compounds_actions():
    ex = ex_epoch("28-Oct-2024")
    rows = [{"time": ex - 100, "open": 100.0, "high": 110.0, "low": 90.0, "close": 100.0, "volume": 10.0},
            {"time": ex + 100, "open": 50.0, "high": 55.0, "low": 45.0, "close": 50.0, "volume": 20.0}]
    ca.adjust_rows(rows, [{"exEpoch": ex, "priceFactor": 0.5, "volumeFactor": 2.0}])
    assert rows[0]["close"] == 50.0 and rows[0]["high"] == 55.0 and rows[0]["volume"] == 20.0
    assert rows[1]["close"] == 50.0 and rows[1]["volume"] == 20.0           # on/after the ex-date: untouched
    twice = [{"time": 1, "open": 8.0, "high": 8.0, "low": 8.0, "close": 8.0, "volume": 1.0}]
    ca.adjust_rows(twice, [{"exEpoch": 5, "priceFactor": 0.5, "volumeFactor": 2.0}, {"exEpoch": 9, "priceFactor": 0.5, "volumeFactor": 2.0}])
    assert twice[0]["close"] == 2.0 and twice[0]["volume"] == 4.0


def test_adjust_rows_with_no_factors_is_a_no_op():
    rows = [{"time": 1, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}]
    assert ca.adjust_rows(rows, []) is rows and rows[0]["close"] == 1.0


def test_only_actions_yahoo_has_not_already_applied_are_returned(monkeypatch):
    # Yahoo's auto-adjusted history already contains the Oct 2024 bonus; applying it again would halve prices twice.
    ex = ex_epoch("28-Oct-2024")
    monkeypatch.setattr(ca, "factors_for", lambda sym: [{"exEpoch": ex, "priceFactor": 0.5, "volumeFactor": 2.0},
                                                       {"exEpoch": ex_epoch("29-Sep-2026"), "priceFactor": 0.5, "volumeFactor": 2.0}])
    monkeypatch.setattr(ca, "_yahoo_known_splits", lambda sym: {ex + 3600: 2.0})        # an hour off: still the same event
    gap = ca.unmatched_factors("RELIANCE.NS", "RELIANCE")
    assert [g["exEpoch"] for g in gap] == [ex_epoch("29-Sep-2026")]                     # only the one Yahoo hasn't caught up to


def test_a_different_ratio_on_the_same_date_is_not_treated_as_already_applied(monkeypatch):
    ex = ex_epoch("28-Oct-2024")
    monkeypatch.setattr(ca, "factors_for", lambda sym: [{"exEpoch": ex, "priceFactor": 0.5, "volumeFactor": 2.0}])
    monkeypatch.setattr(ca, "_yahoo_known_splits", lambda sym: {ex: 5.0})
    assert len(ca.unmatched_factors("X.NS", "X")) == 1


def test_when_yahoos_split_history_is_unreachable_apply_nothing(monkeypatch):
    monkeypatch.setattr(ca, "factors_for", lambda sym: [{"exEpoch": 1, "priceFactor": 0.5, "volumeFactor": 2.0}])
    monkeypatch.setattr(ca, "_yahoo_known_splits", lambda sym: None)
    assert ca.unmatched_factors("X.NS", "X") == []


def test_only_plain_nse_equities_are_adjusted():
    assert ca.nse_equity_symbol("RELIANCE.NS") == "RELIANCE"
    for other in ("^NSEI", "AAPL", "RELIANCE.BO", "NIFTY-FUT"):
        assert ca.nse_equity_symbol(other) is None
    rows = [{"time": 1}]
    assert ca.adjust_candles_for_splits("AAPL", rows) is rows


def test_a_corporate_action_lookup_failure_never_breaks_the_chart(monkeypatch):
    monkeypatch.setattr(ca, "unmatched_factors", lambda *a: (_ for _ in ()).throw(RuntimeError("NSE down")))
    rows = [{"time": 1, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}]
    assert ca.adjust_candles_for_splits("X.NS", rows) is rows


# ---- company names -----------------------------------------------------------------
@pytest.fixture
def clean_names():
    names._cache.clear()
    yield
    names._cache.clear()


def test_attach_names_sets_name_from_the_lookup(clean_names, monkeypatch):
    monkeypatch.setattr(names, "english_name", lambda sym: {"688185.SS": "CanSino Biologics Inc."}.get(sym))
    rows = [{"chartSymbol": "688185.SS"}, {"chartSymbol": "999999.SS"}, {"symbol": "no-chart-symbol"}]
    names.attach_names(rows)
    assert rows[0]["name"] == "CanSino Biologics Inc."
    assert rows[1]["name"] is None                          # looked up, nothing found
    assert "name" not in rows[2]


def test_a_found_name_is_cached_for_a_week_and_a_miss_only_briefly(clean_names):
    import time
    names._cache["A"] = ("Alpha Ltd", time.time() - 6 * 86400)
    assert names._cached("A") is not None
    names._cache["A"] = ("Alpha Ltd", time.time() - 8 * 86400)
    assert names._cached("A") is None
    names._cache["B"] = (None, time.time() - 60)
    assert names._cached("B") is not None                   # a recent miss is remembered (don't hammer Yahoo)
    names._cache["B"] = (None, time.time() - 600)
    assert names._cached("B") is None                       # ...but retried after 5 minutes


def test_english_name_prefers_the_long_name_and_survives_network_errors(clean_names, monkeypatch):
    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"quotes": [{"symbol": "OTHER", "longname": "Wrong"}, {"symbol": "3518.TW", "longname": "Paragon Technologies Co., Ltd.", "shortname": "PARAGON"}]}
    monkeypatch.setattr(names.requests, "get", lambda *a, **k: R())
    assert names.english_name("3518.TW") == "Paragon Technologies Co., Ltd."
    assert names.english_name("MISSING.TW") is None         # no exact-symbol match: never guess another company's name
    def boom(*a, **k): raise names.requests.RequestException("down")
    monkeypatch.setattr(names.requests, "get", boom)
    assert names.english_name("ANY.NS") is None


# ---- NSE stats (legend) -------------------------------------------------------------
ROW = {"totalTradedVolume": 468_837_809, "totalTradedValue": 462_597_606_964.82, "yearHigh": 26373.2, "yearLow": 22182.55,
       "perChange30d": -6.04, "perChange365d": -7.79, "lastUpdateTime": "2026-09-29 15:39:59"}


def test_shape_renames_nse_fields_for_the_ui():
    s = stats._shape(ROW)
    assert s == {"volume": 468_837_809, "value": 462_597_606_964.82, "yearHigh": 26373.2, "yearLow": 22182.55,
                 "change30d": -6.04, "change365d": -7.79, "asOf": "2026-09-29 15:39:59"}


def test_stats_for_indices_stocks_and_everything_else(monkeypatch):
    monkeypatch.setattr(stats, "_index_stats", lambda name: {"index": name})
    monkeypatch.setattr(stats, "_stock_map", lambda: {"RELIANCE": {"stock": "RELIANCE"}})
    assert stats.stats_for("^NSEI") == {"index": "NIFTY 50"}
    assert stats.stats_for("^NSEBANK") == {"index": "NIFTY BANK"}
    assert stats.stats_for("RELIANCE.NS") == {"stock": "RELIANCE"}
    assert stats.stats_for("TINY.NS") is None               # not in the NSE universe
    assert stats.stats_for("^GSPC") is None                 # not an NSE symbol at all


def test_index_stats_picks_the_index_row_not_a_constituent(monkeypatch):
    rows = [{"priority": 0, "symbol": "RELIANCE", **ROW, "totalTradedVolume": 1}, {"priority": 1, "symbol": "NIFTY 50", **ROW}]
    monkeypatch.setattr(stats, "_rows", lambda name: rows)
    assert stats._index_stats("NIFTY 50")["volume"] == 468_837_809


def test_constituents_exclude_the_index_row_and_non_equity_series(monkeypatch):
    rows = [{"priority": 1, "symbol": "NIFTY 50"}, {"priority": 0, "symbol": "RELIANCE", "series": "EQ"},
            {"priority": 0, "symbol": "JUNK", "series": "BE"}, {"priority": 0, "symbol": None, "series": "EQ"}]
    monkeypatch.setattr(stats, "_rows", lambda name: rows)
    assert stats.constituent_symbols("NIFTY 50") == ["RELIANCE.NS"]


def test_rows_survive_nse_returning_an_empty_object(monkeypatch):
    monkeypatch.setattr(stats, "nse_get", lambda *a, **k: {"data": {}})     # what NSE sends for an unknown index name
    assert stats._rows("NIFTY TOTAL MARKET") == []
    monkeypatch.setattr(stats, "nse_get", lambda *a, **k: None)
    assert stats._rows("NIFTY 50") == []
