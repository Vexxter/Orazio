"""Where every number comes from: one registry of feeds, attached to each data response, plus passive feed health.

Each data route's JSON gains a `provenance` object (source, link, delay, units, as-of time), so the page and any
agent reading the API can check a value against its origin. Delays are the ones measured in the README's table.

Health is passive: the last outcome of real requests the app already made, so looking at it costs the upstream
nothing. `probe` is the local path the Sources tab calls, one at a time, when asked to check every feed.
"""
import time

from . import bonds, gsec

# id -> label, source, link to the origin, delay as measured, units, local path that exercises it
FEEDS = {
    "yahoo": ("Indices, stocks, FX, crypto", "Yahoo Finance", "https://finance.yahoo.com", "1–5 s for indices; varies by market", "exchange currency", "/api/quote?symbol=NIFTY"),
    "nse": ("NSE index close", "NSE", "https://www.nseindia.com/market-data/live-market-indices", "about 1 min", "index points", None),
    "bse": ("SENSEX", "BSE push stream", "https://www.bseindia.com/sensex/code/16/", "about 1 s", "index points", "/api/quote?symbol=SENSEX"),
    "asia": ("Korea, Taiwan, China indices", "Naver, TWSE, Sina", "https://finance.naver.com", "seconds", "index points", "/api/quote?symbol=KOSPI"),
    "spot": ("Commodities, spot", "Dukascopy, Swissquote", "https://www.dukascopy.com/swiss/english/marketwatch/", "3–8 s", "USD", "/api/quote?symbol=CRUDE"),
    "perp": ("Commodities, futures", "Hyperliquid oracle, Binance", "https://hyperliquid.xyz", "1 s or less; perpetuals, not the CME contract", "USD", "/api/quote?symbol=CRUDE&feed=futures"),
    "fno": ("NSE futures and options", "NSE public endpoints", "https://www.nseindia.com/option-chain", "about 1 min", "₹; OI in contracts", "/api/fno?symbol=NIFTY"),
    "fno-archive": ("F&O daily history", "NSE F&O bhavcopy", "https://www.nseindia.com/all-reports-derivatives", "daily, after the close", "₹", "/api/rollover"),
    "gift": ("GIFT Nifty", "NSE IX", "https://www.nseix.com", "about 1 min", "index points", "/api/quote?symbol=GIFTNIFTY"),
    "bonds": ("Government yields, 37 countries", "CNBC quote service", "https://www.cnbc.com/bonds/", "15–40 s since the last tick while each market trades", "% yield", "/api/bonds/global"),
    "gsec": ("Indian G-secs, SDLs, T-bills", "CCIL NDS-OM", "https://www.ccilindia.com/market-watch", "each trade, on the next 5 s poll", "% yield; ₹ price", "/api/bonds/india?segment=cg"),
    "corp-bonds": ("Indian corporate bonds", "NSE listed-bonds feed", "https://www.nseindia.com/market-data/bonds-traded-in-capital-market", "about 15 s", "₹ price; approximate % yield", "/api/bonds/india?segment=corp"),
    "screener": ("Screener", "NSE market watch; RSI and SMAs from Yahoo daily bars", "https://www.nseindia.com/market-data/live-equity-market", "about 10 s; technicals daily plus the live price", "₹; ₹ Cr value", "/api/screener?universe=nifty50"),
    "movers": ("Top movers", "NSE, Yahoo, Sina, TWSE", "https://www.nseindia.com/market-data/top-gainers-losers", "seconds to 1 min", "exchange currency", "/api/movers?universe=allSec"),
    "breadth": ("Market breadth", "NSE, Yahoo, Sina, TWSE", "https://www.nseindia.com/market-data/live-market-indices", "seconds to 1 min", "counts of stocks", "/api/breadth"),
    "flows": ("FII/DII and participant OI", "NSE fiidiiTradeReact, fao_participant_oi", "https://www.nseindia.com/reports/fii-dii", "daily, about 6 pm IST", "₹ Cr; contracts", "/api/flows"),
    "delivery": ("Delivery and large deals", "NSE sec_bhavdata_full, large-deal API", "https://www.nseindia.com/all-reports", "daily, after the close", "₹ Cr; %", "/api/delivery"),
    "options": ("Options analytics", "NSE option chain; GEX computed here (Black-Scholes, r = 0)", "https://www.nseindia.com/option-chain", "polled every 30 s", "₹ Cr GEX; % IV", "/api/options/analytics?symbol=NIFTY"),
    "us-options": ("US option chains", "Yahoo Finance", "https://finance.yahoo.com", "delayed", "USD", None),
    "macro": ("Calendar and RBI liquidity", "ForexFactory weekly feed, RBI Money Market Operations", "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx", "calendar hourly; RBI next morning", "₹ Cr; %", "/api/macro"),
    "news": ("Headlines", "Google News RSS", "https://news.google.com", "minutes", "text", "/api/news?symbol=NIFTY"),
    "stats": ("52-week stats and volume", "NSE, Yahoo", "https://www.nseindia.com/market-data/live-market-indices", "about 1 min", "exchange currency", "/api/stats?symbol=NIFTY"),
    "events": ("Results, dividends, deals on the chart", "NSE corporate actions, RBI dates", "https://www.nseindia.com/companies-listing/corporate-filings-actions", "daily", "text", None),
    "filings": ("Corporate announcements", "NSE corporate announcements", "https://www.nseindia.com/companies-listing/corporate-filings-announcements", "polled every 5 min", "text; PDF", "/api/filings"),
    "shareholding": ("Shareholding", "NSE shareholding pattern", "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern", "quarterly, after each filing", "% of shares", "/api/shareholding?symbol=RELIANCE"),
    "fundamentals": ("Company fundamentals and peers", "NSE MarketLens first; Yahoo statements where it lags", "https://marketlens.nseindia.com/screener", "NSE updates intraday, cached 30 min; Yahoo cached 6 h", "₹ Cr; ratios", "/api/fundamentals?symbol=TCS"),
    "earnings": ("Results calendar", "NSE event calendar (board meetings)", "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar", "as companies file; cached 30 min", "dates", "/api/earnings/calendar"),
    "ipos": ("IPOs and corporate actions ahead", "NSE public issues, corporate actions", "https://www.nseindia.com/market-data/all-upcoming-issues-ipo", "as filed; cached 15 min", "₹; dates", "/api/ipos"),
    "rate-path": ("Implied policy-rate path", "CNBC US bills + FRED fed funds target; CCIL T-bills + RBI TREPS", "https://fred.stlouisfed.org/series/DFEDTARU", "bills live; anchors daily", "% ; bp", "/api/rate-path"),
    "insider": ("Insider trades (SEBI PIT)", "NSE insider-trading disclosures", "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading", "as filed, usually within 2 trading days", "₹ Cr; shares", "/api/insider"),
    "option-backtest": ("Option strategy backtest", "NSE F&O bhavcopy, end-of-day closes", "https://www.nseindia.com/all-reports-derivatives", "daily, after the close", "₹", None),
}
ROUTES = {
    "/api/fno": "fno", "/api/bonds/global": "bonds", "/api/screener": "screener", "/api/movers": "movers",
    "/api/breadth": "breadth", "/api/flows": "flows", "/api/delivery": "delivery", "/api/rollover": "fno-archive",
    "/api/options/analytics": "options", "/api/options": "us-options", "/api/macro": "macro", "/api/news": "news",
    "/api/stats": "stats", "/api/chart-events": "events", "/api/filings": "filings", "/api/filings/text": "filings", "/api/shareholding": "shareholding",
    "/api/option-backtest": "option-backtest", "/api/insider": "insider",
    "/api/fundamentals": "fundamentals", "/api/peers": "fundamentals", "/api/earnings/calendar": "earnings",
    "/api/ipos": "ipos", "/api/corp-actions": "ipos", "/api/rate-path": "rate-path",
    "/api/screen": "fundamentals", "/api/screens": "fundamentals",
}
# The `source` a quote or candle payload names -> its feed.
SOURCES = {
    "yahoo": "yahoo", "yfinance": "yahoo", "nse": "nse", "nse-fno": "fno", "nse-gift": "gift", "cnbc": "bonds", "ccil": "gsec",
    "swissquote": "spot", "dukascopy": "spot", "hyperliquid": "perp", "binance": "perp",
    "bse": "bse", "sina": "asia", "naver": "asia", "twse": "asia",
}
AS_OF_KEYS = ("marketTime", "asOf", "date", "fetchedAt", "technicalsAsOf")
_health = {}   # feed id -> {"okAt", "failAt", "error"}


def feed_for(path, args, payload):
    """Which feed answered this request, or None for routes that carry no market data."""
    if path in ROUTES:
        return ROUTES[path]
    if path == "/api/bonds/india":
        return "corp-bonds" if args.get("segment") == "corp" else "gsec"
    if path not in ("/api/quote", "/api/candles"):
        return None
    source = (payload or {}).get("source")
    if source in SOURCES:
        return SOURCES[source]
    sym = args.get("symbol") or ""
    if sym.endswith("-FUT"):
        return "fno-archive" if path == "/api/candles" else "fno"
    if sym == "GIFTNIFTY":
        return "gift"
    if bonds.is_bond(sym):
        return "bonds"
    if gsec.is_gsec(sym):
        return "gsec"
    return "yahoo"


def describe(feed, payload):
    label, source, url, delay, units, _probe = FEEDS[feed]
    as_of = next((payload[k] for k in AS_OF_KEYS if payload.get(k)), None)
    return {"feed": feed, "label": label, "source": source, "url": url, "delay": delay,
            "units": payload.get("currency") or units, "asOf": as_of, "servedAt": int(time.time())}


def record(feed, status, payload=None):
    """One real request's outcome. `available: false` means the upstream didn't answer even though we did."""
    h = _health.setdefault(feed, {"okAt": None, "failAt": None, "error": None})
    now = int(time.time())
    if status == 200 and (payload or {}).get("available", True) is not False:
        h.update(okAt=now, error=None)
    else:
        h.update(failAt=now, error=f"HTTP {status}" if status != 200 else "the source didn't answer")


def registry():
    return [{"id": k, "label": v[0], "source": v[1], "url": v[2], "delay": v[3], "units": v[4], "probe": v[5],
             **_health.get(k, {"okAt": None, "failAt": None, "error": None})} for k, v in FEEDS.items()]
