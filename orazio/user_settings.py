"""The user's own settings on disk (~/.orazio/settings.json): notification channels and the daily brief.

Secrets stay on this machine and are never sent back to the page: public() masks them, and an empty value in an
update means "keep what's stored", so the settings form can round-trip without ever holding a token.
"""
import json
import os
import re
import threading
from pathlib import Path

FILE = Path.home() / ".orazio" / "settings.json"
SECRETS = {"telegramToken", "smtpPassword", "llmApiKey"}
DEFAULTS = {
    "desktop": True,
    "telegramToken": "", "telegramChat": "",
    "webhookUrl": "",
    "smtpHost": "", "smtpPort": 587, "smtpUser": "", "smtpPassword": "", "emailTo": "",
    "briefEnabled": False, "briefTime": "09:00",
    # deep search's model fallback (deep_llm.py): off | claude | codex | openai (any OpenAI-compatible server)
    "llmProvider": "off", "llmBaseUrl": "", "llmModel": "", "llmApiKey": "",
}
LLM_PROVIDERS = ("off", "claude", "codex", "openai")
_lock = threading.Lock()


def load():
    try:
        saved = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def public():
    """Settings for the page: a secret shows only whether it is set."""
    s = load()
    return {k: bool(v) if k in SECRETS else v for k, v in s.items()}


def _check(k, v):
    if isinstance(DEFAULTS[k], bool):
        if not isinstance(v, bool):
            raise ValueError(f"{k} must be true or false")
    elif isinstance(DEFAULTS[k], int):
        if isinstance(v, bool) or not isinstance(v, int) or not 0 < v < 65536:
            raise ValueError(f"{k} must be a port number")
    elif not isinstance(v, str):
        raise ValueError(f"{k} must be text")
    if k == "webhookUrl" and v and not v.startswith(("http://", "https://")):
        raise ValueError("The webhook must be an http:// or https:// URL")
    if k == "llmProvider" and v not in LLM_PROVIDERS:
        raise ValueError(f"The model fallback must be one of: {', '.join(LLM_PROVIDERS)}")
    if k == "llmBaseUrl" and v and not v.startswith(("http://", "https://")) and v not in ("ollama", "lmstudio", "llamacpp", "openrouter", "vllm"):
        raise ValueError("The model server must be an http:// or https:// URL")
    if k == "llmModel" and not re.fullmatch(r"[\w.:/@+-]{0,120}", v):
        raise ValueError("The model name has characters a model name can't have")
    if k == "briefTime" and not (len(v) == 5 and v[2] == ":" and v[:2].isdigit() and v[3:].isdigit() and int(v[:2]) < 24 and int(v[3:]) < 60):
        raise ValueError("The brief time must be HH:MM")


def update(changes):
    with _lock:
        s = load()
        for k, v in changes.items():
            if k not in DEFAULTS:
                raise ValueError(f"Unknown setting: {k}")
            if k in SECRETS and not v:
                continue                   # blank means keep; the page never holds the stored value
            _check(k, v)
            s[k] = v
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=1), encoding="utf-8")
        os.chmod(tmp, 0o600)               # holds tokens: owner only (a no-op beyond read-only on Windows)
        os.replace(tmp, FILE)
    return public()


def clear_secret(key):
    if key not in SECRETS:
        raise ValueError(f"Unknown secret: {key}")
    with _lock:
        s = load()
        s[key] = ""
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text(json.dumps(s, indent=1), encoding="utf-8")
    return public()
