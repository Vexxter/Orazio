"""A tiny TTL cache for coalescing concurrent polls (several tabs / retries)."""
import time

_store = {}


def cached(key, ttl, fn):
    now = time.time()
    hit = _store.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = fn()
    _store[key] = (now, value)
    return value
