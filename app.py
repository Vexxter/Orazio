"""Entry point. All application code lives in the `orazio` package."""
from orazio import create_app
from orazio.config import settings

app = create_app()

if __name__ == "__main__":
    # threaded=True: the default single-threaded dev server processes one request at a
    # time, so rapid UI interactions (range/symbol clicks) queue up server-side behind
    # slow yfinance round-trips — your latest click waits behind stale ones you no
    # longer care about. Threading lets them actually run concurrently.
    app.run(debug=settings.DEBUG, host=settings.HOST, port=settings.PORT, threaded=True)
