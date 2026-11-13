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
    insights       /api/flows and the other Insights hub views
    alerts_api     alerts, filings, shareholding, user settings, notifications
    sources        provenance on every data response, /api/sources
    xl             /xl/* plain-text and CSV values for spreadsheets (=WEBSERVICE, Power Query)
"""
from flask import Blueprint

bp = Blueprint("orazio", __name__)

# Importing the submodules registers their routes on `bp`.
from . import alerts_api, auction, charts, derivatives, exports_api, insights, market, pages, sources, stream, symbol_info, xl  # noqa: E402,F401
