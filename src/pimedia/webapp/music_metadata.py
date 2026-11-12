"""Transport et cache des métadonnées publiques. Chaque fournisseur définit ses projections et son rythme."""
import json
import threading
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime

from ..shared.external import USER_AGENT
from .exploration_entities import CachedMetadata

CACHE_SECONDS = 86400


class MusicSourceError(ValueError):
    """Échec public, exprimé par une clé i18n, sans URL ni secret du fournisseur."""


class MetadataHttp:
    def get(self, url, headers):
        headers = dict(headers, **{"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as response:
            return json.loads(response.read(8 * 1024 * 1024).decode("utf-8"))


class PublicMetadata:
    """Cache des seuls champs utilisés, expiré après une journée. Accès dédupliqués par fournisseur."""
    def __init__(self, repository, api_key, http=None, clock=time.time, sleep=time.sleep):
        self.repository, self.api_key = repository, api_key
        self.http, self.clock, self.sleep = http or MetadataHttp(), clock, sleep
        self.lock = threading.Lock()
        self.next_call = 0

    @property
    def enabled(self):
        return bool(self.api_key)

    def cached(self, key):
        self.repository.expire(self.prefix, int(self.clock() - CACHE_SECONDS))
        entry = self.repository.get(self.prefix + key)
        return entry.data if entry else None

    def read(self, key, url, headers, project, refresh=False):
        if not self.enabled:
            raise MusicSourceError("discovery.disabled")
        cached = None if refresh else self.cached(key)
        if cached is not None:
            return cached
        with self.lock:
            cached = None if refresh else self.cached(key)
            if cached is not None:
                return cached
            self._wait()
            data = self._fetch(url, headers, project)
            self.repository.save(CachedMetadata(self.prefix + key, data, int(self.clock())))
            return data

    def _wait(self):
        delay = self.next_call - self.clock()
        if delay > 2:
            raise MusicSourceError("discovery.rate_limited")
        if delay > 0:
            self.sleep(delay)
        self.next_call = self.clock() + self.interval

    def _fetch(self, url, headers, project):
        try:
            raw = self.http.get(url, headers)
            if not isinstance(raw, dict):
                raise ValueError("metadata response")
            return project(raw)
        except urllib.error.HTTPError as error:
            if error.code == 429:
                self._cooldown((error.headers or {}).get("Retry-After", "60"))
                raise MusicSourceError("discovery.rate_limited") from None
            raise MusicSourceError("discovery.unavailable") from None
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise MusicSourceError("discovery.unavailable") from None

    def _cooldown(self, value):
        try:
            delay = float(value)
        except ValueError:
            try:
                delay = parsedate_to_datetime(value).timestamp() - self.clock()
            except (TypeError, ValueError, OverflowError):
                delay = 60
        self.next_call = self.clock() + max(60, min(delay, 3600))
