"""Always-on alerts: the rules (shared vectors with alert-rules.js), the store, the watcher, notifications, privacy."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from orazio import alerts, brief, notify, user_settings
from orazio.constants import IST

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "alert_vectors.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 11, 2, 10, 0, tzinfo=IST).timestamp()
DAY = 86400


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setattr(alerts, "STORE", tmp_path / "alerts.json")
    monkeypatch.setattr(user_settings, "FILE", tmp_path / "settings.json")
    alerts._history.clear()


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: v["name"])
def test_rules_decide_the_same_as_the_page(v):
    assert alerts.fires(v["closes"], v["rule"]) == v["fires"]


def bars(closes, last=NOW - DAY):
    return [{"time": last - (len(closes) - 1 - i) * DAY, "close": c} for i, c in enumerate(closes)]


def fetcher(quote, closes):
    def fetch(path):
        return {"candles": bars(closes)} if path.startswith("/api/candles") else quote
    return fetch


def test_watcher_fires_once_a_day_and_keeps_the_log():
    a = alerts.add({"symbol": "nifty", "type": "above", "value": 100})
    assert a["symbol"] == "NIFTY"
    sent = []
    fetch = fetcher({"price": 105, "changePercent": 5, "marketTime": NOW}, [90, 95, 99])
    alerts.check_rules(fetch, lambda t, b: sent.append(b), NOW)
    alerts.check_rules(fetch, lambda t, b: sent.append(b), NOW + 60)
    assert len(sent) == 1 and "NIFTY" in sent[0] and "105" in sent[0]
    d = alerts.read()
    assert d["alerts"][0]["lastFired"] == "2026-11-02" and "NIFTY" in d["log"][0]["msg"]


def test_watcher_rearms_the_next_day_and_skips_paused_rules():
    a = alerts.add({"symbol": "X", "type": "chgUp", "value": 1})
    sent = []
    fetch = fetcher({"price": 105, "changePercent": 5, "marketTime": NOW}, [100, 100])
    alerts.check_rules(fetch, lambda t, b: sent.append(b), NOW)
    alerts.check_rules(fetch, lambda t, b: sent.append(b), NOW + DAY)
    assert len(sent) == 2
    alerts.change(a["id"], False)
    alerts.check_rules(fetch, lambda t, b: sent.append(b), NOW + 2 * DAY)
    assert len(sent) == 2


def test_one_symbol_failing_does_not_stop_the_rest():
    alerts.add({"symbol": "BAD", "type": "chgUp", "value": 1})
    alerts.add({"symbol": "GOOD", "type": "chgUp", "value": 1})
    sent = []

    def fetch(path):
        if "BAD" in path:
            return {"price": 1} if "quote" in path else {"candles": bars([1, 1])}   # no changePercent
        return {"price": 5, "changePercent": 5, "marketTime": NOW} if "quote" in path else {"candles": bars([1, 1])}
    alerts.check_rules(fetch, lambda t, b: sent.append(b), NOW)
    assert len(sent) == 1 and "GOOD" in sent[0]


def test_a_corrupt_store_is_set_aside_not_overwritten():
    alerts.STORE.write_text("{not json", encoding="utf-8")
    assert alerts.read()["alerts"] == []
    assert list(alerts.STORE.parent.glob("alerts.bad-*.json"))


def test_import_moves_browser_rules_once_and_skips_bad_rows():
    local = [{"symbol": "NIFTY", "type": "above", "value": 100, "active": False, "lastFired": "2026-10-01"}, {"symbol": "X", "type": "nope", "value": 1}]
    assert alerts.import_local(local, [{"at": "2026-10-01T00:00", "msg": "old"}]) == {"added": 1, "skipped": 1}
    assert alerts.import_local(local, [])["added"] == 0
    a = alerts.read()["alerts"]
    assert len(a) == 1 and a[0]["active"] is False and alerts.read()["log"][0]["msg"] == "old"


@pytest.mark.parametrize("bad", [{"symbol": "", "type": "above", "value": 1}, {"symbol": "X", "type": "zz", "value": 1},
                                 {"symbol": "X", "type": "above", "value": "1"}, {"symbol": "X", "type": "above", "value": True},
                                 {"symbol": "X", "type": "above", "value": float("inf")}])
def test_rules_from_outside_are_validated(bad):
    with pytest.raises(ValueError):
        alerts.clean_rule(bad)


def test_backtest_counts_fires_and_forward_moves():
    closes = [90, 99, 101, 105, 110, 98, 102, 104]
    r = alerts.backtest(bars(closes), {"type": "above", "value": 100}, horizons=(1,))
    assert r["fired"] == 2 and r["stats"][0]["count"] == 2 and r["stats"][0]["upShare"] == 100.0 and len(r["lastFires"]) == 2


# ---- notifications ---------------------------------------------------------------
def test_secrets_never_reach_the_page_and_blank_keeps_them(client):
    client.post("/api/settings", json={"telegramToken": "SECRET", "telegramChat": "42"})
    assert client.get("/api/settings").get_json()["telegramToken"] is True
    client.post("/api/settings", json={"telegramToken": "", "telegramChat": "43"})
    assert user_settings.load()["telegramToken"] == "SECRET" and b"SECRET" not in client.get("/api/settings").data
    client.post("/api/settings/clear", json={"key": "telegramToken"})
    assert user_settings.load()["telegramToken"] == ""


@pytest.mark.parametrize("bad", [{"nope": 1}, {"webhookUrl": "file:///etc/passwd"}, {"briefTime": "25:00"}, {"smtpPort": "x"}, {"desktop": "yes"}])
def test_bad_settings_are_refused(client, bad):
    assert client.post("/api/settings", json=bad).status_code == 400


def test_a_failing_channel_does_not_stop_the_others_and_never_leaks_the_token(monkeypatch):
    user_settings.update({"desktop": False, "telegramToken": "TOK", "telegramChat": "1", "webhookUrl": "https://example.test/h"})
    posted = []

    class Resp:
        status_code = 200

        def raise_for_status(self):
            posted.append("webhook")

    def post(url, **k):
        if "telegram" in url:
            raise notify.requests.ConnectionError(f"failed {url}")
        return Resp()
    monkeypatch.setattr(notify.requests, "post", post)
    out = notify.send("t", "b")
    assert posted == ["webhook"] and out["webhook"] == "ok" and "TOK" not in out["telegram"]


def test_desktop_text_goes_through_the_environment_not_the_command(monkeypatch):
    seen = {}

    class Done:
        returncode = 0

    def run(cmd, env, **k):
        seen.update(cmd=" ".join(cmd), title=env["ORAZIO_TITLE"])
        return Done()
    monkeypatch.setattr(notify.subprocess, "run", run)
    notify._desktop("$(evil)", "body", {})
    assert seen["title"] == "$(evil)" and "evil" not in seen["cmd"]


# ---- privacy ---------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/api/alerts", "/api/settings"])
def test_other_sites_cannot_read_personal_routes(client, path):
    assert client.get(path, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get(path, headers={"Host": "evil.example"}).status_code == 403
    assert client.get(path).status_code == 200


def test_the_alert_routes_round_trip(client):
    a = client.post("/api/alerts", json={"symbol": "NIFTY", "type": "above", "value": 100}).get_json()
    assert client.get("/api/alerts").get_json()["alerts"][0]["id"] == a["id"]
    assert client.patch(f"/api/alerts/{a['id']}", json={"active": False}).status_code == 200
    assert client.get("/api/alerts").get_json()["alerts"][0]["active"] is False
    assert client.delete(f"/api/alerts/{a['id']}").status_code == 200
    assert client.get("/api/alerts").get_json()["alerts"] == []
    assert client.post("/api/alerts", json={"symbol": "NIFTY", "type": "zz", "value": 1}).status_code == 400


# ---- brief -----------------------------------------------------------------------
def test_brief_goes_once_on_weekdays_after_its_time():
    monday_9 = datetime(2026, 11, 2, 9, 0, tzinfo=IST)
    assert brief.due(monday_9, "09:00", None) and not brief.due(monday_9, "09:01", None)
    assert not brief.due(monday_9, "09:00", "2026-11-02")
    assert not brief.due(datetime(2026, 11, 1, 10, 0, tzinfo=IST), "09:00", None)   # Sunday
    sent = []
    fetch = lambda p: {"price": 100.0, "changePercent": 1.0} if "quote" in p else {"cash": [{"date": "2026-10-30", "fii": {"net": -5}, "dii": {"net": 7}}]}
    brief.send_if_due(fetch, lambda t, b: sent.append(b), monday_9)
    brief.send_if_due(fetch, lambda t, b: sent.append(b), monday_9)
    assert len(sent) == 1 and "NIFTY 100.00 (+1.00%)" in sent[0] and "FII -5 / DII 7" in sent[0] and "cmd=:BRIEF" in sent[0]
