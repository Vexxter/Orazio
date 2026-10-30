"""Institutional flows: NSE's FII/DII rows and participant-wise OI CSV parse into the numbers the tab shows."""
from orazio import flows

CSV = '''""Participant wise Open Interest (no. of contracts) in Equity Derivatives as on Oct 29, 2026"",,,,,,,,,,,,,,
Client Type,Future Index Long,Future Index Short,Future Stock Long,Future Stock Short       ,Option Index Call Long,Option Index Put Long,Option Index Call Short,Option Index Put Short,Option Stock Call Long,Option Stock Put Long,Option Stock Call Short,Option Stock Put Short,Total Long Contracts      ,Total Short Contracts
Client,252605,59713,3295677,212487,2567384,3113774,2649861,3591028,1233326,679086,825752,826660,11141852,8165501
FII,35686,273709,3582236,2661993,601754,1106135,825247,651177,130552,189439,195792,122609,5645802,4730527
TOTAL,362467,362467,7892000,7892000,4225986,5375722,4225986,5375722,2130706,1688153,2130706,1688153,21675034,21675034
'''


def test_participant_oi_csv_parses_and_summarises():
    t = flows.parse_participant_oi(CSV)
    assert t["FII"]["future_index_long"] == 35686
    assert t["FII"]["future_stock_short"] == 2661993          # header had trailing spaces
    s = flows.summarise("2026-10-29", t)
    assert s["FII"]["futIdxNet"] == 35686 - 273709
    assert s["FII"]["futIdxLongPct"] == 11.5
    assert s["FII"]["putIdxNet"] == 1106135 - 651177
    assert s["DII"]["futIdxNet"] == 0 and s["DII"]["futIdxLongPct"] is None   # party missing from the file


def test_html_404_page_is_not_a_table():
    assert flows.parse_participant_oi("<!DOCTYPE html><html>\n<head>\n</head>") is None


def test_fiidii_rows_key_by_iso_date_and_party():
    out = flows.parse_fiidii([
        {"buyValue": "18458.64", "category": "DII", "date": "29-Oct-2026", "netValue": "1924.41", "sellValue": "16534.23"},
        {"buyValue": "13,400.29", "category": "FII/FPI", "date": "29-Oct-2026", "netValue": "-943.6", "sellValue": "14343.89"},
        {"category": "FII/FPI", "date": "bad"},
    ])
    assert out == {"2026-10-29": {"dii": {"buy": 18458.64, "sell": 16534.23, "net": 1924.41},
                                  "fii": {"buy": 13400.29, "sell": 14343.89, "net": -943.6}}}
