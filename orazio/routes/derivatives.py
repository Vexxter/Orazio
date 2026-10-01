"""NSE futures & options: the F&O panel and the list of symbols that have contracts."""
from flask import jsonify, request

from .. import fno as fno_service
from ..symbols import clean_symbol
from . import bp
from ._common import json_errors


@bp.route("/api/fno")
@json_errors
def fno_route():
    return jsonify(fno_service.panel(clean_symbol(request.args.get("symbol")), request.args.get("expiry")))


@bp.route("/api/fno/symbols")
def fno_symbols_route():
    return jsonify({"stocks": sorted(fno_service.fno_stocks())})
