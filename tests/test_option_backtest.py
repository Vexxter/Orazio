"""Option backtest: strikes from ATM, settlement, costs by side, date-aware lots, skipped trades. Hand-checked numbers."""
import io
import zipfile
from datetime import date

import pytest

from orazio import option_backtest as ob

FREE = {k: 0.0 for k in ob.DEFAULT_COSTS}
E1 = "2026-10-06"
#        type  expiry strike  close spot   lot  volume
ENTRY = [["CE", E1, 24900.0, 180.0, 25010.0, 75, 100], ["PE", E1, 24900.0, 60.0, 25010.0, 75, 100],
         ["CE", E1, 25000.0, 100.0, 25010.0, 75, 100], ["PE", E1, 25000.0, 90.0, 25010.0, 75, 100],
         ["CE", E1, 25100.0, 50.0, 25010.0, 75, 100], ["PE", E1, 25100.0, 140.0, 25010.0, 75, 0]]
EXPIRY = [["CE", E1, 25000.0, 120.0, 25120.0, 75, 100], ["PE", E1, 25000.0, 0.05, 25120.0, 75, 100]]


def legs(text):
    return ob.parse_legs(text)


def test_short_straddle_pnl_is_premium_kept_less_the_settled_value():
    t = ob.run_trade(ENTRY, EXPIRY, E1, legs("SELL CE 0, SELL PE 0"), 1, FREE)
    # Sold 100 + 90 = 190; settled at 120 + 0. Kept 70 points on a lot of 75.
    assert t["gross"] == 5250.0 and t["net"] == 5250.0 and [l["strike"] for l in t["legs"]] == [25000.0, 25000.0]


def test_offsets_count_strikes_from_at_the_money():
    t = ob.run_trade(ENTRY, EXPIRY, E1, legs("BUY CE 1"), 2, FREE)
    assert t["legs"][0]["strike"] == 25100.0 and t["legs"][0]["qty"] == 150
    # Settles at intrinsic, 25120 - 25100 = 20. Paid 50.
    assert t["gross"] == (20 - 50) * 150


def test_lot_size_comes_from_the_day_itself():
    old = [[*r[:5], 50, r[6]] for r in ENTRY]
    assert ob.run_trade(old, EXPIRY, E1, legs("SELL CE 0"), 1, FREE)["legs"][0]["qty"] == 50


@pytest.mark.parametrize("text,reason", [("SELL PE 1", "a leg didn't trade on entry day"), ("BUY CE 9", "strike not listed")])
def test_a_price_we_do_not_have_skips_the_trade_rather_than_inventing_a_fill(text, reason):
    assert ob.run_trade(ENTRY, EXPIRY, E1, legs(text), 1, FREE) == {"skip": reason}


def test_costs_by_side_with_hand_checked_numbers():
    c = {**FREE, "brokeragePerOrder": 20.0, "sttSellPct": 0.15, "sttExercisePct": 0.15, "stampBuyPct": 0.003, "gstPct": 18.0}
    assert ob.leg_costs("SELL", 10000, 0, c) == pytest.approx(20 + 3.6 + 15)       # brokerage + GST + STT on premium
    assert ob.leg_costs("BUY", 10000, 2000, c) == pytest.approx(20 + 3.6 + 0.3 + 3)  # + stamp + STT on the exercised value
    assert ob.leg_costs("BUY", 10000, 0, c) == pytest.approx(20 + 3.6 + 0.3)        # expired worthless: no exercise STT


def test_costs_are_on_by_default():
    t = ob.backtest({date(2026, 10, 5): ENTRY, date(2026, 10, 6): EXPIRY}, legs("SELL CE 0"))
    assert t["summary"]["costs"] > 0 and t["summary"]["netPnl"] < t["summary"]["grossPnl"]


def test_monthly_picks_each_months_last_expiry_and_weekly_takes_all():
    def row(e):
        return ["CE", e, 100.0, 1.0, 100.0, 1, 1]
    days = {date(2026, 9, 29): [row("2026-09-29")], date(2026, 10, 6): [row("2026-10-06"), row("2026-10-27")], date(2026, 10, 27): [row("2026-10-27")]}
    assert ob.expiries_in(days, "weekly") == ["2026-09-29", "2026-10-06", "2026-10-27"]
    assert ob.expiries_in(days, "monthly") == ["2026-09-29", "2026-10-27"]


def test_an_expiry_we_have_not_reached_is_not_traded():
    days = {date(2026, 10, 5): [["CE", "2026-10-13", 100.0, 1.0, 100.0, 1, 1]]}
    assert ob.expiries_in(days, "weekly") == []


def test_summary_tracks_drawdown_on_closed_trades():
    s = ob.summarize([{"net": 100, "gross": 110, "costs": 10}, {"net": -300, "gross": -290, "costs": 10}, {"net": 50, "gross": 60, "costs": 10}])
    assert s["netPnl"] == -150 and s["maxDrawdown"] == -300 and s["winRate"] == 66.7 and s["worstTrade"] == -300 and s["costs"] == 30


@pytest.mark.parametrize("bad", ["", "SELL", "HOLD CE 0", "SELL XX 0", "SELL CE x", ",".join(["SELL CE 0"] * 7)])
def test_bad_legs_are_refused(bad):
    with pytest.raises(ValueError):
        ob.parse_legs(bad)


def test_parse_reads_the_udiff_columns_for_one_underlying():
    # Real files carry SttlmPric too. On option rows it holds the underlying's price (22749.75 on both legs of a
    # 22750 straddle, 27 Oct 2026), so it must never be read as what the option settled at.
    head = ",".join([*ob.COLS, "SttlmPric"])
    lines = [head, "IDO,NIFTY,2026-10-06,25000,CE,100,25010,75,10,25010", "IDO,BANKNIFTY,2026-10-06,55000,CE,100,55010,30,10,55010", "IDF,NIFTY,2026-10-27,,,25050,25010,75,10,25050"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.csv", "\n".join(lines))
    assert ob.parse(buf.getvalue(), "NIFTY") == [["CE", "2026-10-06", 25000.0, 100.0, 25010.0, 75, 10]]


def test_route_validates_and_downloads_are_reported(client, monkeypatch):
    monkeypatch.setattr(ob, "load_days", lambda u, d: ({}, 12))
    assert client.get("/api/option-backtest?underlying=NIFTY&legs=NOPE").status_code == 400
    assert client.get("/api/option-backtest?underlying=NIFTY&legs=SELL CE 0&entry=99").status_code == 400
    d = client.get("/api/option-backtest?underlying=NIFTY&legs=SELL CE 0").get_json()
    assert d["downloading"] == 12 and "downloading" in d["note"] and d["provenance"]["feed"] == "option-backtest"

