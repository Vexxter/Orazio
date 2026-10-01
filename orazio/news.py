"""Headlines for whatever symbol is on the chart.

Source: Google News' public RSS search (news.google.com/rss/search) — free, no key, and the
only source measured (30 Sep 2026) that is actually current: newest NIFTY headline 3 min
old, RELIANCE 29 min, KOSPI 23 min. Yahoo's own news (in its search endpoint) was 1-2 days
stale or empty for the same symbols, so it is not used.

Stocks are searched by company name (looked up once from Yahoo's search); indices by a
fixed phrase. Google News is a headline aggregator: each item carries its publisher, and
the link opens the publisher's story.
"""
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

from .cache import cached

NEWS_TTL = 60          # seconds — how often a fresh pull is allowed per symbol
NAME_TTL = 86400
MAX_ITEMS = 30
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

INDEX_PHRASES = {
    "^NSEI": "Nifty 50", "GIFTNIFTY": "GIFT Nifty", "^NSEBANK": "Bank Nifty", "^CNXIT": "Nifty IT index", "^BSESN": "Sensex",
    "^GSPC": "S&P 500", "^IXIC": "Nasdaq Composite", "^DJI": "Dow Jones Industrial Average",
    "^KS11": "KOSPI", "^TWII": "TAIEX Taiwan stocks", "000300.SS": "CSI 300", "000001.SS": "Shanghai Composite",
    "ES=F": "S&P 500 futures", "NQ=F": "Nasdaq 100 futures", "YM=F": "Dow futures",
    "CL=F": "crude oil prices", "BZ=F": "Brent crude", "GC=F": "gold price", "SI=F": "silver price",
    "NG=F": "natural gas prices", "HG=F": "copper prices",
    "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "BNB-USD": "BNB Binance Coin", "SOL-USD": "Solana crypto",
    "XRP-USD": "XRP Ripple", "DOGE-USD": "Dogecoin",
}
# A headline must mention one of these to be shown — Google matches loosely, and market
# roundups ("TCS, Infosys, Reliance: stock update") otherwise flood every stock's feed.
INDEX_KEYWORDS = {
    "^NSEI": ["nifty"], "GIFTNIFTY": ["gift nifty", "sgx nifty"], "^NSEBANK": ["nifty", "bank nifty"], "^CNXIT": ["nifty it", "nifty"], "^BSESN": ["sensex"],
    "^GSPC": ["s&p"], "^IXIC": ["nasdaq"], "^DJI": ["dow"], "^KS11": ["kospi"], "^TWII": ["taiex", "taiwan"],
    "000300.SS": ["csi 300", "csi300"], "000001.SS": ["shanghai"],
    "ES=F": ["s&p", "futures"], "NQ=F": ["nasdaq", "futures"], "YM=F": ["dow", "futures"],
    "CL=F": ["crude", "oil", "wti"], "BZ=F": ["brent", "crude", "oil"], "GC=F": ["gold"], "SI=F": ["silver"],
    "NG=F": ["natural gas", "lng"], "HG=F": ["copper"],
    "BTC-USD": ["bitcoin", "btc"], "ETH-USD": ["ethereum", "ether", "eth"], "BNB-USD": ["bnb", "binance"],
    "SOL-USD": ["solana", "sol"], "XRP-USD": ["xrp", "ripple"], "DOGE-USD": ["dogecoin", "doge"],
}
_INDIA = (".NS", ".BO")
_INDIA_INDEXES = {"^NSEI", "^NSEBANK", "^CNXIT", "^BSESN", "GIFTNIFTY"}
_SUFFIXES = re.compile(r"\b(ltd|limited|inc|corp|corporation|co|plc|holdings?|the)\b\.?", re.I)


def _company_name(symbol):
    def fetch():
        try:
            r = requests.get("https://query1.finance.yahoo.com/v1/finance/search",
                             params={"q": symbol, "quotesCount": 1, "newsCount": 0}, headers=UA, timeout=6)
            r.raise_for_status()
            q = (r.json().get("quotes") or [{}])[0]
            return q.get("longname") or q.get("shortname")  # longname is unabbreviated ("Tata Consultancy Services Limited")
        except (requests.RequestException, ValueError):
            return None
    return cached(("news-name", symbol), NAME_TTL, fetch)


def _clean_name(symbol):
    name = _company_name(symbol)
    return re.sub(r"\s+", " ", _SUFFIXES.sub("", name)).strip(" .,") if name else None


def query_for(symbol):
    if symbol in INDEX_PHRASES:
        return INDEX_PHRASES[symbol]
    clean = _clean_name(symbol)
    # "stock" keeps "Apple" the company apart from apples.
    return f'"{clean}" stock' if clean else symbol.split(".")[0]


_GENERIC = {"industries", "services", "consultancy", "bank", "finance", "financial", "motors", "group", "global",
            "international", "india", "indian", "limited", "company", "enterprises", "technologies", "corporation"}


def keywords_for(symbol):
    if symbol in INDEX_KEYWORDS:
        return INDEX_KEYWORDS[symbol]
    words = []
    clean = _clean_name(symbol)
    if clean:
        words.append(clean.lower())
        words += [w for w in clean.lower().split() if len(w) >= 4 and w not in _GENERIC]
    ticker = symbol.split(".")[0].lower()
    if len(ticker) >= 3:
        words.append(ticker)
    return list(dict.fromkeys(words))


def _mentions(title, keywords):
    t = title.lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", t) for k in keywords)


def _edition(symbol):
    india = symbol in _INDIA_INDEXES or symbol.endswith(_INDIA)
    return ("en-IN", "IN") if india else ("en-US", "US")


def _parse(xml_bytes):
    out = []
    for item in ET.fromstring(xml_bytes).findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = item.findtext("link")
        try:
            ts = parsedate_to_datetime(item.findtext("pubDate")).timestamp()
        except (TypeError, ValueError):
            continue
        source = item.find("source")
        publisher = source.text if source is not None and source.text else ""
        # Google appends " - Publisher" to every headline; the publisher has its own field.
        if publisher and title.endswith(" - " + publisher):
            title = title[: -len(publisher) - 3]
        if title and link:
            out.append({"title": title, "publisher": publisher, "url": link, "time": int(ts)})
    return out


def headlines(symbol):
    """Newest-first list of {title, publisher, url, time}, or None when the source is
    unreachable (so the UI can say so instead of showing an empty list as if it were news)."""
    def fetch():
        hl, gl = _edition(symbol)
        try:
            r = requests.get("https://news.google.com/rss/search",
                             params={"q": query_for(symbol) + " when:2d", "hl": hl, "gl": gl, "ceid": f"{gl}:en"},
                             headers=UA, timeout=8)
            r.raise_for_status()
            items = _parse(r.content)
        except (requests.RequestException, ET.ParseError):
            return None
        keywords = keywords_for(symbol)
        seen, unique = set(), []
        for it in sorted(items, key=lambda x: -x["time"]):
            if keywords and not _mentions(it["title"], keywords):
                continue
            key = re.sub(r"\W+", "", it["title"].lower())[:60]
            if key not in seen:
                seen.add(key)
                unique.append(it)
        return unique[:MAX_ITEMS]
    return cached(("news", symbol), NEWS_TTL, fetch)
