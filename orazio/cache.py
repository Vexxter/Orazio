"""A tiny TTL cache for coalescing concurrent polls (several tabs / retries).

One lock per key: when an entry expires and several threads ask for it at once, only the first
calls upstream and the rest wait for its answer, instead of all of them hitting NSE/Yahoo together.
Expired entries are swept once the store grows past PRUNE_AT, so keys for symbols nobody looks at
any more don't pile up for the life of the process.
"""
import threading
import time

PRUNE_AT = 512

_store = {}   # key -> (stored_at, value, ttl)
_locks = {}
_locks_guard = threading.Lock()


def _lock_for(key):
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.Lock()
        return lock


def _fresh(hit, ttl, now):
    return hit is not None and now - hit[0] < ttl


def _prune(now):
    for key, hit in list(_store.items()):
        if now - hit[0] >= hit[2]:
            _store.pop(key, None)
            with _locks_guard:
                _locks.pop(key, None)


def cached(key, ttl, fn):
    hit = _store.get(key)
    if _fresh(hit, ttl, time.time()):
        return hit[1]
    with _lock_for(key):
        hit = _store.get(key)                 # another thread may have refreshed it while we waited
        if _fresh(hit, ttl, time.time()):
            return hit[1]
        value = fn()
        now = time.time()
        _store[key] = (now, value, ttl)
    if len(_store) > PRUNE_AT:
        _prune(now)
    return value
