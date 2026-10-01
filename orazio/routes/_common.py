"""Helpers shared by the route modules."""
import functools
from urllib.parse import urlparse

from flask import abort, jsonify, request


def json_errors(view):
    """Validation failures (bad dates, an unwritable folder, ...) are messages for the user, not
    server errors: answer 400 with {"error": "..."} instead of a 500 page."""
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    return wrapper


def require_same_origin():
    """CORS is open app-wide, so any web page could otherwise POST here and make this machine
    write files into a folder of its choosing. Browsers always attach Origin to a cross-origin
    POST — reject it unless it is this very server."""
    origin = request.headers.get("Origin")
    if origin and urlparse(origin).netloc != request.host:
        abort(403, description="cross-origin requests are not allowed here")
