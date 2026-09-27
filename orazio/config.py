"""Environment-driven app settings.

Kept deliberately tiny: everything a deployer needs to change between local
dev and a shared environment, and nothing else.
"""
import os


class Settings:
    # Flask's debugger gives remote code execution to anyone who can trigger an
    # unhandled exception — it must never be on by default outside local dev.
    DEBUG = os.environ.get("ORAZIO_DEBUG", "1") == "1"
    HOST = os.environ.get("ORAZIO_HOST", "127.0.0.1")
    PORT = int(os.environ.get("ORAZIO_PORT", "5000"))


settings = Settings()
