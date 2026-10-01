"""BSE push stream: a stale cached certificate chain must repair itself, not silently demote SENSEX to 1-minute REST."""
import asyncio
import ssl

from orazio import bse_stream


def test_forget_chain_removes_the_cache_and_tolerates_it_being_absent(tmp_path, monkeypatch):
    chain = tmp_path / "chain.pem"
    chain.write_text("x")
    monkeypatch.setattr(bse_stream, "CHAIN_FILE", str(chain))
    bse_stream.forget_chain()
    assert not chain.exists()
    bse_stream.forget_chain()                                  # already gone: no error


def test_a_certificate_failure_drops_the_cached_chain_and_retries(monkeypatch):
    calls = {"forgot": 0, "sessions": 0}
    stream = bse_stream.BseStream()

    async def session():
        calls["sessions"] += 1
        if calls["sessions"] == 1:
            raise ssl.SSLCertVerificationError("unable to get local issuer certificate")
        raise asyncio.CancelledError                           # second attempt: stop the loop

    async def no_wait(_s):
        return None

    monkeypatch.setattr(stream, "_session", session)
    monkeypatch.setattr(bse_stream, "forget_chain", lambda: calls.__setitem__("forgot", calls["forgot"] + 1))
    monkeypatch.setattr(bse_stream.asyncio, "sleep", no_wait)
    try:
        asyncio.run(stream._forever())
    except asyncio.CancelledError:
        pass
    assert calls == {"forgot": 1, "sessions": 2}
    assert "SSLCertVerificationError" in stream.last_error


def test_other_failures_keep_the_cached_chain(monkeypatch):
    calls = {"forgot": 0, "sessions": 0}
    stream = bse_stream.BseStream()

    async def session():
        calls["sessions"] += 1
        if calls["sessions"] == 1:
            raise OSError("network down")
        raise asyncio.CancelledError

    async def no_wait(_s):
        return None

    monkeypatch.setattr(stream, "_session", session)
    monkeypatch.setattr(bse_stream, "forget_chain", lambda: calls.__setitem__("forgot", calls["forgot"] + 1))
    monkeypatch.setattr(bse_stream.asyncio, "sleep", no_wait)
    try:
        asyncio.run(stream._forever())
    except asyncio.CancelledError:
        pass
    assert calls["forgot"] == 0
