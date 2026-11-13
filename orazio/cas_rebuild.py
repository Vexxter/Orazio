"""Real-time closing-auction (CAS) estimate for NIFTY, BANKNIFTY and NIFTY IT, rebuilt from their stocks.

During the auction (15:15 to the random close at ~15:28-15:30) the index itself stops moving and NSE's
indicative index value is the only official read. This rebuilds it from the constituents, every 2 s:

  1. NSE's own auction price per stock (casApi: `finalPrice` once matched, else `IEP`) - the authoritative
     number; ridham1102/cas-live-index measured it changing every ~4 s per stock (Aug 2026).
  2. Between NSE updates, BSE's auction move for the same stock since NSE's last print is carried onto it.
     BSE runs its own auction on the same stocks and pushes it faster, free and without login:
       * bnotification.bseindia.com, channel EQ30SCWeb: every SENSEX stock, ~0.7 s per stock. The pipe-
         separated frame's 5th field is the indicative auction price (field order read from BSE's own page
         code, chunk "AKQPE63N": Symbol|Flag|MsgType|SessionNumber|IndicativePrice|IndicativeQty|...|Price|...).
       * api.bseindia.com GetStkCurrMain_new (BSE 200 market watch, 30 rows a page): `IndEq_Price`.
     Only the move since NSE's print is used, never BSE's level, so the two books' level gap cancels.
  3. NSE unreachable: BSE's own auction move from 15:15 on its own.

Every stock's 15:15 price is snapshotted ONCE, the first time the auction data appears: at the cross the
exchanges overwrite the last traded price with the auction price, so re-reading it would zero the move.

Weights: the index is exactly linear in its constituents' prices (index = sum k_i * price_i). The anchor is
NSE's own free-float market cap per constituent (/api/equity-stock-indices `ffmc`, what the index is
computed from), capped at 33% / top-3 62% for the sector indices as NSE caps them; a week of 1-minute bars
then corrects what the anchor can't know (cap factors fixed at NSE's last rebalance), by ridge regression
toward it with its strength chosen on the latest day. Measured 14 Oct 2026 on a day the fit had not seen:
NIFTY ~1 point RMS (NSE's weights alone), NIFTY IT ~3, BANKNIFTY ~18.

Estimate = reference value x sum(k_i * price_i now) / sum(k_i * price_i at 15:15). The divisor cancels.
`coverage` is the share of the index (by 15:15 value) that has an auction price yet.

Re-anchoring (measured on the 14 Oct 2026 auction): the raw rebuild sat at a near-constant offset from NSE's
indicative (+9 NIFTY, +48 BANKNIFTY, -14 NIFTY IT) because its reference is Yahoo's last tick before 15:15,
not NSE's own frozen value. So whenever NSE prints an indicative value (~every 15 s that day) it is taken as
exact and the rebuild only carries the move since then:  NSE print x raw(now) / raw(at that print).
That made the estimate land on NSE's close; between prints it did no better than NSE's last print that day
(the 2 s moves agreed in direction with NSE's next print about half the time), so the panel says so.
"""
import json
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import yfinance as yf

from .cache import cached
from .constants import IST
from .http_clients import bse_http, nse_http
from .nse_client import nse_get

CAPPED = {"BANKNIFTY", "NIFTYIT"}       # sector indices: one stock <= 33%, top three <= 62%
RIDGE = (1e-5, 1e-4, 1e-3, None)        # prior strengths tried (None = NSE's weights as they are); best on the latest day wins
NSE_NAMES = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK", "NIFTYIT": "NIFTY IT"}
INDEX_LISTS = {
    "NIFTY": ("ind_nifty50list.csv", "^NSEI"),
    "BANKNIFTY": ("ind_niftybanklist.csv", "^NSEBANK"),
    "NIFTYIT": ("ind_niftyitlist.csv", "^CNXIT"),
}
LIST_URL = "https://nsearchives.nseindia.com/content/indices/{}"
BOARD_URL = "https://api.bseindia.com/BseIndiaAPI/api/GetStkCurrMain_new/w"
BOARD_PAGES = 7                      # BSE 200 at 30 rows a page
FIT_FILE = Path.home() / ".orazio" / "index_fit.json"
WINDOW = ((15, 15, 0), (15, 40, 0))   # when the rebuild runs: from the 15:14:59 freeze to the 15:40 derivatives close
MAX_BSE_MOVE = 0.01                   # a BSE move over 1% since NSE's last print is treated as a bad BSE print
TICK_SEC = 2

_fits = {}                                       # alias -> {"date", "k": {symbol: k}, "rmse"}
_series = {alias: deque(maxlen=2000) for alias in INDEX_LISTS}   # (t, value, coverage)
_lock = threading.Lock()
_started = False
_day = {"date": None, "base": {}, "bse_base": {}, "anchors": {}, "nse_index": {}}   # per-session snapshots


# ---------------------------------------------------------------------------
# Pure pieces (tests/test_cas_rebuild.py)
# ---------------------------------------------------------------------------
def fit_composition(X, y, rounds=20):
    """Non-negative least squares for index = X @ k: refit without any column that came out negative
    (a constituent can't have negative weight; negatives are noise fitting noise)."""
    active = np.ones(X.shape[1], bool)
    k = np.zeros(X.shape[1])
    for _ in range(rounds):
        sol = np.linalg.lstsq(X[:, active], y, rcond=None)[0]
        if (sol >= 0).all():
            break
        active[np.flatnonzero(active)[sol < 0]] = False
    k[active] = np.clip(sol, 0, None)
    return k


def cap_weights(w, single=0.33, top3=0.62):
    """NSE's sector-index caps applied to weights (any scale in, fractions out)."""
    w = np.asarray(w, float) / np.sum(w)
    for _ in range(100):
        order = np.argsort(-w)
        if w[order[0]] <= single + 1e-9 and w[order[:3]].sum() <= top3 + 1e-9:
            break
        if w[order[0]] > single + 1e-9:
            big = w > single
            excess = (w[big] - single).sum()
            w[big] = single
        else:
            big = np.zeros(len(w), bool)
            big[order[:3]] = True
            excess = w[big].sum() - top3
            w[big] *= top3 / w[big].sum()
        w[~big] += excess * w[~big] / w[~big].sum()
    return w


def fit_with_prior(X, y, prior, alpha_rel):
    """Ridge regression of index = X @ k pulled toward c * prior (c fitted): the data corrects the
    free-float prior where it disagrees, and no stock can vanish the way plain least squares drops them.
    alpha_rel=None keeps the prior exactly and fits only the scale (the index divisor)."""
    xs = X @ prior
    c = float(xs @ y / (xs @ xs))
    if alpha_rel is None:
        return c * prior
    G = X.T @ X
    a = alpha_rel * np.trace(G) / G.shape[0]
    return np.linalg.solve(G + a * np.eye(len(prior)), X.T @ y + a * c * prior)


def parse_eq_frame(frame):
    """One EQ30SCWeb frame -> (BSE code, indicative price or None, last price or None). '-' means unchanged."""
    parts = str(frame).split("|")
    if len(parts) < 12 or not parts[0].isdigit():
        return None

    def num(s):
        try:
            v = float(s)
        except ValueError:
            return None
        return v if v > 0 else None
    return parts[0], num(parts[4]), num(parts[11])


def board_rows(pages):
    """BSE market-watch pages -> {NSE-style symbol: {"code", "iep", "price"}} (iep None until the auction prices one)."""
    out = {}
    for rows in pages:
        for r in rows or []:
            try:
                iep = float(r.get("IndEq_Price") or 0)
                price = float(r.get("Price") or 0)
            except (TypeError, ValueError):
                continue
            if r.get("ScripName") and price > 0:
                try:
                    shares = float(r.get("MCapFF") or 0) / price      # free-float shares (crore-scaled; only ratios matter)
                except (TypeError, ValueError):
                    shares = 0.0
                out[r["ScripName"].upper()] = {"code": str(r.get("Symbol")), "iep": iep if iep > 0 else None, "price": price,
                                               "ffShares": shares}
    return out


def snapshot_bases(day, nse, bse):
    """Record each stock's 15:15 price the first time it is seen, and never again (see module doc)."""
    for sym, n in nse.items():
        if sym not in day["base"] and n.get("ltp"):
            day["base"][sym] = n["ltp"]
    for sym, b in bse.items():
        if sym not in day["bse_base"] and b.get("price"):
            day["bse_base"][sym] = b["price"]
        if sym not in day["base"] and b.get("price"):     # BSE-only (NSE down): its own 15:15 price
            day["base"][sym] = b["price"]


def stock_price(sym, day, nse_px, bse_now):
    """(price now in NSE terms, has an auction price): NSE's print carried forward by BSE's move since it."""
    anchors, base = day["anchors"], day["base"][sym]
    if nse_px:
        if sym not in anchors or anchors[sym][0] != nse_px:        # NSE printed: re-anchor on it
            anchors[sym] = (nse_px, bse_now)
        a_nse, a_bse = anchors[sym]
        if a_bse and bse_now and abs(bse_now / a_bse - 1) < MAX_BSE_MOVE:
            return a_nse * bse_now / a_bse, True
        return a_nse, True
    bse_base = day["bse_base"].get(sym)
    if bse_now and bse_base and abs(bse_now / bse_base - 1) < 0.2:
        return base * bse_now / bse_base, True
    return base, False


def blend(k, day, nse, bse, ref_value):
    """(estimate, coverage) from weights k {symbol: k_i}, NSE rows {symbol: {"px", "ltp"}}, BSE rows
    {symbol: {"iep", "price"}} and the locked reference; None while under 90% of the stocks have a base."""
    num = den = live = 0.0
    have = 0
    for sym, w in k.items():
        if sym not in day["base"]:
            continue
        px, priced = stock_price(sym, day, (nse.get(sym) or {}).get("px"), (bse.get(sym) or {}).get("iep"))
        base = day["base"][sym]
        num += w * px
        den += w * base
        have += 1
        if priced:
            live += w * base
    if not den or have < 0.9 * len(k):
        return None
    return ref_value * num / den, live / den


# ---------------------------------------------------------------------------
# Composition fit (daily)
# ---------------------------------------------------------------------------
def constituents(alias):
    csv, _ = INDEX_LISTS[alias]
    def fetch():
        r = nse_http.get(LIST_URL.format(csv), timeout=10)
        return [line.split(",")[2].strip() for line in r.text.strip().splitlines()[1:]] if r.status_code == 200 else []
    return cached(("index-list", alias), 86400, fetch)


def calibrate(alias):
    """Fit `alias`'s composition from the last week of 1-minute bars (index and constituents, from Yahoo)."""
    syms = constituents(alias)
    if not syms:
        return None
    idx = INDEX_LISTS[alias][1]
    tickers = [s + ".NS" for s in syms]
    # threads=False: yfinance's multi-ticker download shares global state, and the app's other pollers
    # download at the same time — a clash comes back with columns missing.
    df = yf.download(tickers + [idx], period="7d", interval="1m", progress=False, threads=False)["Close"].ffill().dropna()
    cols = [t for t in tickers if t in df.columns]
    if len(df) < 500 or len(cols) < 0.9 * len(tickers):
        return None
    X, y = df[cols].values, df[idx].values
    k = _fit(alias, [c[:-3] for c in cols], X, y, df.index.date)
    rmse = float(np.sqrt(((X @ k - y) ** 2).mean()))
    return {"date": datetime.now(IST).strftime("%Y-%m-%d"), "rmse": round(rmse, 2),
            "k": {c[:-3]: float(v) for c, v in zip(cols, k) if v > 0}}


def nse_shares(alias):
    """{symbol: free-float shares} from NSE's own constituent feed (ffmc / last price), cached for the day."""
    def fetch():
        d = nse_get("/api/equity-stock-indices", {"index": NSE_NAMES[alias]}) or {}
        return {r["symbol"]: r["ffmc"] / r["lastPrice"] for r in d.get("data", [])
                if r.get("priority") == 0 and r.get("ffmc") and r.get("lastPrice")}
    return cached(("nse-ffmc", alias), 86400, fetch)


def _fit(alias, syms, X, y, dates):
    """Ridge toward NSE's own weights (BSE's free-float figures if NSE's feed is down), its strength chosen
    on the latest day (held out); plain non-negative least squares when neither source covers the index."""
    nse, b = nse_shares(alias), board()
    prior = np.array([nse.get(s) or (b.get(s) or {}).get("ffShares") or 0.0 for s in syms])
    if (prior > 0).sum() < 0.9 * len(syms):
        return fit_composition(X, y)
    if alias in CAPPED:
        last = X[-1]
        prior = cap_weights(prior * last) / last
    held = dates == dates[-1]
    best = min(RIDGE, key=lambda a: float(np.mean((X[held] @ fit_with_prior(X[~held], y[~held], prior, a) - y[held]) ** 2))
               if (~held).sum() > 300 else 0)
    return np.clip(fit_with_prior(X, y, prior, best), 0, None)


def _load_fits():
    try:
        _fits.update(json.loads(FIT_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass


def _calibrate_all():
    today = datetime.now(IST).strftime("%Y-%m-%d")
    changed = False
    for alias in INDEX_LISTS:
        if (_fits.get(alias) or {}).get("date") == today:
            continue
        try:
            fit = calibrate(alias)
        except Exception:  # noqa: BLE001 — a failed fit keeps yesterday's, which is still close
            fit = None
        if fit:
            _fits[alias] = fit
            changed = True
    if changed:
        FIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        FIT_FILE.write_text(json.dumps(_fits), encoding="utf-8")


# ---------------------------------------------------------------------------
# Live prices during the auction
# ---------------------------------------------------------------------------
def _board_page(page):
    r = bse_http.get(BOARD_URL, params={"flag": "Equity", "ddlVal1": "Index", "ddlVal2": "BSE 200", "m": "0",
                                        "pgN": str(page), "srts": "D", "srtb": "6"}, timeout=8)
    return r.json() if r.status_code == 200 else []


_pool = ThreadPoolExecutor(max_workers=BOARD_PAGES, thread_name_prefix="bse-board")


def board():
    """The BSE 200 board, all pages fetched in parallel; cached for one tick."""
    def fetch():
        try:
            return board_rows(_pool.map(_board_page, range(1, BOARD_PAGES + 1)))
        except Exception:  # noqa: BLE001 — the push stream still covers the SENSEX names
            return {}
    return cached(("bse-board", ""), TICK_SEC, fetch)


def bse_prices(stream_scrips):
    """BSE board prices, overridden by the push stream (fresher) for the SENSEX stocks it carries."""
    prices = {sym: dict(p) for sym, p in board().items()}
    by_code = {p["code"]: sym for sym, p in prices.items()}
    for code, (iep, price, _t) in stream_scrips.items():
        sym = by_code.get(code)
        if sym:
            if price:
                prices[sym]["price"] = price
            if iep:
                prices[sym]["iep"] = iep
    return prices


def in_window(now_ist):
    hms = (now_ist.hour, now_ist.minute, now_ist.second)
    return now_ist.weekday() < 5 and WINDOW[0] <= hms < WINDOW[1]


def reanchor(day, alias, raw, nse_print):
    """Carry the raw rebuild onto NSE's latest indicative print (exact when it lands, see module doc)."""
    anchors = day["nse_index"]
    if nse_print and (alias not in anchors or anchors[alias][0] != nse_print):
        anchors[alias] = (nse_print, raw)
    if alias not in anchors:
        return raw
    printed, raw_then = anchors[alias]
    return printed * raw / raw_then


def tick(now_ist, references, stream_scrips, nse=None, nse_index=None):
    """One rebuild pass: append (t, estimate, coverage) per index that has a fit and a locked reference.
    `nse` is NSE's auction feed as {symbol: {"px", "ltp"}}; `nse_index` NSE's indicative value per alias."""
    nse, nse_index = nse or {}, nse_index or {}
    bse = bse_prices(stream_scrips)
    today = now_ist.strftime("%Y-%m-%d")
    t = int(now_ist.timestamp())
    with _lock:
        if _day["date"] != today:
            _day.update(date=today, base={}, bse_base={}, anchors={}, nse_index={})
        snapshot_bases(_day, nse, bse)
        for alias, ref in references.items():
            fit = _fits.get(alias)
            if not fit or not ref:
                continue
            est = blend(fit["k"], _day, nse, bse, ref["value"])
            if est:
                value = reanchor(_day, alias, est[0], nse_index.get(alias))
                _series[alias].append((t, round(value, 2), round(est[1], 3)))


def series(alias):
    with _lock:
        return list(_series.get(alias, ()))


def snapshot(alias):
    """What the routes show: the latest estimate, its points, coverage and the fit's quality."""
    pts = series(alias)
    fit = _fits.get(alias) or {}
    if not pts:
        return None
    t, value, coverage = pts[-1]
    return {"value": value, "t": t, "coverage": coverage, "points": [[p[0], p[1]] for p in pts],
            "fitRmse": fit.get("rmse"), "fitDate": fit.get("date"),
            "source": "NSE's indicative print, carried between prints by a rebuild from each stock's auction price (NSE, then BSE)"}


def start(reference_for, stream, nse_prices=dict, nse_indicative=dict):
    """Background loop: refit the composition once a day (outside market hours), rebuild every
    TICK_SEC inside the auction window. `reference_for(alias, now)` gives the locked 15:14:59 value;
    `nse_prices()` NSE's auction feed as {symbol: {"px", "ltp"}}; `nse_indicative()` {alias: NSE's indicative}."""
    global _started
    if _started:
        return
    _started = True
    _load_fits()

    def loop():
        tried = 0.0
        while True:
            now = datetime.now(IST)
            try:
                if in_window(now):
                    tick(now, {a: reference_for(a, now) for a in INDEX_LISTS}, stream.scrip_prices(), nse_prices(), nse_indicative())
                # Refit daily after the close; and whenever an index has no fit at all (first run, or a
                # failed download), retry every 10 minutes so the next auction still gets one.
                elif (not (9 <= now.hour < 16) or any(a not in _fits for a in INDEX_LISTS)) and time.time() - tried > 600:
                    tried = time.time()
                    _calibrate_all()
            except Exception:  # noqa: BLE001 — never let one bad pass kill the loop
                pass
            time.sleep(TICK_SEC if in_window(now) else 30)

    threading.Thread(target=loop, daemon=True, name="cas-rebuild").start()
