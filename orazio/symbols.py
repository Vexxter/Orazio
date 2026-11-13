"""Symbol validation and interval/range resolution — pure functions, no I/O."""
import re

from flask import abort

from .constants import DEFAULT_SYMBOL, INTERVAL_LADDER, INTERVAL_MAX_RANGE, RANGE_ALIASES, RANGE_ORDER, RANGE_TO_PERIOD, SYMBOL_ALIASES

# Yahoo Finance tickers: letters, digits, ^ . - = _ are all valid (e.g. ^NSEI, RELIANCE.NS,
# BTC-USD, EURUSD=X, AAPL, NIFTY_MIDCAP_100.NS). Reject anything else to keep this a fixed-format passthrough,
# not a place to smuggle arbitrary strings into outbound requests.
# 32, not 20: Indian G-sec chart ids run long ("NDS_0657_GS_2033_17_AUG", gsec.chart_id).
# & is in NSE tickers (M&M.NS, M&MFIN.NS); every outbound call passes symbols as params or URL paths, never raw query text.
SYMBOL_RE = re.compile(r"^[A-Za-z0-9\^\.\-=_&]{1,32}$")


def clean_symbol(raw):
    symbol = (raw or DEFAULT_SYMBOL).strip().upper()
    symbol = SYMBOL_ALIASES.get(symbol, symbol)
    if not SYMBOL_RE.match(symbol):
        abort(400, description="invalid symbol")
    return symbol


def resolve_interval_range(interval, rng, max_range=INTERVAL_MAX_RANGE):
    """Pick the coarsest interval that can actually serve the requested range.

    Interval (bar size) and range (how much history) are independent controls, but
    Yahoo can't serve e.g. 1-minute bars over a year — rather than erroring, escalate
    to a coarser interval that can, and tell the caller what was actually used.
    """
    if interval not in INTERVAL_LADDER:
        interval = "1d"
    rng = RANGE_ALIASES.get(rng, rng)
    if rng not in RANGE_TO_PERIOD:
        rng = "1D"

    req_idx = RANGE_ORDER.index(rng)
    for candidate in INTERVAL_LADDER[INTERVAL_LADDER.index(interval):]:
        max_idx = RANGE_ORDER.index(max_range[candidate])
        if req_idx <= max_idx:
            return candidate, rng
    return "1d", rng
