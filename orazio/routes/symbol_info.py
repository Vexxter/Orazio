"""Information about the symbol on the chart: headlines, company name, search, and US option chains."""
import time

import requests
import yfinance as yf
from flask import abort, jsonify, request

from .. import fno as fno_service
from .. import names as names_service
from .. import news as news_service
from ..symbols import clean_symbol
from . import bp


@bp.route("/api/news")
def news_route():
    symbol = clean_symbol(request.args.get("symbol"))
    if symbol.endswith("-FUT"):
        symbol = fno_service.spot_symbol(symbol)  # a future's news is its underlying's news
    items = news_service.headlines(symbol)
    return jsonify({"symbol": symbol, "query": news_service.query_for(symbol),
                    "available": items is not None, "items": items or [], "fetchedAt": int(time.time())})


@bp.route("/api/name")
def name_route():
    symbol = clean_symbol(request.args.get("symbol"))
    if symbol.endswith("-FUT"):
        res = fno_service.resolve(symbol)
        return jsonify({"symbol": symbol, "name": f"{res['name']} — futures (front month)" if res else None})
    return jsonify({"symbol": symbol, "name": names_service.english_name(symbol)})


@bp.route("/api/search")
def search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 1:
        return jsonify([])
    # Yahoo Finance's own public symbol-search endpoint (same one their site's search box calls)
    # — not a third-party site, no anti-bot bypass involved.
    try:
        resp = requests.get(
            "https://query1.finance.yahoo.com/v1/finance/search",
            params={"q": q, "quotesCount": 8, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        resp.raise_for_status()
        quotes = resp.json().get("quotes", [])
    except (requests.RequestException, ValueError):
        return jsonify([])
    return jsonify([
        {
            "symbol": item.get("symbol"),
            "name": item.get("shortname") or item.get("longname") or item.get("symbol"),
            "exchange": item.get("exchange"),
            "type": item.get("quoteType"),
        }
        for item in quotes
        if item.get("symbol")
    ])


def _option_rows(df):
    cols = ["strike", "lastPrice", "bid", "ask", "volume", "openInterest", "impliedVolatility"]
    return [
        {c: (None if c not in row or row[c] != row[c] else float(row[c])) for c in cols}
        for row in df.to_dict("records")
    ]


@bp.route("/api/options")
def options():
    """Yahoo's option chain (US stocks). NSE's F&O chains are served by /api/fno."""
    symbol = clean_symbol(request.args.get("symbol"))
    t = yf.Ticker(symbol)

    try:
        expiries = list(t.options)
    except Exception as e:  # yfinance raises assorted exceptions for symbols without options
        return jsonify({"available": False, "reason": str(e)[:200], "expiries": []})

    if not expiries:
        return jsonify({"available": False, "reason": "no option chain for this symbol", "expiries": []})

    expiry = request.args.get("expiry") or expiries[0]
    if expiry not in expiries:
        abort(400, description="unknown expiry for this symbol")

    chain = t.option_chain(expiry)
    return jsonify({
        "available": True, "symbol": symbol, "expiry": expiry, "expiries": expiries,
        "calls": _option_rows(chain.calls), "puts": _option_rows(chain.puts),
    })
