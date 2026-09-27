"""Static lookup tables and timing constants shared across the app.

Nothing in this module does I/O or holds mutable state — it is safe to import
from anywhere without worrying about import order or circular dependencies.
"""
from datetime import timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_SYMBOL = "^NSEI"  # Nifty 50 index on Yahoo Finance

SYMBOL_ALIASES = {
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "NIFTYIT": "^CNXIT",
    "SPX": "^GSPC",
    "NASDAQ": "^IXIC",
    "DOWJONES": "^DJI",
    "KOSPI": "^KS11",
    "TAIEX": "^TWII",
    "CHINA": "000300.SS",  # CSI 300 — mainland China's main broad-market index
    "SSE": "000001.SS",    # Shanghai Composite — kept alongside CSI 300, not instead of it
}

# Left-rail quick-access list: (display label, alias to send to the API).
QUICK_INDICES = [
    ("NIFTY", "NIFTY"), ("BANKNIFTY", "BANKNIFTY"), ("NIFTYIT", "NIFTYIT"),
    ("SENSEX", "SENSEX"), ("SPX", "SPX"), ("NASDAQ", "NASDAQ"), ("DOWJONES", "DOWJONES"),
    ("KOSPI", "KOSPI"), ("TAIEX", "TAIEX"), ("CHINA", "CHINA"), ("SSE", "SSE"),
]

# Cash <-> futures ticker map. Only populated for indices where yfinance actually
# carries a futures contract (verified live) — NSE indices have none, so they're
# simply absent here and the frontend shows no toggle for them.
FUTURES_MAP = {
    "^GSPC": "ES=F",
    "^IXIC": "NQ=F",
    "^DJI": "YM=F",
}

# Readable names for the futures tickers. Note NQ=F is the Nasdaq-100 E-mini, which is
# not the Nasdaq Composite (^IXIC) the NASDAQ rail item charts — the label says so.
FUTURES_META = {
    "ES=F": {"name": "S&P 500 Futures (ES)", "alias": "SPX"},
    "NQ=F": {"name": "Nasdaq-100 Futures (NQ)", "alias": "NASDAQ"},
    "YM=F": {"name": "Dow Futures (YM)", "alias": "DOWJONES"},
}

# Range presets, ordered from shortest to longest. Each maps to the yfinance `period` arg.
RANGE_ORDER = ["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "5Y", "ALL"]
RANGE_TO_PERIOD = {
    "1D": "1d", "5D": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo",
    "YTD": "ytd", "1Y": "1y", "5Y": "5y", "ALL": "max",
}

# Bar size ladder, coarsest fallback last. Yahoo's actual intraday history limits:
# 1m ~7 days, 5m/15m ~60 days, 1h ~2 years, 1d unlimited.
INTERVAL_LADDER = ["1m", "5m", "15m", "1h", "1d"]
INTERVAL_MAX_RANGE = {"1m": "5D", "5m": "1M", "15m": "1M", "1h": "1Y", "1d": "ALL"}

# Real yfinance intraday ceilings per bar size — how far back a lazy-load ("drag left")
# request can reach before there's simply no more data to fetch.
HISTORY_PERIOD = {"1m": "7d", "5m": "1mo", "15m": "1mo", "1h": "1y", "1d": "max"}

INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}

QUOTE_CACHE_TTL = 1.5  # seconds; coalesces concurrent polls (several tabs / retries)

# Yahoo's feed for the NSE indices stops at the auction: measured on 21 Sep 2026 its last tick
# was 15:17:32 and never carried the closing value (official NIFTY close 23414.30 vs the 23429.00
# Yahoo still reported an hour later). NSE's own index feed does carry the close, so it takes over
# whenever Yahoo's tick is stale and NSE's stamp is newer.
NSE_INDEX_BY_YAHOO = {"^NSEI": "NIFTY 50", "^NSEBANK": "NIFTY BANK", "^CNXIT": "NIFTY IT"}
YAHOO_STALE_SEC = 120

LIVE_BAR_POLL_SEC = 3
NSE_POLL_SEC = 3

# Rail alias -> the name NSE's allIndices feed uses.
NSE_INDEX_NAMES = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK", "NIFTYIT": "NIFTY IT"}
YAHOO_INDEX_SYMBOL = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK", "NIFTYIT": "^CNXIT"}

# ---------------------------------------------------------------------------
# Call Auction Session (CAS).
#   Pre-open  09:00-09:15 IST: orders collected 09:00-09:08, matched 09:08-09:12.
#     Price discovery is real here, and NSE publishes each stock's IEP (indicative
#     equilibrium price). The index level it implies shows up as that index's `open`.
#   Post-close 15:40-16:00 IST: this is NOT price discovery — it is trading AT the
#     already-determined close, so there is no IEP. What is meaningful is the
#     indicative/official closing value, which NSE and BSE both publish.
# Only NSE/BSE indices have a public auction feed; the rest are reported as such
# rather than filled with a guess.
# ---------------------------------------------------------------------------
# Verified against NSE and broker documentation (Sept 2026), not assumed:
#   SEBI circular HO/47/11/11(3)2025-MRD-POD2/I/2765/2026 (16 Jan 2026) introduced the
#   Closing Auction Session, live from 3 August 2026, for F&O-eligible stocks only.
#   Continuous trading in those names now STOPS at 15:15 — it does not run to 15:30.
#   Non-F&O stocks keep the old VWAP close and trade through to 15:30.
CAS_SESSIONS = [
    {
        "phase": "pre-open", "label": "Pre-open auction", "start": (9, 0), "end": (9, 15),
        "stages": [
            ((9, 0), (9, 5), "Order entry — market & limit"),
            ((9, 5), (9, 10), "Limit orders only — closes randomly 09:08-09:10"),
            ((9, 10), (9, 12), "Matching & opening price"),
            ((9, 12), (9, 15), "Buffer before continuous trading"),
        ],
    },
    {
        "phase": "closing-auction", "label": "Closing auction (CAS)", "start": (15, 15), "end": (15, 35),
        "stages": [
            ((15, 15), (15, 20), "Reference price (VWAP 15:00-15:15) — no new orders"),
            ((15, 20), (15, 25), "Order entry — market & limit"),
            ((15, 25), (15, 30), "Limit orders only — closes randomly 15:28-15:30"),
            ((15, 30), (15, 35), "Matching, confirmation & closing price"),
        ],
    },
    {
        "phase": "post-market", "label": "Post-market", "start": (15, 50), "end": (16, 0),
        "stages": [((15, 50), (16, 0), "Market orders at the closing price")],
    },
]

# The auction is measured against the LAST VALUE AT 15:14:59, i.e. the final traded value before
# continuous trading stops at 15:15. Once found it is locked for the day.
CAS_REFERENCE_AT = (15, 14, 59)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
