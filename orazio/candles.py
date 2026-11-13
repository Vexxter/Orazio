"""Shaping yfinance OHLCV data into the JSON rows the frontend consumes."""


def drop_spurious_flat_rows(rows):
    """Yahoo occasionally leaks a non-trading-day row (e.g. a Sunday) into daily
    history: open==high==low==close (a duplicated prior close) with zero volume.
    A real session — even a quiet one — essentially never has exactly zero range,
    so this heuristic only ever removes fabricated rows, not real flat trading."""
    return [
        r for r in rows
        if not (r["open"] == r["high"] == r["low"] == r["close"] and r["volume"] <= 0)
    ]


def week_key(t):
    """IST week (Monday start) an epoch falls in; epoch day 0 was a Thursday, hence the +3 days."""
    return (t + 19800 + 3 * 86400) // (7 * 86400)


def resample_weekly(daily):
    """Daily rows -> weekly rows (Mon-Sun, IST), each stamped with its first session's time. For sources
    with no weekly feed of their own (NSE futures, GIFT Nifty)."""
    out = []
    for r in daily:
        if out and week_key(out[-1]["time"]) == week_key(r["time"]):
            w = out[-1]
            w["high"], w["low"], w["close"] = max(w["high"], r["high"]), min(w["low"], r["low"]), r["close"]
            w["volume"] = (w.get("volume") or 0) + (r.get("volume") or 0)
        else:
            out.append(dict(r))
    return out


def df_to_rows(df):
    df = df.dropna()

    def val(row, col):
        v = row[col]
        return float(v.iloc[0]) if hasattr(v, "iloc") else float(v)

    rows = [
        {
            "time": int(ts.timestamp()),
            "open": val(row, "Open"),
            "high": val(row, "High"),
            "low": val(row, "Low"),
            "close": val(row, "Close"),
            "volume": val(row, "Volume"),
        }
        for ts, row in df.iterrows()
    ]
    return drop_spurious_flat_rows(rows)
