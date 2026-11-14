"""The Insights hub's data: institutional flows, options analytics, delivery, rollover, macro."""
from flask import jsonify, request

from .. import chart_events, corp_calendar, deep, deep_llm, screen, delivery, earnings, flows, fundamentals, insider, macro, option_backtest, options_analytics, rate_path, rollover
from ..symbols import clean_symbol
from . import bp
from ._common import json_errors


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


@bp.route("/api/insider")
def insider_route():
    sym = (request.args.get("symbol") or "").strip().upper()
    if sym:
        return jsonify({"available": True, "rows": insider.for_symbol(sym)})
    return jsonify(insider.recent(senior_only=request.args.get("all") != "1"))


def _stock(arg):
    """'TCS', 'tcs.ns' -> 'TCS.NS'; anything already qualified (^, =, -, other suffix) passes through."""
    s = clean_symbol(arg or "")
    return s if not s or "." in s or any(c in s for c in "^=-") else f"{s}.NS"


@bp.route("/api/fundamentals")
def fundamentals_route():
    return jsonify(fundamentals.fundamentals(_stock(request.args.get("symbol"))))


@bp.route("/api/peers")
def peers_route():
    return jsonify(fundamentals.peers(_stock(request.args.get("symbol"))))


@bp.route("/api/earnings/calendar")
def earnings_calendar_route():
    symbols = [s for s in (request.args.get("symbols") or "").split(",") if s.strip()]
    return jsonify(earnings.calendar(symbols))


@bp.route("/api/ipos")
def ipos_route():
    return jsonify(corp_calendar.ipos())


@bp.route("/api/corp-actions")
def corp_actions_route():
    return jsonify(corp_calendar.actions())


@bp.route("/api/screen")
@json_errors
def screen_route():
    return jsonify(screen.ask(request.args.get("q")))


@bp.route("/api/screens")
def screens_route():
    return jsonify({"presets": screen.presets()})


@bp.route("/api/deep")
@json_errors
def deep_route():
    """Deep search: ?q=<plain English>&drop=0,2 (clause indexes switched off in the read-back)."""
    drop = {int(x) for x in (request.args.get("drop") or "").split(",") if x.strip().isdigit()}
    skip = request.args.get("nollm") == "1"          # "Run without model": the rules alone, no model call
    return jsonify(deep.ask(request.args.get("q"), drop=drop, llm=None if skip else deep_llm.read, skipped=skip))


@bp.route("/api/deep/llm-log")
def deep_llm_log_route():
    return jsonify({"provider": deep_llm.config()["provider"], "calls": deep_llm.log()})


@bp.route("/api/deep/read")
def deep_read_route():
    """Instant read-back while typing: clauses, unread words, repairs and completions. No data, no network."""
    q = request.args.get("q") or ""
    p = deep.parse(q)
    return jsonify({"clauses": [{"phrase": c.get("phrase", ""), "label": deep.label(c), "kind": c["t"]} for c in p["clauses"]],
                    "unread": p["unread"], "repaired": [{"was": a, "now": b} for a, b in p["repaired"]],
                    "suggest": deep.suggest(q), "llm": deep_llm.config()["provider"]})


@bp.route("/api/deep/llm-test", methods=["POST"])
def deep_llm_test_route():
    return jsonify(deep_llm.test())


@bp.route("/api/rate-path")
def rate_path_route():
    return jsonify(rate_path.payload())


@bp.route("/api/chart-events")
def chart_events_route():
    return jsonify(chart_events.events(request.args.get("symbol")))


@bp.route("/api/option-backtest")
@json_errors
def option_backtest_route():
    return jsonify(option_backtest.run(request.args))
