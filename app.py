"""Entry point. All application code lives in the `orazio` package."""
import os

from orazio import alerts, create_app, iv_history, screen
from orazio.config import settings

app = create_app()

if __name__ == "__main__":
    # With the debug reloader, the parent process only watches files; the child serves. The watcher belongs there.
    if not settings.DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        alerts.start(app)
        iv_history.start()
        screen.warm()   # builds the screening universe (~15 s) so the first plain-English screen answers at once
    # threaded=True: the default single-threaded dev server processes one request at a
    # time, so rapid UI interactions (range/symbol clicks) queue up server-side behind
    # slow yfinance round-trips — your latest click waits behind stale ones you no
    # longer care about. Threading lets them actually run concurrently.
    app.run(debug=settings.DEBUG, host=settings.HOST, port=settings.PORT, threaded=True)
