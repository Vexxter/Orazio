"""Live smoke test: ask a RUNNING Orazio server for every feature and report what works right now.

    python scripts/smoke.py                       # http://127.0.0.1:5000
    python scripts/smoke.py http://127.0.0.1:5000

The unit tests (pytest, npm test) never touch the network, so they can't tell you that NSE moved an
endpoint or Yahoo changed a field. This does: each line is one feature checked against the real
feeds. Markets being closed is normal — those are reported as SKIP (stale data), not FAIL.
Exit code 1 if anything FAILs.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000").rstrip("/")
results = []


def fetch(path, timeout=40):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check(feature, path, verify, timeout=40):
    """verify(payload) returns None for OK, 'skip: reason' for a quiet market, or a failure message."""
    started = time.time()
    try:
        outcome = verify(fetch(path, timeout))
    except urllib.error.HTTPError as e:
        outcome = f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 — a smoke test reports every kind of failure
        outcome = f"{type(e).__name__}: {e}"
    status = "PASS" if outcome is None else "SKIP" if outcome.startswith("skip:") else "FAIL"
    results.append(status)
    print(f"{status:4}  {feature:34} {time.time() - started:5.1f}s  {'' if outcome is None else outcome}")


def has(*keys):
    def verify(d):
        missing = [k for k in keys if k not in d]
        return f"missing {missing}" if missing else None
    return verify


def bars(minimum=1):
    def verify(d):
        n = len(d.get("candles", []))
        return None if n >= minimum else f"skip: only {n} bars (market closed?)"
    return verify


def quote_fresh(d):
    if "price" not in d:
        return "no price"
    return None if (d.get("delaySec") or 0) < 3600 else f"skip: last tick {d['delaySec']}s old (market closed)"


print(f"Smoke-testing {BASE}\n")
check("config / rail order", "/api/config", lambda d: None if d["quickIndices"][:2] == ["NIFTY", "SENSEX"] else "unexpected order")
check("NIFTY quote", "/api/quote?symbol=NIFTY", quote_fresh)
check("NIFTY candles 1m", "/api/candles?symbol=NIFTY&interval=1m&range=1D", bars())
check("SENSEX quote (BSE stream)", "/api/quote?symbol=SENSEX", quote_fresh)
check("GIFT Nifty quote", "/api/quote?symbol=GIFTNIFTY", quote_fresh)
check("GIFT Nifty candles", "/api/candles?symbol=GIFTNIFTY&interval=1m&range=1D", bars())
check("GIFT Nifty daily history (NSE IX)", "/api/candles?symbol=GIFTNIFTY&interval=1d&range=1Y", bars(200), timeout=120)
check("CSI 300 quote (Sina)", "/api/quote?symbol=CHINA", quote_fresh)
check("KOSPI quote (Naver)", "/api/quote?symbol=KOSPI", quote_fresh)
check("TAIEX quote (TWSE)", "/api/quote?symbol=TAIEX", quote_fresh)
def realtime_commodity(d):
    """Yahoo's CME feed was ~600 s old; Binance should be seconds. A delay over a minute, or a
    Yahoo source, means the fast path has silently fallen back."""
    if d.get("source") != "binance":
        return f"fell back to {d.get('source')} (Binance unreachable or blocked?)"
    return None if (d.get("delaySec") or 0) < 120 else f"Binance quote is {d['delaySec']}s old"


for name, alias in (("Gold", "GOLD"), ("Crude oil", "CRUDE"), ("Silver", "SILVER"), ("Natural gas", "NATGAS")):
    check(f"{name} quote is real-time", f"/api/quote?symbol={alias}", realtime_commodity)
check("Gold intraday candles (Binance)", "/api/candles?symbol=GOLD&interval=1m&range=1D", lambda d: None if d.get("source") == "binance" and len(d["candles"]) > 100 else "not served by Binance")
check("Gold 1Y history (Yahoo CME)", "/api/candles?symbol=GOLD&interval=1d&range=1Y", lambda d: None if len(d["candles"]) > 200 and d.get("liveFold") is False else "unexpected shape", timeout=60)
check("Bitcoin quote", "/api/quote?symbol=BTC", quote_fresh)
check("NIFTY stats (52W, volume)", "/api/stats?symbol=NIFTY&interval=1m", lambda d: None if d.get("available") and d.get("yearHigh") else "no stats")
check("NIFTY live volume bars", "/api/stats?symbol=NIFTY&interval=1m", lambda d: None if d.get("volumeBars") else "skip: no volume bars yet")
check("Breadth (all indices)", "/api/breadth", lambda d: None if len(d["indices"]) >= 5 else f"only {len(d['indices'])} indices")
check("Movers: NSE market", "/api/movers?universe=allSec", lambda d: None if d["gainers"] else "no gainers")
check("Movers: Nasdaq-100", "/api/movers?universe=NASDAQ", lambda d: None if d["gainers"] else "no gainers")
check("Movers: Shanghai (Sina)", "/api/movers?universe=SSE", lambda d: None if d["gainers"] else "no gainers", timeout=60)
check("Movers: TAIEX (TWSE)", "/api/movers?universe=TAIEX", lambda d: None if d["gainers"] else "no gainers", timeout=60)
check("Movers carry company names", "/api/movers?universe=TAIEX", lambda d: None if d["gainers"] and d["gainers"][0].get("name") else "no names", timeout=60)
check("F&O panel (NIFTY)", "/api/fno?symbol=NIFTY", lambda d: None if d.get("available") and d["futures"] and d["chain"]["rows"] else "empty panel")
check("F&O panel (stock)", "/api/fno?symbol=RELIANCE.NS", lambda d: None if d.get("available") and d["futures"] else "empty panel")
check("NIFTY future quote", "/api/quote?symbol=NIFTY-FUT", quote_fresh)
check("NIFTY future candles (today)", "/api/candles?symbol=NIFTY-FUT&interval=1m&range=1D", bars())
check("NIFTY future daily history", "/api/candles?symbol=NIFTY-FUT&interval=1d&range=1M", bars(10), timeout=90)
check("News (NIFTY)", "/api/news?symbol=NIFTY", lambda d: None if d["items"] else "no headlines")
check("Company name", "/api/name?symbol=457190.KS", lambda d: None if d.get("name") else "no name")
check("CAS panel", "/api/cas", has("phase", "indices"))
check("Export options", "/api/export/options?symbol=NIFTY", has("intervals", "universes", "formats"))

fails = results.count("FAIL")
print(f"\n{results.count('PASS')} passed, {results.count('SKIP')} skipped, {fails} failed")
sys.exit(1 if fails else 0)
