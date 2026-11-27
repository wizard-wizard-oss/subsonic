"""Socle des services externes : cache par préfixe, cadence par service, une reprise, copie périmée en secours."""
import threading
import time
import urllib.error
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

from .cache import CachedMetadata
from .http import HttpClient

TRANSIENT_ERRORS = {429, 500, 502, 503, 504}
RETRY_DELAY = 2           # une seule reprise immédiate, si le service ne demande pas d'attendre plus
MAX_WAIT = 2              # au-delà, la cadence répond « trop de demandes » au lieu de bloquer la page
MIN_BACKOFF = 60


class ProviderUnavailable(ValueError):
    """Échec public, exprimé par une clé i18n, sans URL ni secret du service."""


@dataclass(frozen=True)
class Fetched:
    data: dict
    stale: bool = False


def retry_after(error, now):
    """Délai demandé par le service (en secondes), ou None s'il n'en donne pas."""
    value = (getattr(error, "headers", None) or {}).get("Retry-After", "")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, parsedate_to_datetime(value).timestamp() - now)
        except (TypeError, ValueError, OverflowError):
            return None


class PublicMetadata:
    prefix = ""
    interval = 1.0
    ttl = 86400
    stale_ttl = 30 * 86400

    def __init__(self, store, http=None, clock=time.time, sleep=time.sleep):
        if not self.prefix:
            raise TypeError("prefix")
        self.store, self.http = store, http or HttpClient()
        self.clock, self.sleep = clock, sleep
        self._guard, self._locks, self._retry_at = threading.Lock(), {}, {}
        self._pace, self._next_call = threading.Lock(), 0.0

    @property
    def enabled(self):
        return True

    def fetch(self, key, url, *, read=None, ttl=None, headers=None, refresh=False):
        if not self.enabled:
            raise ProviderUnavailable("discovery.disabled")
        key, ttl = self.prefix + key, self.ttl if ttl is None else ttl
        cached = self._fresh(key, ttl, refresh)
        if isinstance(cached, Fetched):
            return cached
        with self._lock(key):
            cached = self._fresh(key, ttl, refresh)
            if isinstance(cached, Fetched):
                return cached
            if self.clock() < self._retry_at.get(key, 0):
                return self._fallback(cached, "discovery.unavailable")
            try:
                data = self._attempts(url, read or (lambda address: self.http.get_json(address, headers)))
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                return self._failed(key, cached, error)
            self._retry_at.pop(key, None)
            now = int(self.clock())
            self.store.save(CachedMetadata(key, data, now))
            self.store.expire(self.prefix, now - self.stale_ttl)
            return Fetched(data)

    def _fresh(self, key, ttl, refresh):
        cached = self.store.get(key)
        if cached and not refresh and self.clock() - cached.fetched_at < ttl:
            return Fetched(cached.data)
        return cached

    def _lock(self, key):
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def _wait_turn(self):
        with self._pace:
            delay = self._next_call - self.clock()
            if delay > MAX_WAIT:
                raise ProviderUnavailable("discovery.rate_limited")
            if delay > 0:
                self.sleep(delay)
            self._next_call = self.clock() + self.interval

    def _attempts(self, url, read):
        for attempt in range(2):
            self._wait_turn()
            try:
                data = read(url)
                if not isinstance(data, dict):
                    raise ValueError("metadata response")
                return data
            except ProviderUnavailable:
                raise
            except (OSError, ValueError) as error:
                delay = self._retry_delay(error)
                if attempt or delay is None or delay > RETRY_DELAY:
                    raise
                self.sleep(max(RETRY_DELAY, delay))

    def _retry_delay(self, error):
        if not isinstance(error, urllib.error.HTTPError):
            return RETRY_DELAY if isinstance(error, OSError) else None
        if error.code not in TRANSIENT_ERRORS:
            return None
        asked = retry_after(error, self.clock())
        return asked if asked is not None else RETRY_DELAY

    def _failed(self, key, cached, error):
        code = "discovery.unavailable"
        if isinstance(error, ProviderUnavailable):
            code = str(error)
        elif isinstance(error, urllib.error.HTTPError) and error.code == 429:
            code = "discovery.rate_limited"
            asked = retry_after(error, self.clock())
            self._next_call = self.clock() + max(MIN_BACKOFF, min(asked if asked is not None else MIN_BACKOFF, 3600))
        delay = self._retry_delay(error) if not isinstance(error, ProviderUnavailable) else None
        self._retry_at = {k: date for k, date in self._retry_at.items() if date > self.clock()}
        if delay is not None:
            self._retry_at[key] = self.clock() + max(MIN_BACKOFF, delay)
        return self._fallback(cached, code)

    def _fallback(self, cached, code):
        if cached and self.clock() - cached.fetched_at < self.stale_ttl:
            return Fetched(cached.data, stale=True)
        raise ProviderUnavailable(code)
