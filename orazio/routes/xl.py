"""Spreadsheet links (Bloomberg's BDP / BDH, on public data): live values and history as plain text or CSV.

    =WEBSERVICE("http://127.0.0.1:5000/xl/quote?s=TCS.NS&f=price")       one live value (Excel 2013+, Windows)
    /xl/quote?s=TCS.NS,INFY.NS&f=price,changePercent                      a table (Power Query / Data > From Web)
    /xl/history?s=NIFTY&range=1Y&interval=1d                              daily bars as CSV
    /xl/fund?s=TCS&f=pe                                                   one ratio from the fundamentals panel

Each call goes through the app's own JSON routes, so symbols resolve and fall back exactly as on the chart.
Text cells that a spreadsheet would run as a formula (=, +, @, leading -) are prefixed with ' (CSV injection).
ponytail: localhost only, so Google Sheets (which fetches from Google's servers) can't reach it; Excel and LibreOffice can.
"""
import csv
import io
from datetime import datetime

from flask import Response, current_app, request

from ..constants import IST
from . import bp

QUOTE_FIELDS = ("symbol", "price", "change", "changePercent", "currency", "marketTime", "source")
MAX_SYMBOLS = 50


def _get(path):
    resp = current_app.test_client().get(path)
    return resp.get_json(silent=True) if resp.status_code == 200 else None


def safe_cell(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6g}" if abs(v) < 1e15 else str(v)
    s = str(v)
    if s[:1] in ("=", "+", "@") or (s[:1] == "-" and not _is_number(s)):
        return "'" + s
    return s


def _is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def to_csv(header, rows, with_header=True):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    if with_header:
        w.writerow(header)
    w.writerows([[safe_cell(c) for c in r] for r in rows])
    return buf.getvalue()


def _answer(header, rows):
    """One cell -> the bare value (what =WEBSERVICE wants); anything bigger -> CSV."""
    with_header = request.args.get("h", "1" if len(rows) > 1 or len(header) > 1 else "0") != "0"
    if len(rows) == 1 and len(header) == 1 and not with_header:
        return Response(safe_cell(rows[0][0]), mimetype="text/plain")
    return Response(to_csv(header, rows, with_header), mimetype="text/csv")


def _symbols():
    syms = [s.strip() for s in (request.args.get("s") or "").split(",") if s.strip()][:MAX_SYMBOLS]
    if not syms:
        return None
    return syms


@bp.route("/xl/quote")
def xl_quote():
    syms = _symbols()
    if not syms:
        return Response("pass s=SYMBOL[,SYMBOL...]", status=400, mimetype="text/plain")
    fields = [f for f in (request.args.get("f") or "price").split(",") if f in QUOTE_FIELDS] or ["price"]
    rows = []
    for s in syms:
        q = _get(f"/api/quote?symbol={s}") or {}
        rows.append([q.get(f, s if f == "symbol" else None) for f in fields])
    return _answer(fields, rows)


@bp.route("/xl/history")
def xl_history():
    syms = _symbols()
    if not syms:
        return Response("pass s=SYMBOL", status=400, mimetype="text/plain")
    rng, interval = request.args.get("range") or "1Y", request.args.get("interval") or "1d"
    d = _get(f"/api/candles?symbol={syms[0]}&interval={interval}&range={rng}") or {}
    daily = interval in ("1d", "1wk", "1mo")
    fmt = "%Y-%m-%d" if daily else "%Y-%m-%d %H:%M"
    rows = [[datetime.fromtimestamp(b["time"], IST).strftime(fmt), b.get("open"), b.get("high"), b.get("low"), b.get("close"), b.get("volume")]
            for b in d.get("candles") or []]
    return Response(to_csv(["date", "open", "high", "low", "close", "volume"], rows), mimetype="text/csv")


@bp.route("/xl/fund")
def xl_fund():
    syms = _symbols()
    if not syms:
        return Response("pass s=SYMBOL", status=400, mimetype="text/plain")
    d = _get(f"/api/fundamentals?symbol={syms[0]}") or {}
    ratios = d.get("ratios") or {}
    want = [f for f in (request.args.get("f") or "").split(",") if f in ratios] or list(ratios)
    if len(want) == 1:
        return _answer([want[0]], [[ratios[want[0]]]])
    return Response(to_csv(["field", "value"], [[k, ratios[k]] for k in want]), mimetype="text/csv")
