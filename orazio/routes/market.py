"""Market-wide views: breadth counts, top movers, and the legend's session stats."""
from flask import jsonify, request

from .. import cas, constituents as constituents_service, global_movers, live_volume, market_breadth, names as names_service
from .. import movers as movers_service
from .. import poller
from .. import stats as stats_service
from ..constants import INTERVAL_SECONDS
from ..symbols import clean_symbol
from . import bp


@bp.route("/api/breadth")
def breadth():
    poller.ensure_poller()
    return jsonify({"indices": cas.breadth_rows() + constituents_service.breadth_rows() + market_breadth.breadth_rows()})


def _with_names(payload):
    """Movers rows carry only a ticker (688185, 457190.KS); add the company's name."""
    names_service.attach_names((payload.get("gainers") or []) + (payload.get("losers") or []))
    return jsonify(payload)


@bp.route("/api/movers")
def movers_route():
    universe = request.args.get("universe") or "allSec"
    # NIFTY/BANKNIFTY/allSec come live from NSE (movers.py). NASDAQ/SSE/TAIEX come from
    # global_movers.py; the other indices are computed from the same constituent data
    # /api/breadth already polls (constituents.py) rather than a second, duplicate fetch.
    if universe in global_movers.UNIVERSES:
        return _with_names(global_movers.movers(universe))
    if universe in constituents_service.CONSTITUENT_ALIASES:
        cached = constituents_service.movers_for(universe)
        if not cached:
            return jsonify({"available": False, "universe": universe, "gainers": [], "losers": []})
        return _with_names({"available": True, "universe": universe, **cached})
    return _with_names(movers_service.movers(universe))


@bp.route("/api/stats")
def stats_route():
    symbol = clean_symbol(request.args.get("symbol"))
    s = stats_service.stats_for(symbol)
    if not s:
        return jsonify({"available": False, "symbol": symbol})
    payload = {"available": True, "symbol": symbol, **s}
    if symbol in live_volume.TRACKED:
        step = INTERVAL_SECONDS.get(request.args.get("interval", "1m"), 86400)
        payload["volumeBars"] = live_volume.bucket_volumes(symbol, step)
    return jsonify(payload)
