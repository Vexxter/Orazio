from orazio.constituents import summarize, top_movers, total_volume


def _row(prev, last, open_=None, high=None, low=None, volume=None):
    return {
        "prevClose": prev, "last": last,
        "open": open_ if open_ is not None else prev,
        "high": high if high is not None else max(prev, last),
        "low": low if low is not None else min(prev, last),
        "volume": volume if volume is not None else 1000,
    }


def test_summarize_counts_advances_declines_and_unchanged():
    data = {
        "A": _row(100.0, 105.0),   # up
        "B": _row(100.0, 95.0),    # down
        "C": _row(100.0, 100.0),   # flat
        "D": _row(50.0, 51.0),     # up
    }
    assert summarize(data) == {"advances": 2, "declines": 1, "unchanged": 1}


def test_summarize_skips_missing_rows_instead_of_counting_them():
    data = {"A": _row(100.0, 105.0), "B": None}
    assert summarize(data) == {"advances": 1, "declines": 0, "unchanged": 0}


def test_summarize_empty_input():
    assert summarize({}) == {"advances": 0, "declines": 0, "unchanged": 0}


def test_top_movers_ranks_by_percent_change_and_strips_ticker_suffix():
    data = {
        "AAA.NS": _row(100.0, 110.0),   # +10%
        "BBB.NS": _row(100.0, 90.0),    # -10%
        "CCC.NS": _row(200.0, 202.0),   # +1%
        "DDD.NS": _row(50.0, 40.0),     # -20%
    }
    result = top_movers(data, n=2)
    assert [r["symbol"] for r in result["gainers"]] == ["AAA", "CCC"]
    assert [r["symbol"] for r in result["losers"]] == ["DDD", "BBB"]
    assert result["gainers"][0]["perChange"] == 10.0


def test_top_movers_skips_missing_or_zero_prev_close():
    data = {"A": _row(100.0, 110.0), "B": None, "C": _row(0, 5)}
    result = top_movers(data, n=5)
    symbols = {r["symbol"] for r in result["gainers"]} | {r["symbol"] for r in result["losers"]}
    assert symbols == {"A"}


def test_total_volume_sums_available_constituents():
    data = {
        "A": _row(100.0, 105.0, volume=1000),
        "B": _row(100.0, 95.0, volume=2500),
        "C": None,
    }
    assert total_volume(data) == 3500


def test_total_volume_skips_rows_with_no_volume():
    # _row()'s volume=None means "use the 1000 default", not "no volume" — build the
    # no-volume row directly to exercise that case.
    no_volume_row = {"prevClose": 100.0, "last": 95.0, "open": 100.0, "high": 100.0, "low": 95.0, "volume": None}
    data = {"A": _row(100.0, 105.0, volume=1000), "B": no_volume_row}
    assert total_volume(data) == 1000


def test_total_volume_none_when_nothing_usable():
    assert total_volume({"A": None}) is None
    assert total_volume({}) is None
