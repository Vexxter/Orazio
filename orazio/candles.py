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
