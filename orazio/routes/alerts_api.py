"""Alerts, the filing watch and user settings: the user's own data, so only this app's own page may read or change it."""
import functools

from flask import abort, jsonify, request

from .. import alerts, filings, notify, user_settings
from ..config import settings
from . import bp
from ._common import json_errors, require_same_origin

LOCAL_NAMES = {"localhost", "127.0.0.1", "[::1]", settings.HOST}


def private(view):
    """CORS is open for market data, but this is personal: refuse other sites' pages, and a rebinding hostname."""
    @functools.wraps(view)
    @json_errors
    def wrapper(*args, **kwargs):
        require_same_origin()
        if request.host.rsplit(":", 1)[0] not in LOCAL_NAMES:
            abort(403, description="not a local request")
        return view(*args, **kwargs)
    return wrapper


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


@bp.route("/api/alerts", methods=["GET", "POST"])
@private
def alerts_route():
    if request.method == "POST":
        return jsonify(alerts.add(_body()))
    d = alerts.read()
    return jsonify({"alerts": d["alerts"], "log": d["log"], "filingWatch": {k: d["filingWatch"][k] for k in ("keywords", "symbols")}})


@bp.route("/api/alerts/<alert_id>", methods=["PATCH", "DELETE"])
@private
def alert_route(alert_id):
    if request.method == "DELETE":
        alerts.remove(alert_id)
    else:
        alerts.change(alert_id, _body().get("active"))
    return jsonify({"ok": True})


@bp.route("/api/alerts/import", methods=["POST"])
@private
def alerts_import():
    body = _body()
    return jsonify(alerts.import_local(body.get("alerts"), body.get("log")))


@bp.route("/api/alerts/backtest")
@json_errors
def alerts_backtest():
    from flask import current_app
    try:
        value = float(request.args.get("value", ""))
    except ValueError:
        raise ValueError("value must be a number") from None
    rule = alerts.clean_rule({"symbol": request.args.get("symbol"), "type": request.args.get("type"), "value": value})
    resp = current_app.test_client().get("/api/candles", query_string={"symbol": rule["symbol"], "interval": "1d", "range": "ALL"})
    bars = (resp.get_json(silent=True) or {}).get("candles") or []
    if not bars:
        return jsonify({"available": False, "rule": rule})
    return jsonify({"available": True, "rule": rule, "description": alerts.describe(rule), **alerts.backtest(bars, rule)})


@bp.route("/api/filings/watch", methods=["POST"])
@private
def filing_watch():
    body = _body()
    w = alerts.set_filing_watch(body.get("keywords"), body.get("symbols"))
    return jsonify({k: w[k] for k in ("keywords", "symbols")})


@bp.route("/api/settings", methods=["GET", "POST"])
@private
def settings_route():
    return jsonify(user_settings.update(_body()) if request.method == "POST" else user_settings.public())


@bp.route("/api/settings/clear", methods=["POST"])
@private
def settings_clear():
    return jsonify(user_settings.clear_secret(_body().get("key")))


@bp.route("/api/notify/test", methods=["POST"])
@private
def notify_test():
    return jsonify(notify.send("Orazio test", "If you can read this, this channel works."))


@bp.route("/api/filings")
def filings_route():
    symbols = [s for s in (request.args.get("symbols") or "").split(",") if s]
    return jsonify(filings.query(symbols, request.args.get("q")))


@bp.route("/api/filings/text")
@private
def filing_text_route():
    return jsonify(filings.filing_text(request.args.get("url")))


@bp.route("/api/shareholding")
def shareholding_route():
    return jsonify(filings.shareholding(request.args.get("symbol")))
