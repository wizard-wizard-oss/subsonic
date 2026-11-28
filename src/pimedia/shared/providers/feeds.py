"""Client unique des flux RSS/Atom et de leurs images : HTTP public, cadence et cache borné."""
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from ..images import image_type
from .http import HttpClient, NotPublic, TooLarge, is_public_host  # noqa: F401 (compatibilité podcasts)
from .metadata import Pacer, ProviderUnavailable, TRANSIENT_ERRORS

MAX_FEED_BYTES = 6 * 1024 * 1024
MAX_IMAGE_BYTES = 4 * 1024 * 1024
IMAGE_CACHE_BYTES = 16 * 1024 * 1024
IMAGE_CACHE_ITEMS = 64
IMAGE_CACHE_SECONDS = 3600


class FeedError(Exception):
    """Flux ou image illisible, trop volumineux ou situé sur un réseau privé."""


@dataclass(frozen=True)
class FeedImage:
    mime: str
    data: bytes


def check_feed_url(url):
    try:
        HttpClient().check_public(url)
    except (NotPublic, ValueError):
        raise FeedError("Adresse de flux refusée") from None


class FeedFetcher:
    def __init__(self, http=None, clock=time.monotonic, pacer=None):
        self.http = http or HttpClient(timeout=15, max_bytes=MAX_FEED_BYTES)
        self.clock = clock
        self.pacer = pacer or Pacer(.05)
        self._images, self._lock = OrderedDict(), threading.Lock()

    def _read(self, url, accept):
        for attempt in range(2):
            try:
                self.pacer.wait()
                data = self.http.get_bytes(url, accept=accept, public_only=True)
                if len(data) > MAX_FEED_BYTES:
                    raise TooLarge("Flux trop volumineux")
                return data
            except (NotPublic, TooLarge, ProviderUnavailable):
                raise FeedError("Adresse refusée ou réponse trop volumineuse") from None
            except (OSError, ValueError) as error:
                if attempt or isinstance(error, ValueError) or getattr(error, "code", None) not in TRANSIENT_ERRORS | {None}:
                    raise FeedError("Flux injoignable") from None

    def fetch(self, url, timeout=15):
        """Octets du flux ; les limites et redirections sont contrôlées par le transport commun."""
        return self._read(url, "application/rss+xml, application/atom+xml, text/html, */*")

    def image(self, url):
        with self._lock:
            hit = self._images.get(url)
            if hit and self.clock() - hit[0] < IMAGE_CACHE_SECONDS:
                self._images.move_to_end(url)
                return hit[1]
            self._images.pop(url, None)
        data = self._read(url, "image/jpeg,image/png,image/webp,image/gif")
        mime = image_type(data)
        if not mime or len(data) > MAX_IMAGE_BYTES:
            raise FeedError("Image refusée")
        image = FeedImage(mime, data)
        with self._lock:
            self._images[url] = (self.clock(), image)
            while (len(self._images) > IMAGE_CACHE_ITEMS or
                   sum(len(entry[1].data) for entry in self._images.values()) > IMAGE_CACHE_BYTES):
                self._images.popitem(last=False)
        return image
