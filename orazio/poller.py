"""Starts every background thread the app needs, exactly once."""
from . import binance_stream, cas, commodities, constituents, exports, gift_nifty, live_volume, market_breadth, market_data

_started = False


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
        binance_stream.start(commodities.SYMBOLS)
        market_breadth.start()
        exports.start_scheduler()
