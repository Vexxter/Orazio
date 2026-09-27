"""Shared outbound HTTP sessions, one per upstream, each with the headers it needs."""
import requests

from .constants import USER_AGENT

_UA = {"User-Agent": USER_AGENT}

yahoo_http = requests.Session()
yahoo_http.headers.update(_UA)

bse_http = requests.Session()
bse_http.headers.update({**_UA, "Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com",
                          "Accept": "application/json, text/plain, */*"})

nse_http = requests.Session()
nse_http.headers.update({**_UA, "Accept": "application/json"})
