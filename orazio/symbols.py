"""Symbol validation and interval/range resolution — pure functions, no I/O."""
import re

from flask import abort

from .constants import DEFAULT_SYMBOL, INTERVAL_LADDER, INTERVAL_MAX_RANGE, RANGE_ORDER, RANGE_TO_PERIOD, SYMBOL_ALIASES

# Yahoo Finance tickers: letters, digits, ^ . - = are all valid (e.g. ^NSEI, RELIANCE.NS,
# BTC-USD, EURUSD=X, AAPL). Reject anything else to keep this a fixed-format passthrough,
# not a place to smuggle arbitrary strings into outbound requests.
SYMBOL_RE = re.compile(r"^[A-Za-z0-9\^\.\-=]{1,20}$")


def clean_symbol(raw):
    symbol = (raw or DEFAULT_SYMBOL).strip().upper()
    symbol = SYMBOL_ALIASES.get(symbol, symbol)
    if not SYMBOL_RE.match(symbol):
        abort(400, description="invalid symbol")
    return symbol


def resolve_interval_range(interval, rng):
    """Pick the coarsest interval that can actually serve the requested range.

    Interval (bar size) and range (how much history) are independent controls, but
    Yahoo can't serve e.g. 1-minute bars over a year — rather than erroring, escalate
    to a coarser interval that can, and tell the caller what was actually used.
    """
    if interval not in INTERVAL_LADDER:
        interval = "1d"
    if rng not in RANGE_TO_PERIOD:
        rng = "1D"

    req_idx = RANGE_ORDER.index(rng)
    for candidate in INTERVAL_LADDER[INTERVAL_LADDER.index(interval):]:
        max_idx = RANGE_ORDER.index(INTERVAL_MAX_RANGE[candidate])
        if req_idx <= max_idx:
            return candidate, rng
    return "1d", rng
