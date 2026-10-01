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

# Sina's endpoint 403s without a Referer from its own site; the same trick nse_http/
# bse_http already use above.
sina_http = requests.Session()
sina_http.headers.update({**_UA, "Referer": "https://finance.sina.com.cn"})

naver_http = requests.Session()
naver_http.headers.update({**_UA, "Referer": "https://finance.naver.com"})

# mis.twse.com.tw wants a Referer from its own live-quote page, plus a warm-up cookie
# (see twse_index_quote in market_data.py) — otherwise it answers with an empty array.
twse_http = requests.Session()
twse_http.headers.update({**_UA, "Referer": "https://mis.twse.com.tw/stock/index.jsp"})
