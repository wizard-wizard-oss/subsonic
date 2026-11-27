"""Socle des services externes : cache par préfixe, cadence par service, une reprise, copie périmée en secours."""
import threading
import time
import urllib.error
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

from .cache import CachedMetadata
from .http import HttpClient

TRANSIENT_ERRORS = {429, 500, 502, 503, 504}
GONE = {404, 410}
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


class Pacer:
    """Un départ de requête par intervalle pour un service, quel que soit l'appelant (horloge réelle)."""
    def __init__(self, interval, clock=time.monotonic, sleep=time.sleep):
        self.interval, self.clock, self.sleep = interval, clock, sleep
        self.lock, self.next_call = threading.Lock(), 0.0

    def wait(self):
        with self.lock:
            delay = self.next_call - self.clock()
            if delay > MAX_WAIT:
                raise ProviderUnavailable("discovery.rate_limited")
            if delay > 0:
                self.sleep(delay)
            self.next_call = self.clock() + self.interval

    def hold(self, seconds):
        """Le service a demandé d'attendre : aucun départ avant ce délai."""
        with self.lock:
            self.next_call = max(self.next_call, self.clock() + seconds)


class PublicMetadata:
    prefix = ""
    interval = 1.0
    ttl = 86400
    stale_ttl = 30 * 86400

    unavailable_code = "discovery.unavailable"

    def __init__(self, store, http=None, clock=time.time, sleep=time.sleep, pacer=None):
        if not self.prefix:
            raise TypeError("prefix")
        self.store, self.http = store, http or HttpClient()
        self.clock, self.sleep = clock, sleep
        self.pacer = pacer or Pacer(self.interval)
        self._guard, self._locks, self._retry_at = threading.Lock(), {}, {}

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
            until, code = self._retry_at.get(key, (0, self.unavailable_code))
            if self.clock() < until:
                return self._fallback(None if refresh else cached, code)
            try:
                data = self._attempts(url, read or (lambda address: self.http.get_json(address, headers)))
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                # Un rafraîchissement demandé ne se contente pas de l'ancienne copie : l'échec est signalé.
                return self._failed(key, None if refresh else cached, error)
            self._retry_at.pop(key, None)
            now = int(self.clock())
            self.store.save(CachedMetadata(key, data, now))
            self.store.expire(self.prefix, now - self.stale_ttl)
            return Fetched(data)

    def cached(self, key, ttl=None):
        """Données encore fraîches en cache, sans aucun appel au service (None sinon)."""
        entry = self.store.get(self.prefix + key)
        if entry and self.clock() - entry.fetched_at < (self.ttl if ttl is None else ttl):
            return entry.data
        return None

    def _fresh(self, key, ttl, refresh):
        cached = self.store.get(key)
        if cached and not refresh and self.clock() - cached.fetched_at < ttl:
            return Fetched(cached.data)
        return cached

    def _lock(self, key):
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def _attempts(self, url, read):
        for attempt in range(2):
            self.pacer.wait()
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
        code = self.unavailable_code
        if isinstance(error, ProviderUnavailable):
            code = str(error)
        elif isinstance(error, urllib.error.HTTPError) and error.code == 429:
            code = "discovery.rate_limited"
            asked = retry_after(error, self.clock())
            self.pacer.hold(max(MIN_BACKOFF, min(asked if asked is not None else MIN_BACKOFF, 3600)))
        elif isinstance(error, urllib.error.HTTPError) and error.code in GONE:
            # L'entité n'existe plus : ni reprise ni copie périmée.
            raise ProviderUnavailable(code) from None
        delay = self._retry_delay(error) if not isinstance(error, ProviderUnavailable) else None
        self._retry_at = {k: entry for k, entry in self._retry_at.items() if entry[0] > self.clock()}
        if delay is not None:
            self._retry_at[key] = (self.clock() + max(MIN_BACKOFF, delay), code)
        return self._fallback(cached, code)

    def _fallback(self, cached, code):
        if cached and self.clock() - cached.fetched_at < self.stale_ttl:
            return Fetched(cached.data, stale=True)
        raise ProviderUnavailable(code)
