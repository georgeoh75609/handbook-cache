# LRU TTL Cache

A bounded in-memory cache that evicts on two conditions at once: when it exceeds a fixed capacity (least-recently-used first) and when entries pass a time-to-live deadline. Zero third-party dependencies; standard library only.

```python
from lru_ttl_cache import LRUTTLCache

cache = LRUTTLCache(capacity=100, ttl=60.0)
cache["key"] = "value"
assert cache.get("key") == "value"
assert "key" in cache

# Deterministic testing: pass your own clock.
class FakeClock:
    def __init__(self, start=0.0):
        self.now = start
    def __call__(self):
        return self.now

clock = FakeClock()
c = LRUTTLCache(capacity=2, ttl=5.0, clock=clock)
c["a"] = 1
assert c["a"] == 1
clock.now = 5.0
assert c.get("a") is None  # expired
```

## Why

A cache that only does LRU silently leaks stale data; a cache that only does TTL can grow unboundedly under key churn. Either failure mode is bad enough to bring down a service that assumed the cache was a fixed-cost structure. This library makes both limits explicit and enforceable.

The trade-off: expiry is lazy. There is no background sweeper thread. Expired entries are removed when they are touched (get, set, contains, len) or when a subsequent sweep observes them. Lazy expiry is the right call for a zero-dependency library: no timer thread to leak, no lock ordering to get wrong, no clock races. The cost is that an idle cache retains expired entries in memory until they are next accessed. If that is unacceptable, call `clear()` periodically from your own scheduler.

## Edges you will hit

- TTL is inclusive at the boundary: an entry set at `t=0` with `ttl=5` is considered expired at `now=5` (`0 + 5 <= 5`). This matches `<=` semantics and keeps tests deterministic without float epsilon.
- `del cache[k]` on a key that has already expired by the clock raises `KeyError`, consistent with `k in cache` returning `False`. The expiry is observed, not the historical presence.
- The clock defaults to `time.monotonic`, not `time.time`. Monotonic time cannot step backwards under NTP, so already-expired entries cannot be resurrected. If you pass your own clock, it must be non-decreasing.
- `__contains__` triggers a recency bump, same as `get`. If you want to peek without affecting eviction order, do not use `in`; there is no peek method on purpose, to keep the surface small.

## Exports

- `LRUTTLCache(capacity: int, ttl: float, *, clock: Callable[[], float] = time.monotonic)`
  - Methods: `__getitem__`, `__setitem__`, `__delitem__`, `__contains__`, `__len__`, `get(key, default=None)`, `set(key, value)`, `clear()`.
