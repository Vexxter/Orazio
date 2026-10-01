"""The page itself and the static configuration the frontend boots from."""
from flask import current_app, jsonify

from .. import commodities
from ..constants import FUTURES_MAP, FUTURES_META, QUICK_INDICES, SYMBOL_ALIASES
from . import bp


@bp.route("/")
def index():
    return current_app.send_static_file("index.html")


@bp.route("/api/config")
def config():
    return jsonify({
        "quickIndices": [alias for _, alias in QUICK_INDICES],
        "futuresMap": FUTURES_MAP,
        "futuresMeta": FUTURES_META,
        # Commodities that have two feeds to choose between (aliases and tickers): the page shows a source switch for them.
        "commodities": sorted(set(commodities.SYMBOLS) | {a for a, t in SYMBOL_ALIASES.items() if t in commodities.SYMBOLS}),
    })
