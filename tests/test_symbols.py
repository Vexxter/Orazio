import pytest
from flask import Flask
from werkzeug.exceptions import BadRequest

from orazio.symbols import clean_symbol, resolve_interval_range


@pytest.fixture(autouse=True)
def app_context():
    # clean_symbol() calls flask.abort(), which needs an app/request context.
    app = Flask(__name__)
    with app.test_request_context():
        yield


def test_clean_symbol_resolves_known_alias():
    assert clean_symbol("nifty") == "^NSEI"
    assert clean_symbol("SENSEX") == "^BSESN"


def test_clean_symbol_passes_through_raw_tickers():
    assert clean_symbol("reliance.ns") == "RELIANCE.NS"
    assert clean_symbol("btc-usd") == "BTC-USD"


def test_clean_symbol_defaults_when_blank():
    assert clean_symbol("") == "^NSEI"
    assert clean_symbol(None) == "^NSEI"


@pytest.mark.parametrize("bad", ["'; DROP TABLE", "a" * 21, "SELECT *", "<script>"])
def test_clean_symbol_rejects_anything_outside_the_ticker_charset(bad):
    with pytest.raises(BadRequest):
        clean_symbol(bad)


def test_resolve_interval_range_keeps_fine_interval_when_range_allows_it():
    assert resolve_interval_range("1m", "1D") == ("1m", "1D")


def test_resolve_interval_range_escalates_when_yahoo_cannot_serve_the_combo():
    # 1m bars only go back ~5 trading days on Yahoo; a 1-year request must escalate.
    interval, rng = resolve_interval_range("1m", "1Y")
    assert interval == "1h"
    assert rng == "1Y"


def test_resolve_interval_range_falls_back_to_daily_for_the_longest_ranges():
    interval, rng = resolve_interval_range("1m", "ALL")
    assert interval == "1d"
    assert rng == "ALL"


def test_resolve_interval_range_defaults_unknown_inputs():
    interval, rng = resolve_interval_range("bogus", "also-bogus")
    assert interval == "1d"
    assert rng == "1D"
