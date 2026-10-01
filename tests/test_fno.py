"""F&O: which symbols have contracts, the futures rows, the option chain maths, and the futures chart series."""
from datetime import date, datetime, timedelta

import pytest

from orazio import fno
from orazio.constants import IST

STOCKS = {"RELIANCE": "Reliance Industries Limited", "BAJAJ-AUTO": "Bajaj Auto Limited"}


@pytest.fixture(autouse=True)
def known_stocks(monkeypatch):
    monkeypatch.setattr(fno, "fno_stocks", lambda: STOCKS)


# ---- resolve ---------------------------------------------------------------
@pytest.mark.parametrize("symbol,underlying,kind", [
    ("NIFTY", "NIFTY", "index"), ("^NSEI", "NIFTY", "index"), ("nifty-fut", "NIFTY", "index"),
    ("BANKNIFTY", "BANKNIFTY", "index"), ("^NSEBANK", "BANKNIFTY", "index"),
    ("RELIANCE.NS", "RELIANCE", "stock"), ("RELIANCE-FUT", "RELIANCE", "stock"), ("BAJAJ-AUTO.NS", "BAJAJ-AUTO", "stock"),
])
def test_resolve_maps_every_spelling_of_an_fno_symbol_to_its_underlying(symbol, underlying, kind):
    r = fno.resolve(symbol)
    assert r["underlying"] == underlying and r["kind"] == kind


@pytest.mark.parametrize("symbol", ["IWP.NS", "AAPL", "^GSPC", "GOLD", "RELIANCE", "", None])
def test_resolve_returns_none_when_nse_lists_no_contracts(symbol):
    # a bare "RELIANCE" with no .NS / -FUT suffix is not a chart symbol we claim as F&O
    assert fno.resolve(symbol) is None


def test_resolve_gives_the_spot_and_future_symbols_the_toggle_swaps_between():
    r = fno.resolve("RELIANCE.NS")
    assert (r["spot"], r["fut"], r["chainType"]) == ("RELIANCE.NS", "RELIANCE-FUT", "Equity")
    n = fno.resolve("NIFTY")
    assert (n["spot"], n["fut"], n["chainType"]) == ("NIFTY", "NIFTY-FUT", "Indices")


def test_spot_symbol_is_what_news_and_names_should_search_for():
    assert fno.spot_symbol("NIFTY-FUT") == "^NSEI"
    assert fno.spot_symbol("BANKNIFTY-FUT") == "^NSEBANK"
    assert fno.spot_symbol("RELIANCE-FUT") == "RELIANCE.NS"
    assert fno.spot_symbol("AAPL") == "AAPL"      # not F&O: passed through untouched


# ---- futures rows ----------------------------------------------------------
def deriv_payload(expiries, spot=22700.0):
    rows = [{"instrumentType": "FUTIDX", "expiryDate": e, "identifier": f"FUTIDXNIFTY{e}", "lastPrice": 22800 + i * 100,
             "change": -40.7, "pchange": -0.18, "prevClose": 22840.7, "openPrice": 22839.9, "highPrice": 22897, "lowPrice": 22803,
             "openInterest": 268628 - i * 1000, "changeinOpenInterest": 5447, "totalTradedVolume": 18084 - i,
             "totalTurnover": 1.0, "underlyingValue": spot} for i, e in enumerate(expiries)]
    rows.append({"instrumentType": "OPTIDX", "expiryDate": expiries[0], "lastPrice": 1})   # options must be ignored
    return {"data": rows, "timestamp": "30-Sep-2026 10:40:19"}


def future_day(offset):
    return (datetime.now(IST).date() + timedelta(days=offset)).strftime("%d-%b-%Y")


def test_futures_sorts_by_expiry_drops_expired_contracts_and_computes_basis(monkeypatch):
    payload = deriv_payload([future_day(40), future_day(-3), future_day(10)])
    monkeypatch.setattr(fno, "nse_get", lambda path, params=None: payload)
    rows, spot, ts = fno.futures("NIFTY")
    assert [r["expiry"] for r in rows] == [future_day(10), future_day(40)]        # expired one dropped, rest sorted
    assert spot == 22700.0 and ts == "30-Sep-2026 10:40:19"
    first = rows[0]
    assert first["basis"] == pytest.approx(first["last"] - 22700.0)
    assert first["basisPct"] == pytest.approx((first["last"] - 22700.0) / 22700.0 * 100)
    assert first["pChange"] == -0.18 and first["volume"] is not None


def test_futures_is_none_when_nse_is_unreachable(monkeypatch):
    monkeypatch.setattr(fno, "nse_get", lambda *a, **k: None)
    assert fno.futures("NIFTY") == (None, None, None)


def test_quote_uses_the_front_month_and_derives_prev_close(monkeypatch):
    monkeypatch.setattr(fno, "nse_get", lambda path, params=None: deriv_payload([future_day(10), future_day(40)]))
    q = fno.quote("NIFTY-FUT")
    assert q["price"] == 22800.0 and q["prevClose"] == 22840.7 and q["currency"] == "INR"
    assert q["marketTime"] == int(datetime(2026, 9, 30, 10, 40, 19, tzinfo=IST).timestamp())
    assert fno.quote("IWP.NS") is None


# ---- option chain maths ----------------------------------------------------
def side(oi, d_oi=0, ltp=1.0, iv=12.0):
    return {"openInterest": oi, "changeinOpenInterest": d_oi, "totalTradedVolume": 10, "impliedVolatility": iv, "lastPrice": ltp, "change": 0.5}


def chain_payload(spot=22710.0):
    data = [
        {"strikePrice": 22600, "CE": side(100, ltp=130.0), "PE": side(900, ltp=20.0)},
        {"strikePrice": 22700, "CE": side(500, ltp=95.5), "PE": side(600, ltp=88.0)},
        {"strikePrice": 22800, "CE": side(900, ltp=40.0), "PE": side(100, ltp=150.0)},
    ]
    return {"records": {"data": data, "timestamp": "30-Sep-2026 10:36:09", "underlyingValue": spot}}


def fake_chain_nse(path, params=None):
    if path == "/api/option-chain-contract-info":
        return {"expiryDates": ["06-Oct-2026", "13-Oct-2026"]}
    return chain_payload()


def test_chain_summary_pcr_atm_straddle_and_max_pain(monkeypatch):
    monkeypatch.setattr(fno, "nse_get", fake_chain_nse)
    c = fno.chain(fno.resolve("NIFTY"), None)
    assert c["expiry"] == "06-Oct-2026" and c["expiries"] == ["06-Oct-2026", "13-Oct-2026"]
    assert c["totalCeOi"] == 1500 and c["totalPeOi"] == 1600
    assert c["pcr"] == pytest.approx(1600 / 1500)
    assert c["atm"] == 22700                                   # nearest strike to spot 22710
    assert c["straddle"] == pytest.approx(95.5 + 88.0)
    assert c["maxPain"] == 22700                               # writers lose least if it expires at the heavy middle strike
    assert [r["strike"] for r in c["rows"]] == [22600, 22700, 22800]


def test_chain_falls_back_to_the_nearest_expiry_when_asked_for_an_unknown_one(monkeypatch):
    monkeypatch.setattr(fno, "nse_get", fake_chain_nse)
    assert fno.chain(fno.resolve("NIFTY"), "01-Jan-2020")["expiry"] == "06-Oct-2026"
    assert fno.chain(fno.resolve("NIFTY"), "13-Oct-2026")["expiry"] == "13-Oct-2026"


def test_chain_is_none_without_contract_info_and_empty_when_no_records(monkeypatch):
    monkeypatch.setattr(fno, "nse_get", lambda *a, **k: None)
    assert fno.chain(fno.resolve("NIFTY"), None) is None
    cache_clear()
    monkeypatch.setattr(fno, "nse_get", lambda path, params=None: {"expiryDates": ["06-Oct-2026"]} if "contract-info" in path else None)
    assert fno.chain(fno.resolve("NIFTY"), None)["rows"] == []


def cache_clear():
    from orazio import cache
    cache._store.clear()


def test_max_pain_minimises_total_payout():
    rows = [{"strike": 100, "ce": {"oi": 10}, "pe": {"oi": 0}},
            {"strike": 110, "ce": {"oi": 0}, "pe": {"oi": 0}},
            {"strike": 120, "ce": {"oi": 0}, "pe": {"oi": 1}}]
    assert fno.max_pain(rows) == 100
    assert fno.max_pain([{"strike": 5, "ce": None, "pe": None}]) == 5      # sides can be missing


def test_panel_for_a_symbol_without_contracts_explains_instead_of_erroring():
    p = fno.panel("IWP.NS")
    assert p["available"] is False and "NSE" in p["reason"]


# ---- intraday bars from the tick chart --------------------------------------
def test_intraday_bars_shift_nse_ist_stamps_back_to_real_epoch_and_bucket_by_minute(monkeypatch):
    monkeypatch.setattr(fno, "futures", lambda u: ([{"identifier": "FUTIDXNIFTY27-10-2026XX0.00"}], 22700.0, "ts"))
    real_open = int(datetime(2026, 9, 30, 9, 15, 1, tzinfo=IST).timestamp())
    stamp = lambda real: (real + 19800) * 1000       # NSE stamps "IST as if it were UTC", in milliseconds
    monkeypatch.setattr(fno, "_ticks", lambda ident: [[stamp(real_open), 100.0], [stamp(real_open + 20), 103.0],
                                                      [stamp(real_open + 40), 99.0], [stamp(real_open + 70), 101.0]])
    bars = fno.intraday_bars("NIFTY", 60)
    minute0 = real_open - real_open % 60
    assert bars[0] == {"time": minute0, "open": 100.0, "high": 103.0, "low": 99.0, "close": 99.0, "volume": 0}
    assert bars[1]["time"] == minute0 + 60 and bars[1]["close"] == 101.0


# ---- daily history from the bhavcopy archive ---------------------------------
def test_daily_bars_pick_the_nearest_unexpired_contract_each_day(monkeypatch):
    today = datetime.now(IST).date()
    near, far = (today + timedelta(days=10)).isoformat(), (today + timedelta(days=40)).isoformat()
    expired = (today - timedelta(days=30)).isoformat()

    def fake_days(days):
        return {d: [["NIFTY", expired, 1, 1, 1, 1, 0, 0],               # must be ignored: already expired that day
                    ["NIFTY", far, 9, 9, 9, 9, 0, 0],
                    ["NIFTY", near, 10, 12, 8, 11, 500, 777],
                    ["BANKNIFTY", near, 99, 99, 99, 99, 0, 0]] for d in days}

    monkeypatch.setattr(fno, "_ensure_days", fake_days)
    monkeypatch.setattr(fno, "futures", lambda u: (None, None, None))
    bars = fno.daily_bars("NIFTY", 10)
    assert bars, "expected one bar per weekday"
    assert all((b["open"], b["high"], b["low"], b["close"], b["volume"]) == (10, 12, 8, 11, 777) for b in bars)
    assert [b["time"] for b in bars] == sorted(b["time"] for b in bars)


def test_daily_bars_end_with_todays_live_front_month(monkeypatch):
    monkeypatch.setattr(fno, "_ensure_days", lambda days: {})
    live = [{"open": 22839.9, "high": 22897.0, "low": 22803.0, "last": 22815.0, "volume": 17496}]
    monkeypatch.setattr(fno, "futures", lambda u: (live, 22700.0, "ts"))
    today = datetime.now(IST).date()
    bars = fno.daily_bars("NIFTY", 5)
    if today.weekday() < 5:
        assert bars[-1]["close"] == 22815.0 and bars[-1]["volume"] == 17496
    else:
        assert bars == []


def test_a_cached_archive_day_never_touches_the_network(isolated_state, monkeypatch):
    day = date(2026, 9, 29)
    fno.CACHE_DIR.mkdir(parents=True)
    fno._day_path(day).write_text('[["NIFTY", "2026-10-27", 1, 2, 0.5, 1.5, 10, 20]]')
    monkeypatch.setattr(fno.nse_http, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    assert fno._fetch_day(day) == [["NIFTY", "2026-10-27", 1, 2, 0.5, 1.5, 10, 20]]


def test_archive_404_is_a_holiday_only_once_it_is_safely_in_the_past(isolated_state, monkeypatch):
    class Resp:
        status_code, content = 404, b""
    monkeypatch.setattr(fno.nse_http, "get", lambda *a, **k: Resp())
    old, recent = datetime.now(IST).date() - timedelta(days=30), datetime.now(IST).date()
    assert fno._fetch_day(old) == []                 # long past + 404: a real non-trading day, remembered
    assert fno._read_day(old) == []
    assert fno._fetch_day(recent) is None            # today's file simply isn't published yet: do NOT cache it as a holiday
    assert fno._read_day(recent) is None


def test_candles_serve_intraday_for_1d_and_daily_otherwise(monkeypatch):
    monkeypatch.setattr(fno, "intraday_bars", lambda u, step: [{"time": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}])
    monkeypatch.setattr(fno, "daily_bars", lambda u, days: [{"time": 2, "open": 2, "high": 2, "low": 2, "close": 2, "volume": 0}])
    intraday = fno.candles("NIFTY-FUT", "1m", "1D")
    assert intraday["interval"] == "1m" and intraday["symbol"] == "NIFTY-FUT"
    daily = fno.candles("NIFTY-FUT", "1m", "1M")          # no older intraday ticks exist: escalate to daily
    assert daily["interval"] == "1d" and daily["candles"][0]["time"] == 2
    with pytest.raises(ValueError):
        fno.candles("IWP.NS", "1m", "1D")
