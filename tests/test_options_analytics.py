"""Options analytics: Black-Scholes gamma, GEX sign convention, the zero-gamma flip and the OTM smile."""
import math
from datetime import datetime

from orazio import options_analytics as oa
from orazio.constants import IST


def test_bs_gamma_matches_closed_form_at_the_money():
    # S=K, iv 20%, T=1y, r=0: d1 = 0.1, gamma = phi(0.1) / (100 * 0.2)
    expected = math.exp(-0.005) / math.sqrt(2 * math.pi) / 20
    assert abs(oa.bs_gamma(100, 100, 20, 1) - expected) < 1e-12
    assert oa.bs_gamma(100, 100, None, 1) == 0.0


def test_calls_add_gamma_puts_subtract_it():
    row = {"strike": 100, "ce": {"oi": 10, "iv": 20}, "pe": {"oi": 10, "iv": 20}}
    c, p = oa.strike_gex(row, 100, 1, 1)
    assert c > 0 and p < 0 and abs(c + p) < 1e-9


def test_flip_sits_between_put_heavy_and_call_heavy_strikes():
    rows = [{"strike": 90, "ce": None, "pe": {"oi": 100, "iv": 15}},
            {"strike": 110, "ce": {"oi": 100, "iv": 15}, "pe": None}]
    flip = oa.flip_level(rows, 100, 30 / 365, 1, width=0.2)
    assert 98 < flip < 102


def test_smile_takes_puts_below_spot_and_calls_above():
    rows = [{"strike": 90, "ce": {"iv": 40}, "pe": {"iv": 20}}, {"strike": 110, "ce": {"iv": 18}, "pe": {"iv": 50}}]
    assert oa.smile(rows, 100) == [{"strike": 90, "iv": 20}, {"strike": 110, "iv": 18}]


def test_years_to_expiry_close_and_floor():
    now = datetime(2026, 11, 3, 15, 0, tzinfo=IST)
    assert oa.years_to("03-Nov-2026", now) == 3600 / (365 * 86400)
    assert abs(oa.years_to("04-Nov-2026", datetime(2026, 11, 3, 15, 30, tzinfo=IST)) - 1 / 365) < 1e-12
