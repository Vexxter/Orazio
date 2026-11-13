"""Starts every background thread the app needs, exactly once."""
from . import binance_stream, cas, cas_rebuild, commodities, constituents, exports, futures, gift_nifty, gsec, live_volume, market_breadth, market_data

_started = False


def nse_indicative():
    """{alias: NSE's indicative close} for the indices the rebuild covers (0 / missing outside the auction)."""
    names = cas_rebuild.NSE_NAMES
    rows = {r.get("index"): r for r in (cas.all_indices() or {}).get("data", [])}
    return {a: (rows.get(n) or {}).get("indicativeClose") or None for a, n in names.items()}


def nse_auction_prices():
    """NSE's CAS rows as {symbol: {"px": final price once matched, else IEP; "ltp": last traded price}}."""
    return {r["symbol"]: {"px": r.get("finalPrice") or r.get("iep") or None, "ltp": r.get("lastPrice") or r.get("refPrice")}
            for r in cas.normalise_cas_rows(cas.cas_payload())}


def ensure_poller():
    global _started
    if not _started:
        _started = True
        market_data.bse_stream.start()
        market_data.start_live_bar_poller()
        cas.start_seed_loop()
        cas.ensure_nse_poller()
        constituents.start_constituent_poller()
        live_volume.start()
        gift_nifty.start()
        # Binance only serves gold and silver futures now (futures.py); oil, gas and copper are Hyperliquid's.
        binance_stream.start({k: v for k, v in commodities.SYMBOLS.items() if not futures.is_hl(k)})
        market_breadth.start()
        exports.start_scheduler()
        gsec.start()   # records CCIL G-sec trades so individual securities can be charted
        cas_rebuild.start(lambda alias, now: cas.cas_reference(alias, now, list(cas.nse_series(alias))),
                          market_data.bse_stream, nse_auction_prices, nse_indicative)
