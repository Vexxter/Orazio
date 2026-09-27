"""Shared NSE JSON fetcher. NSE needs a cookie from the landing page before its
JSON endpoints answer, so every caller goes through here to share that cookie."""
import time

import requests

from .http_clients import nse_http

_cookie_at = 0


def nse_get(path, params=None):
    global _cookie_at
    now = time.time()
    if now - _cookie_at > 240:
        try:
            nse_http.get("https://www.nseindia.com", timeout=5)
            _cookie_at = now
        except requests.RequestException:
            return None
    try:
        r = nse_http.get("https://www.nseindia.com" + path, params=params, timeout=6)
        if r.status_code != 200:
            _cookie_at = 0
            return None
        return r.json()
    except (requests.RequestException, ValueError):
        _cookie_at = 0
        return None
