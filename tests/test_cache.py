"""The TTL cache: concurrent misses call upstream once, and expired keys don't pile up."""
import threading
import time

from orazio import cache


def test_concurrent_misses_call_upstream_once():
    calls = []

    def slow():
        calls.append(1)
        time.sleep(0.05)
        return "v"

    results = []
    threads = [threading.Thread(target=lambda: results.append(cache.cached("k", 10, slow))) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1
    assert results == ["v"] * 8


def test_expired_entry_is_refetched():
    cache.cached("k", 10, lambda: 1)
    cache._store["k"] = (time.time() - 11, 1, 10)
    assert cache.cached("k", 10, lambda: 2) == 2


def test_expired_keys_are_swept_once_the_store_is_large(monkeypatch):
    monkeypatch.setattr(cache, "PRUNE_AT", 3)
    old = time.time() - 100
    for i in range(3):
        cache._store[("old", i)] = (old, i, 1)
    cache.cached("new", 60, lambda: "fresh")
    assert list(cache._store) == ["new"]
