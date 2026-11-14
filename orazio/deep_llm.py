"""Deep search's optional model fallback: only when the grammar (deep.py) leaves words unread, and only if one is set up.

Backends (Insights › Settings, stored in ~/.orazio/settings.json; off by default, no API key needed for any of them):
  claude  the Claude app's CLI on your own plan: `claude -p --json-schema …`        (Claude Code login)
  codex   the Codex CLI on your own plan:      `codex exec --output-schema …`      (Codex login)
  openai  any OpenAI-compatible server: llama.cpp, Ollama, LM Studio, vLLM, OpenRouter (base URL + model [+ key])
Every backend gets the same JSON Schema, and every clause it returns must pass deep.valid() before it touches data:
the model can only pick from Orazio's fields, operators and sectors, never write code or a query.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import deque

import requests

from . import deep, user_settings
from .cache import cached

PRESETS = {"ollama": "http://localhost:11434/v1", "lmstudio": "http://localhost:1234/v1", "llamacpp": "http://localhost:8080/v1",
           "openrouter": "https://openrouter.ai/api/v1", "vllm": "http://localhost:8000/v1"}
TIMEOUT = 90

SCHEMA = {
    "type": "object",
    "properties": {
        "clauses": {"type": "array", "items": {"type": "object", "properties": {
            "t": {"type": "string", "enum": sorted(deep.KINDS)},
            "phrase": {"type": "string", "description": "the words of the question this clause reads"},
            "field": {"type": "string", "enum": sorted(deep.FIELDS)},
            "other": {"type": "string", "enum": sorted(deep.FIELDS)},
            "op": {"type": "string", "enum": [">", "<", ">=", "<=", "between"]},
            "v": {"type": "number"}, "v2": {"type": "number"}, "k": {"type": "number"}, "pct": {"type": "number"},
            "side": {"type": "string", "enum": ["top", "bottom", "buy", "sell"]},
            "words": {"type": "array", "items": {"type": "string", "enum": sorted(deep.SECTORS)}},
            "cls": {"type": "string", "enum": ["large", "mid", "small"]},
            "who": {"type": "string", "enum": ["promoter", "insider"]},
            "days": {"type": "integer"}, "desc": {"type": "boolean"}, "limit": {"type": "integer"}, "neg": {"type": "boolean"},
        }, "required": ["t", "phrase"]}},
        "unsupported": {"type": "array", "items": {"type": "string"}, "description": "parts of the question no clause can express"},
    },
    "required": ["clauses", "unsupported"],
}


def _system():
    fields = "\n".join(f"  {fid}: {lab}" for fid, (lab, *_rest) in deep.FIELDS.items())
    return f"""You translate a stock-screening question about Indian (NSE) stocks into JSON clauses. Output only the JSON object.
Clause kinds (t):
  cmp        field op v [v2 when op is between]    e.g. ROCE above 20 -> {{"t":"cmp","field":"roce","op":">","v":20}}
  rel        field op other, k multiplies other     e.g. price within 5% of 52-week high -> {{"t":"rel","field":"price","op":">=","other":"w52high","k":0.95}}
  rank       field side top|bottom pct              e.g. high dividend yield -> {{"t":"rank","field":"divy","side":"top","pct":30}}
  sector     words (any of them)                    e.g. IT or pharma -> {{"t":"sector","words":["it","pharma"]}}
  size       cls large|mid|small (SEBI ranks 1-100, 101-250, 251+)
  insider    who promoter|insider, side buy|sell, optional days
  turnaround (loss a year ago, profit now) · sort field desc [limit] · limit limit
Any clause may carry "neg": true for excluding/not. Market cap is in ₹ crore; percentages are plain numbers (20 means 20%).
"Beat earnings" means profit growth over the same quarter last year: {{"t":"cmp","field":"profyoy","op":">","v":0}}.
Use only these fields:
{fields}
Put anything you cannot express with these clauses in "unsupported"; never invent a field or a sector."""


def config():
    s = user_settings.load()
    return {"provider": s.get("llmProvider") or "off", "model": s.get("llmModel") or "", "base": s.get("llmBaseUrl") or "",
            "key": s.get("llmApiKey") or ""}


def _json(text):
    """The first JSON object in a model's reply (some local models wrap it in prose or ``` fences)."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        return json.loads(m.group(0)) if m else None


def _exe(name):
    """The real executable behind a CLI. npm on Windows installs a .CMD shim, and cmd.exe mangles multi-line or
    quote-heavy arguments (our system prompt, the JSON Schema): run the .exe the shim points at instead."""
    exe = shutil.which(name)
    if exe and exe.lower().endswith((".cmd", ".bat")):
        try:
            text = open(exe, encoding="utf-8", errors="replace").read()
        except OSError:
            return exe
        m = re.search(r'"%dp0%\\?([^"]+?\.exe)"', text, flags=re.I)
        if m:
            real = os.path.join(os.path.dirname(exe), m.group(1))
            if os.path.exists(real):
                return real
    return exe


def _claude(question, cfg):
    exe = _exe("claude")
    if not exe:
        raise RuntimeError("The claude CLI isn't on PATH. Install Claude Code and sign in once.")
    cmd = [exe, "-p", "--output-format", "json", "--json-schema", json.dumps(SCHEMA), "--system-prompt", _system(),
           "--tools", "", "--no-session-persistence"] + (["--model", cfg["model"]] if cfg["model"] else [])
    out = subprocess.run(cmd, input=question, capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT)
    if out.returncode:
        raise RuntimeError((out.stderr or out.stdout or "claude failed").strip()[:300])
    d = _json(out.stdout) or {}
    return d.get("structured_output") or _json(d.get("result") or "")


def _codex(question, cfg):
    exe = _exe("codex")
    if not exe:
        raise RuntimeError("The codex CLI isn't on PATH. Install Codex and sign in once.")
    with tempfile.TemporaryDirectory() as tmp:
        schema, last = os.path.join(tmp, "schema.json"), os.path.join(tmp, "out.json")
        with open(schema, "w", encoding="utf-8") as f:
            json.dump(_strict(SCHEMA), f)
        cmd = [exe, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-C", tmp, "--output-schema", schema,
               "-o", last] + (["-m", cfg["model"]] if cfg["model"] else []) + [f"{_system()}\n\nQuestion: {question}"]
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT, stdin=subprocess.DEVNULL)
        if out.returncode or not os.path.exists(last):
            raise RuntimeError((out.stderr or out.stdout or "codex failed").strip()[-300:])
        with open(last, encoding="utf-8") as f:
            return _json(f.read())


def _strict(schema):
    """OpenAI-style strict schemas want every property required and no extras: optional ones become nullable."""
    if schema.get("type") == "object":
        props = {k: _strict(v) for k, v in schema["properties"].items()}
        req = set(schema.get("required", []))
        for k, v in props.items():
            if k not in req:
                props[k] = {"anyOf": [v, {"type": "null"}]}
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    if schema.get("type") == "array":
        return {**schema, "items": _strict(schema["items"])}
    return {k: v for k, v in schema.items() if k != "description"}


def _openai(question, cfg):
    base = (PRESETS.get(cfg["base"]) or cfg["base"]).rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise RuntimeError("Set the server's base URL, e.g. http://localhost:11434/v1 for Ollama.")
    headers = {"Authorization": f"Bearer {cfg['key']}"} if cfg["key"] else {}
    body = {"model": cfg["model"] or "local", "temperature": 0,
            "messages": [{"role": "system", "content": _system()}, {"role": "user", "content": question}]}
    for fmt in ({"type": "json_schema", "json_schema": {"name": "screen", "schema": SCHEMA}}, {"type": "json_object"}, None):
        r = requests.post(f"{base}/chat/completions", json={**body, **({"response_format": fmt} if fmt else {})}, headers=headers, timeout=TIMEOUT)
        if r.status_code == 400 and fmt:
            continue                   # this server doesn't take that response_format: try the next, plainer one
        r.raise_for_status()
        return _json(r.json()["choices"][0]["message"]["content"])
    return None


BACKENDS = {"claude": _claude, "codex": _codex, "openai": _openai}


def read(question, parsed=None, cfg=None):
    """Question -> {clauses (validated), rejected, unsupported, source, cached, seconds[, error]}; None when off.
    Logged every time, cache hits included, so the UI can always say whether and how a model was used."""
    cfg = cfg or config()
    fn = BACKENDS.get(cfg["provider"])
    if not fn:
        return None

    def ask():
        try:
            d = fn(question, cfg)
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired, requests.RequestException) as e:
            return {"error": str(e)[:300]}
        if not isinstance(d, dict):
            return {"error": "The model didn't return JSON."}
        cl = [{k: v for k, v in c.items() if v is not None} for c in d.get("clauses") or [] if isinstance(c, dict)]
        good = [c for c in cl if deep.valid(c)]
        return {"clauses": good, "rejected": len(cl) - len(good), "unsupported": [u for u in d.get("unsupported") or [] if isinstance(u, str)]}

    fresh = {}

    def timed():
        t = time.time()
        out = ask()
        fresh["seconds"] = round(time.time() - t, 1)
        return out
    got = cached(("deep-llm", cfg["provider"], cfg["model"], cfg["base"], question.strip().lower()), 24 * 3600, timed)
    info = {**got, "source": cfg["provider"] + (f" · {cfg['model']}" if cfg["model"] else ""),
            "cached": "seconds" not in fresh, "seconds": fresh.get("seconds", 0.0)}
    LOG.appendleft({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "question": question[:200], "source": info["source"],
                    "cached": info["cached"], "seconds": info["seconds"], "ok": not got.get("error") and bool(got.get("clauses")),
                    "clauses": len(got.get("clauses") or []), "rejected": got.get("rejected", 0), "error": got.get("error")})
    return info


LOG = deque(maxlen=50)   # every model use this session, newest first: Settings shows it, so a call is never invisible


def log():
    return list(LOG)


def test(cfg=None):
    """Settings' 'Test' button: one known question through the configured backend."""
    cfg = cfg or config()
    if cfg["provider"] not in BACKENDS:
        return {"ok": False, "error": "Model fallback is off."}
    t = time.time()
    try:
        d = BACKENDS[cfg["provider"]]("IT or pharma stocks within 10% of their 52 week high, excluding small caps", cfg)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired, requests.RequestException) as e:
        return {"ok": False, "error": str(e)[:300]}
    cl = [c for c in (d or {}).get("clauses") or [] if isinstance(c, dict)]
    good = [c for c in ({k: v for k, v in c.items() if v is not None} for c in cl) if deep.valid(c)]
    return {"ok": bool(good), "seconds": round(time.time() - t, 1), "clauses": [deep.label(c) for c in good], "rejected": len(cl) - len(good)}
