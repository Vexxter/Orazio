from orazio.cas import breadth_from_all_indices


def test_maps_the_three_tracked_nse_indices():
    payload = {"data": [
        {"index": "NIFTY 50", "advances": "35", "declines": "15", "unchanged": "0"},
        {"index": "NIFTY BANK", "advances": "8", "declines": "4", "unchanged": "0"},
        {"index": "NIFTY IT", "advances": "5", "declines": "5", "unchanged": "0"},
        {"index": "NIFTY MIDCAP 100", "advances": "50", "declines": "50", "unchanged": "0"},
    ]}
    rows = breadth_from_all_indices(payload)
    aliases = {r["alias"]: r for r in rows}
    assert set(aliases) == {"NIFTY", "BANKNIFTY", "NIFTYIT"}
    assert aliases["NIFTY"] == {"alias": "NIFTY", "advances": 35, "declines": 15, "unchanged": 0}


def test_skips_an_index_missing_from_the_payload():
    payload = {"data": [{"index": "NIFTY 50", "advances": "35", "declines": "15", "unchanged": "0"}]}
    rows = breadth_from_all_indices(payload)
    assert [r["alias"] for r in rows] == ["NIFTY"]


def test_skips_a_row_with_unparseable_counts_instead_of_reporting_zero():
    payload = {"data": [{"index": "NIFTY 50", "advances": None, "declines": "15", "unchanged": "0"}]}
    assert breadth_from_all_indices(payload) == []


def test_handles_empty_or_missing_payload():
    assert breadth_from_all_indices(None) == []
    assert breadth_from_all_indices({}) == []
