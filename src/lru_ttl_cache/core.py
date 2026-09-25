from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable, Generic, Hashable, Optional, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class LRUTTLCache(Generic[K, V]):
    """A bounded cache that evicts on BOTH access order (LRU) and age (TTL).

    Two policies must agree before an entry is considered live:
    it must be within the capacity window AND within the TTL window. Either
    condition expiring removes the entry. The TTL check happens lazily on
    access and on any insertion; we never spawn a timer thread. Lazy expiry
    is the right call for a zero-dependency library: no background thread to
    manage lifecycle for, no locks, no races with the clock.

    The clock is injectable (default: `time.monotonic`) so callers can drive
    deterministic tests. We intentionally use `monotonic` and not
    `time.time`, because `time.time` can go backwards on NTP step and would
    silently resurrect already-expired entries.
    """

    def __init__(
        self,
        capacity: int,
        ttl: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity!r}")
        if ttl <= 0:
            raise ValueError(f"ttl must be > 0, got {ttl!r}")
        # OrderedDict gives us O(1) move-to-end for LRU recency updates and
        # O(1) popitem(last=False) for eviction. A plain dict preserves
        # insertion order in 3.7+ but lacks the atomic recency bump we need.
        self._data: "OrderedDict[K, tuple[V, float]]" = OrderedDict()
        self._capacity = capacity
        self._ttl = ttl
        self._clock = clock

    def __len__(self) -> int:
        # Length of the live view, not the backing map. Expired-but-not-yet-
        # swept entries do not count toward what the caller can observe.
        self._sweep()
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        # `key` is `object`, not `K`, because Python's `in` operator accepts
        # any operand; we do the hashable check implicitly via __getitem__.
        try:
            self._get(key)  # type: ignore[arg-type]
            return True
        except KeyError:
            return False

    def __getitem__(self, key: K) -> V:
        return self._get(key)

    def get(self, key: K, default: Any = None) -> Any:
        try:
            return self._get(key)
        except KeyError:
            return default

    def __setitem__(self, key: K, value: V) -> None:
        now = self._clock()
        # Re-setting a key is a value+expiry update; it also counts as the
        # most-recent access, so move_to_end. We delete first to keep the
        # semantics unambiguous (fresh insertion, fresh expiry).
        if key in self._data:
            del self._data[key]
        self._data[key] = (value, now)
        self._data.move_to_end(key, last=True)
        self._enforce_capacity()

    def set(self, key: K, value: V) -> None:
        # Alias for callers who prefer an explicit method over `[]`.
        self[key] = value

    def __delitem__(self, key: K) -> None:
        # Pre-sweep so a key that expired at the current clock reading is
        # reported as missing (KeyError) rather than silently dropped. This
        # keeps `del cache[k]` consistent with `k in cache`.
        self._sweep()
        del self._data[key]

    def _get(self, key: K) -> V:
        now = self._clock()
        if key not in self._data:
            raise KeyError(key)
        value, expires_at = self._data[key]
        if expires_at + self._ttl <= now:
            # Lazy expiry: entry is stale. Delete before raising so the next
            # access does not have to re-discover this.
            del self._data[key]
            raise KeyError(key)
        # Recency bump: this access makes the entry the most-recently-used.
        self._data.move_to_end(key, last=True)
        return value

    def _enforce_capacity(self) -> None:
        # Evict strictly on insertion, oldest-first. We deliberately do not
        # count TTL-expiry against capacity here; sweep handles expiry.
        while len(self._data) > self._capacity:
            self._data.popitem(last=False)

    def _sweep(self) -> None:
        now = self._clock()
        # Walk once; erase in-place via list of keys to avoid mutating the
        # OrderedDict while iterating its view. A second pass is not needed:
        # entries are inserted in LRU order, so once we pass the boundary the
        # rest are older or equal — but TTL is independent of recency, so we
        # scan the whole structure rather than breaking early.
        expired = [
            k for k, (_v, exp) in self._data.items() if exp + self._ttl <= now
        ]
        for k in expired:
            del self._data[k]

    def clear(self) -> None:
        self._data.clear()
