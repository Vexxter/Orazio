"""Shared fixtures. The rule for every test in this suite: no real network, no real home directory.

* `_fresh_cache` empties the app's TTL cache around every test, so one test's mocked response can
  never be served to the next.
* `isolated_state` points every on-disk cache/seed/schedule file at a temp folder.
* `client` is the real Flask app with its background pollers switched off.
"""
import pytest

from orazio import cache


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache._store.clear()
    yield
    cache._store.clear()


@pytest.fixture(autouse=True)
def _no_equity_download(monkeypatch):
    """NSE's equity list (symbol search, screener names) comes from ~/.orazio or the network: neither in tests."""
    from orazio import symbol_master
    monkeypatch.setattr(symbol_master, "_equity_text", lambda: "")


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Redirect every file the app writes (futures archive cache, export schedule, GIFT Nifty bars,
    live-volume and CAS seeds) into tmp_path."""
    from orazio import cas, exports, fno, gift_nifty, live_volume
    monkeypatch.setattr(fno, "CACHE_DIR", tmp_path / "fut_cache")
    monkeypatch.setattr(exports, "CONFIG_PATH", tmp_path / "export_schedule.json")
    monkeypatch.setattr(gift_nifty, "STORE", tmp_path / "gift_nifty_bars.json")
    monkeypatch.setattr(gift_nifty, "CACHE_DIR", tmp_path / "gift_cache")
    monkeypatch.setattr(live_volume, "SEED_FILE", str(tmp_path / "live_volume_seed.json"))
    monkeypatch.setattr(cas, "SEED_FILE", str(tmp_path / "cas_seed.json"))
    from orazio import cas_rebuild, technicals
    monkeypatch.setattr(cas_rebuild, "FIT_FILE", tmp_path / "index_fit.json")
    monkeypatch.setattr(technicals, "CACHE_FILE", tmp_path / "technicals.json")
    from orazio import flows
    monkeypatch.setattr(flows, "FIIDII_FILE", tmp_path / "fiidii.json")
    monkeypatch.setattr(flows, "OI_DIR", tmp_path / "participant_oi")
    from orazio import delivery
    monkeypatch.setattr(delivery, "DIR", tmp_path / "delivery")
    from orazio import macro
    monkeypatch.setattr(macro, "MMO_DIR", tmp_path / "rbi_mmo")
    monkeypatch.setattr(macro, "CAL_FILE", tmp_path / "calendar.json")
    from orazio import gsec
    monkeypatch.setattr(gsec, "TICK_DIR", tmp_path / "gsec_ticks")
    return tmp_path


@pytest.fixture
def client(isolated_state, monkeypatch):
    """The real app, with the background pollers (which would hit the network) disabled."""
    from orazio import create_app, poller
    monkeypatch.setattr(poller, "ensure_poller", lambda: None)
    import orazio.routes as routes
    if hasattr(routes, "ensure_poller"):  # bound at import time in the single-module layout
        monkeypatch.setattr(routes, "ensure_poller", lambda: None)
    app = create_app()
    app.testing = True
    return app.test_client()
