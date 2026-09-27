"""Orazio: a self-hosted TradingView-style chart backed by yfinance/NSE/BSE."""
from pathlib import Path

from flask import Flask
from flask_cors import CORS

from . import cas
from .config import settings
from .routes import bp

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app():
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
    CORS(app)
    app.register_blueprint(bp)

    # The reference price and live-index series live in memory; restore anything
    # persisted from an earlier run of this process before serving any request.
    cas.load_seed()

    return app
