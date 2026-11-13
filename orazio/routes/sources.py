"""Stamps every data response with its provenance, records feed health, and serves the feed registry."""
from flask import current_app, jsonify, request

from .. import provenance
from . import bp


@bp.after_request
def stamp(resp):
    if not request.path.startswith("/api/") or resp.direct_passthrough:
        return resp
    payload = resp.get_json(silent=True) if resp.is_json else None
    payload = payload if isinstance(payload, dict) else None
    feed = provenance.feed_for(request.path, request.args, payload)
    if feed is None:
        return resp
    if resp.status_code == 200 or resp.status_code >= 500:   # a refused or bad request says nothing about the feed
        provenance.record(feed, resp.status_code, payload)
    if resp.status_code == 200 and payload is not None:
        resp.set_data(current_app.json.dumps({**payload, "provenance": provenance.describe(feed, payload)}))
    return resp


@bp.route("/api/sources")
def sources():
    return jsonify({"feeds": provenance.registry()})
