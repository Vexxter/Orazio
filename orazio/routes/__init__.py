"""HTTP routes, one module per feature area, all registered on a single blueprint.

Each view is thin glue: parse the request, call a service module, shape the JSON response.
Business logic lives in the service modules (fno.py, news.py, exports.py, ...), never here.

    pages          the HTML page and /api/config
    charts         /api/candles, /api/candles/history, /api/quote
    stream         /api/stream/quote (server-sent events: the quote pushed as it changes)
    market         /api/breadth, /api/movers, /api/stats
    symbol_info    /api/news, /api/name, /api/search, /api/options
    auction        /api/cas, /api/cas/movement, /api/cas/feed
    derivatives    /api/fno, /api/fno/symbols
    exports_api    /api/export/*
"""
from flask import Blueprint

bp = Blueprint("orazio", __name__)

# Importing the submodules registers their routes on `bp`.
from . import auction, charts, derivatives, exports_api, market, pages, stream, symbol_info  # noqa: E402,F401
