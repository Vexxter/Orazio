"""Bonus/split gap-fill for individual NSE stocks — ported from the AMC pipeline's
corpo_action/actions_NSE.py (fetch_nse_corporate_actions / process_nse_corporate_actions
/ adjust_historical_data), but NOT applied the way that script applies it.

Verified against RELIANCE.NS before wiring this in: yf.download()'s default
(auto_adjust=True) already retroactively back-adjusts a stock's ENTIRE OHLC history for
every split/bonus Yahoo knows about (`yf.Ticker(...).splits` lists all 4 of RELIANCE's
bonuses back to 1997, and the downloaded Close series is smooth straight through the Oct
2024 ex-date — no discontinuity). Blanket-reapplying NSE's own corporate-action factor on
top of that, as the AMC script does for portfolio holdings, double-adjusts and silently
corrupts every pre-ex-date bar (caught in testing: it halved RELIANCE's 2021 close a
second time). So this module only fires for the narrow gap that's actually real: an NSE-
confirmed bonus/split Yahoo hasn't caught up to yet (`fetch_corp_actions_gap` diffs NSE's
record against `yf.Ticker(symbol).splits` and returns only unmatched actions).

Only bonus issues and face-value splits are handled — demergers/spin-offs need a
per-stock price lookup on the ex-date to derive a factor (see the AMC pipeline's
extract_nse_spin_off) that doesn't apply cleanly to a plain OHLC series, so they're left
alone rather than guessed at.
"""
import re
from datetime import date, datetime, timedelta

import yfinance as yf

from .cache import cached
from .constants import IST
from .nse_client import nse_get

ACTIONS_CACHE_TTL = 6 * 3600  # corporate actions are announced days/weeks ahead and don't change


def _extract_split_ratio(purpose):
    # "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share"
    m = re.search(r"R(?:s|e)\.?\s*(\d+)(?:\s*/-)?\s*.*?\s*R(?:s|e)\.?\s*(\d+)(?:\s*/-)?", purpose)
    if not m:
        return None
    old_fv, new_fv = float(m.group(1)), float(m.group(2))
    return old_fv / new_fv if new_fv else None


def _extract_bonus_ratio(purpose):
    # "Bonus Issue 1:2" -> 1 new share for every 2 held -> holding becomes 3x
    m = re.search(r"(\d+)\s*:\s*(\d+)\s*$", purpose)
    if not m:
        return None
    numerator, denominator = float(m.group(1)), float(m.group(2))
    return (numerator + denominator) / denominator if denominator else None


def _fetch_actions(nse_symbol):
    def fetch():
        end = date.today()
        start = end - timedelta(days=365 * 10)
        d = nse_get("/api/corporates-corporateActions", {
            "index": "equities", "symbol": nse_symbol,
            "from_date": start.strftime("%d-%m-%Y"), "to_date": end.strftime("%d-%m-%Y"),
        })
        return d if isinstance(d, list) else []
    return cached(("corp-actions", nse_symbol), ACTIONS_CACHE_TTL, fetch)


def factors_for(nse_symbol):
    """[{ exEpoch, priceFactor, volumeFactor, kind }], oldest first. A bar strictly
    before exEpoch needs its price multiplied by priceFactor and volume by volumeFactor
    to be comparable to bars after it."""
    out = []
    for row in _fetch_actions(nse_symbol) or []:
        purpose = re.sub(r"\s+", " ", (row.get("subject") or "")).strip()
        ex_date = row.get("exDate")
        if not purpose or not ex_date:
            continue
        try:
            ex_epoch = int(datetime.strptime(ex_date, "%d-%b-%Y").replace(tzinfo=IST).timestamp())
        except ValueError:
            continue

        if re.search(r"\bBONUS\b", purpose, re.I) and not re.search(
                r"NCRPS|PREFERENCE|PREF|DEBENTURE", purpose, re.I):
            ratio = _extract_bonus_ratio(purpose)
            if ratio:
                out.append({"exEpoch": ex_epoch, "priceFactor": 1 / ratio, "volumeFactor": ratio, "kind": "Bonus"})
        elif "Face Value Split" in purpose:
            ratio = _extract_split_ratio(purpose)
            if ratio:
                out.append({"exEpoch": ex_epoch, "priceFactor": 1 / ratio, "volumeFactor": ratio, "kind": "Split"})

    out.sort(key=lambda f: f["exEpoch"])
    return out


def _yahoo_known_splits(yahoo_symbol):
    """{ex_epoch: ratio} of every split/bonus yfinance already knows about and has
    therefore already baked into its OHLC history — same cache lifetime as the NSE side
    since neither changes intraday."""
    def fetch():
        try:
            s = yf.Ticker(yahoo_symbol).splits
        except Exception:
            return None  # unreachable, NOT "no splits" — unmatched_factors must not treat these the same
        return {int(ts.timestamp()): float(ratio) for ts, ratio in s.items()}
    return cached(("yahoo-splits", yahoo_symbol), ACTIONS_CACHE_TTL, fetch)


def unmatched_factors(yahoo_symbol, nse_symbol):
    """NSE-confirmed bonus/split actions that Yahoo's own split history does NOT already
    cover — the only ones safe to apply on top of an auto_adjust=True download without
    double-adjusting. A match is any Yahoo split within 5 days of the NSE ex-date with a
    ratio within 1% (bonus/split ratios are exact fractions; a wider date window guards
    against the two sources timestamping the ex-date a day or two apart)."""
    known = _yahoo_known_splits(yahoo_symbol)
    if known is None:
        return []  # Yahoo's own split history is unreachable — safer to apply nothing
    window = 5 * 86400
    out = []
    for f in factors_for(nse_symbol):
        matched = any(
            abs(f["exEpoch"] - ex) <= window and abs(ratio - f["volumeFactor"]) / f["volumeFactor"] < 0.01
            for ex, ratio in known.items()
        )
        if not matched:
            out.append(f)
    return out


def adjust_rows(rows, factors):
    """Apply each factor to every bar strictly before its ex-date. Independent masks —
    order doesn't matter, multiple factors compound naturally on an older bar."""
    if not factors or not rows:
        return rows
    for f in factors:
        ex_epoch, pf, vf = f["exEpoch"], f["priceFactor"], f["volumeFactor"]
        for r in rows:
            if r["time"] < ex_epoch:
                r["open"] *= pf
                r["high"] *= pf
                r["low"] *= pf
                r["close"] *= pf
                r["volume"] *= vf
    return rows


def nse_equity_symbol(yahoo_symbol):
    """'RELIANCE.NS' -> 'RELIANCE'; None for anything not a plain NSE equity ticker
    (indices, futures, other exchanges) — those have no NSE corporate-actions record
    to adjust against."""
    if yahoo_symbol.endswith(".NS"):
        return yahoo_symbol[:-3]
    return None


def adjust_candles_for_splits(yahoo_symbol, rows):
    nse_symbol = nse_equity_symbol(yahoo_symbol)
    if not nse_symbol:
        return rows
    try:
        factors = unmatched_factors(yahoo_symbol, nse_symbol)
    except Exception:
        return rows  # a corp-actions lookup failure must never break the chart itself
    return adjust_rows(rows, factors)
