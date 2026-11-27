"""Socle commun des services externes : cache, cadence, reprise, copie périmée et expiration."""
import threading
import time
import unittest
from urllib.error import HTTPError, URLError

from pimedia.shared.providers.cache import CachedMetadata, MemoryStore
from pimedia.shared.providers.metadata import Fetched, ProviderUnavailable, PublicMetadata


class Fake(PublicMetadata):
    prefix = "fake:"
    interval = 1
    ttl = 60


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def http_error(code, retry_after=None):
    return HTTPError("https://api.test", code, "error", {"Retry-After": retry_after} if retry_after else {}, None)


class PublicMetadataTest(unittest.TestCase):
    def setUp(self):
        self.store, self.clock = MemoryStore(), Clock()
        self.provider = Fake(self.store, clock=self.clock, sleep=self.clock.sleep)
        self.calls = []

    def reader(self, *results):
        results = list(results)

        def read(url):
            self.calls.append(url)
            result = results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return read

    def test_fresh_copy_skips_network(self):
        self.store.save(CachedMetadata("fake:a", {"v": 1}, int(self.clock.now) - 10))
        self.assertEqual(self.provider.fetch("a", "https://api.test/a", read=self.reader()), Fetched({"v": 1}))
        self.assertEqual(self.calls, [])

    def test_403_serves_stale_copy(self):
        self.store.save(CachedMetadata("fake:a", {"v": 1}, int(self.clock.now) - 3600))
        result = self.provider.fetch("a", "https://api.test/a", read=self.reader(http_error(403)))
        self.assertEqual(result, Fetched({"v": 1}, stale=True))

    def test_no_copy_raises_provider_unavailable(self):
        with self.assertRaises(ProviderUnavailable) as raised:
            self.provider.fetch("a", "https://api.test/a", read=self.reader(http_error(404)))
        self.assertEqual(str(raised.exception), "discovery.unavailable")
        with self.assertRaises(ProviderUnavailable) as raised:
            self.provider.fetch("b", "https://api.test/b", read=self.reader(http_error(429, "120")))
        self.assertEqual(str(raised.exception), "discovery.rate_limited")

    def test_retry_once_on_503_then_succeeds(self):
        result = self.provider.fetch("a", "https://api.test/a", read=self.reader(http_error(503), {"v": 2}))
        self.assertEqual(result, Fetched({"v": 2}))
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.store.get("fake:a").data, {"v": 2})

    def test_network_error_without_retry_after_retries_once(self):
        with self.assertRaises(ProviderUnavailable):
            self.provider.fetch("a", "https://api.test/a", read=self.reader(URLError("down"), URLError("down")))
        self.assertEqual(len(self.calls), 2)

    def test_save_expires_old_entries_of_prefix_only(self):
        old = int(self.clock.now) - Fake.stale_ttl - 1
        self.store.save(CachedMetadata("fake:old", {"v": 0}, old))
        self.store.save(CachedMetadata("other:old", {"v": 0}, old))
        self.provider.fetch("new", "https://api.test/new", read=self.reader({"v": 1}))
        self.assertIsNone(self.store.get("fake:old"))
        self.assertIsNotNone(self.store.get("other:old"))

    def test_non_dict_answer_is_unavailable(self):
        with self.assertRaises(ProviderUnavailable):
            self.provider.fetch("a", "https://api.test/a", read=self.reader([], []))

    def test_two_keys_do_not_wait_on_each_other(self):
        provider = Fake(MemoryStore())     # vraie horloge : la clé rapide n'attend que la cadence
        release, done = threading.Event(), {}

        def slow(url):
            release.wait(5)
            return {"slow": True}

        thread = threading.Thread(target=lambda: provider.fetch("slow", "https://api.test/slow", read=slow))
        thread.start()
        started = time.monotonic()
        done["fast"] = provider.fetch("fast", "https://api.test/fast", read=lambda url: {"fast": True})
        elapsed = time.monotonic() - started
        release.set()
        thread.join(5)
        self.assertEqual(done["fast"], Fetched({"fast": True}))
        self.assertLess(elapsed, Fake.interval + 0.5)


if __name__ == "__main__":
    unittest.main()
