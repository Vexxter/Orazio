"""The Insights hub's data: institutional flows, options analytics, delivery, rollover, macro."""
from flask import jsonify, request

from .. import chart_events, delivery, flows, macro, options_analytics, rollover
from . import bp


@bp.route("/api/flows")
def flows_route():
    return jsonify(flows.payload())


@bp.route("/api/options/analytics")
def options_analytics_route():
    return jsonify(options_analytics.analytics(request.args.get("symbol") or "NIFTY", request.args.get("expiry")))


@bp.route("/api/delivery")
def delivery_route():
    return jsonify({**delivery.delivery(), "deals": delivery.deals()})


@bp.route("/api/rollover")
def rollover_route():
    return jsonify(rollover.rollover())


@bp.route("/api/macro")
def macro_route():
    return jsonify(macro.payload())


@bp.route("/api/chart-events")
def chart_events_route():
    return jsonify(chart_events.events(request.args.get("symbol")))
