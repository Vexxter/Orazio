"""Data export: the download dialog and the end-of-day schedule. These endpoints write files, so the
ones that change anything refuse requests from other websites (see _common.require_same_origin)."""
from flask import Response, jsonify, request

from .. import exports as exports_service
from ..symbols import clean_symbol
from . import bp
from ._common import json_errors, require_same_origin


@bp.route("/api/export/options")
@json_errors
def export_options():
    return jsonify(exports_service.options(clean_symbol(request.args.get("symbol"))))


@bp.route("/api/export/download")
@json_errors
def export_download():
    a = request.args
    name, mimetype, payload = exports_service.build_download(
        clean_symbol(a.get("symbol")), a.get("universe") or "CURRENT", a.get("interval") or "1m",
        a.get("mode") or "day", a.get("day"), a.get("from"), a.get("to"), a.get("format") or "csv")
    return Response(payload, mimetype=mimetype, headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "Access-Control-Expose-Headers": "Content-Disposition",
    })


@bp.route("/api/export/schedule", methods=["GET", "POST"])
@json_errors
def export_schedule():
    if request.method == "POST":
        require_same_origin()
        return jsonify(exports_service.save_schedule(request.get_json(silent=True) or {}))
    return jsonify(exports_service.load_schedule())


@bp.route("/api/export/schedule/run", methods=["POST"])
@json_errors
def export_schedule_run():
    require_same_origin()
    return jsonify(exports_service.run_now())
