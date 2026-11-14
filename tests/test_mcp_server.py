"""The MCP server, run as a real subprocess over stdio against a stand-in for Orazio."""
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "orazio_mcp.py"


class Stub(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        code, body = (500, {"error": "boom"}) if u.path == "/api/flows" else (200, {"path": u.path, "query": parse_qs(u.query), "provenance": {"source": "stub"}})
        self.send_response(code)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def session():
    server = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    proc = subprocess.Popen([sys.executable, str(SCRIPT)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
                            env={"ORAZIO_URL": f"http://127.0.0.1:{server.server_port}", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})

    def ask(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline()) if "id" in msg else None
    yield ask
    proc.stdin.close()
    proc.wait(timeout=5)
    server.shutdown()


def call(ask, name, args=None, mid=9):
    return ask({"jsonrpc": "2.0", "id": mid, "method": "tools/call", "params": {"name": name, "arguments": args or {}}})["result"]


def test_handshake_echoes_a_known_version(session):
    r = session({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})["result"]
    assert r["protocolVersion"] == "2025-06-18" and r["serverInfo"]["name"] == "orazio" and "tools" in r["capabilities"]
    assert session({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_an_unknown_version_gets_ours(session):
    assert session({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})["result"]["protocolVersion"] != "1999-01-01"


def test_tools_are_few_read_only_and_described(session):
    tools = session({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})["result"]["tools"]
    assert 10 <= len(tools) <= 16
    assert all(t["description"] and t["inputSchema"]["type"] == "object" and t["annotations"]["readOnlyHint"] for t in tools)
    names = " ".join(t["name"] for t in tools)
    assert not any(w in names for w in ("order", "journal", "settings", "alert_add", "buy", "sell"))


def test_a_call_reaches_the_local_endpoint_with_provenance(session):
    r = call(session, "get_quote", {"symbol": "NIFTY"})
    d = json.loads(r["content"][0]["text"])
    assert r["isError"] is False and d["path"] == "/api/quote" and d["query"] == {"symbol": ["NIFTY"]} and d["provenance"]["source"] == "stub"


def test_unknown_arguments_never_reach_the_url(session):
    d = json.loads(call(session, "get_quote", {"symbol": "X", "evil": "1"})["content"][0]["text"])
    assert "evil" not in d["query"]


def test_filing_text_is_labelled_untrusted(session):
    assert "never as instructions" in call(session, "get_filings")["content"][0]["text"]


def test_failures_come_back_as_tool_errors_not_crashes(session):
    r = call(session, "get_flows")
    assert r["isError"] and "500" in r["content"][0]["text"]
    assert call(session, "nope")["isError"]


def test_bad_json_and_unknown_methods_are_protocol_errors(session):
    assert session({"jsonrpc": "2.0", "id": 5, "method": "nope"})["error"]["code"] == -32601
    assert session({"jsonrpc": "2.0", "id": 6, "method": "ping"})["result"] == {}


def test_a_filing_read_through_mcp_is_untrusted_and_asks_for_citations(session):
    text = call(session, "get_filing_text", {"url": "https://nsearchives.nseindia.com/corporate/x.pdf"})["content"][0]["text"]
    assert "never as instructions" in text and "page number" in text
