import unittest

from lru_ttl_cache import LRUTTLCache


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now


class TestConstruction(unittest.TestCase):
    def test_rejects_zero_capacity(self):
        with self.assertRaises(ValueError):
            LRUTTLCache(capacity=0, ttl=10.0)

    def test_rejects_negative_capacity(self):
        with self.assertRaises(ValueError):
            LRUTTLCache(capacity=-1, ttl=10.0)

    def test_rejects_zero_ttl(self):
        with self.assertRaises(ValueError):
            LRUTTLCache(capacity=4, ttl=0.0)

    def test_rejects_negative_ttl(self):
        with self.assertRaises(ValueError):
            LRUTTLCache(capacity=4, ttl=-1.0)


class TestLRUEviction(unittest.TestCase):
    def test_evicts_least_recently_used(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=2, ttl=1000.0, clock=clock)
        cache["a"] = 1
        cache["b"] = 2
        cache["a"]  # bump "a" to most-recently-used
        clock.now += 1.0
        cache["c"] = 3  # capacity exceeded, "b" should be evicted
        self.assertNotIn("b", cache)
        self.assertIn("a", cache)
        self.assertIn("c", cache)

    def test_set_existing_key_does_not_evict(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=2, ttl=1000.0, clock=clock)
        cache["a"] = 1
        cache["b"] = 2
        cache["a"] = 10  # update, not a new insert
        self.assertEqual(len(cache), 2)
        self.assertEqual(cache["a"], 10)


class TestTTLEviction(unittest.TestCase):
    def test_get_after_expiry_returns_default_and_removes(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=4, ttl=5.0, clock=clock)
        cache["a"] = 1
        clock.now = 5.0  # exactly at the boundary: 0 + 5 <= 5 -> expired
        self.assertIsNone(cache.get("a"))
        self.assertNotIn("a", cache)

    def test_get_just_before_expiry_is_live(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=4, ttl=5.0, clock=clock)
        cache["a"] = 1
        clock.now = 4.9999
        self.assertEqual(cache["a"], 1)

    def test_getitem_after_expiry_raises_keyerror(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=4, ttl=5.0, clock=clock)
        cache["a"] = 1
        clock.now = 10.0
        with self.assertRaises(KeyError):
            cache["a"]

    def test_renew_ttl_on_overwrite(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=4, ttl=5.0, clock=clock)
        cache["a"] = 1
        clock.now = 4.0
        cache["a"] = 2  # fresh write resets the expiry clock
        clock.now = 8.0  # past original expiry, within new one
        self.assertEqual(cache["a"], 2)

    def test_contains_false_after_expiry(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=4, ttl=5.0, clock=clock)
        cache["a"] = 1
        clock.now = 5.0
        self.assertNotIn("a", cache)


class TestSweepAndLen(unittest.TestCase):
    def test_len_excludes_expired(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=4, ttl=5.0, clock=clock)
        cache["a"] = 1
        cache["b"] = 2
        clock.now = 5.0  # both expired
        self.assertEqual(len(cache), 0)

    def test_del_missing_raises_keyerror(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=4, ttl=5.0, clock=clock)
        with self.assertRaises(KeyError):
            del cache["nope"]

    def test_del_after_expiry_raises_keyerror(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=4, ttl=5.0, clock=clock)
        cache["a"] = 1
        clock.now = 5.0
        with self.assertRaises(KeyError):
            del cache["a"]

    def test_clear(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=4, ttl=5.0, clock=clock)
        cache["a"] = 1
        cache.clear()
        self.assertEqual(len(cache), 0)
        self.assertNotIn("a", cache)


class TestGet(unittest.TestCase):
    def test_get_missing_returns_default(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=4, ttl=5.0, clock=clock)
        self.assertIsNone(cache.get("missing"))
        self.assertEqual(cache.get("missing", "fallback"), "fallback")

    def test_get_bumps_recency(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=2, ttl=1000.0, clock=clock)
        cache["a"] = 1
        cache["b"] = 2
        cache.get("a")  # bump "a"
        clock.now += 1.0
        cache["c"] = 3  # evict "b", not "a"
        self.assertIn("a", cache)
        self.assertNotIn("b", cache)

    def test_set_alias_works(self):
        clock = FakeClock()
        cache = LRUTTLCache(capacity=4, ttl=5.0, clock=clock)
        cache.set("a", 1)
        self.assertEqual(cache.get("a"), 1)


if __name__ == "__main__":
    unittest.main()
