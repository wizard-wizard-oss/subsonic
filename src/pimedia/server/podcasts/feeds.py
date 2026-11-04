"""Lecture des flux RSS de podcasts (réseau protégé, XML sans entités, résultat limité)."""
import hashlib
import ipaddress
import re
import socket
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
USER_AGENT = "PiMediaStation/1.0 (lecteur personnel)"
MAX_FEED_BYTES = 6 * 1024 * 1024
MAX_EPISODES = 300


class FeedError(Exception):
    """Flux illisible ou refusé : le message peut être montré à l'utilisateur."""


# ---------- fonctions pures ----------
def parse_duration(text):
    """« 1:02:03 », « 12:30 » ou « 754 » -> secondes (0 si illisible)."""
    parts = (text or "").strip().split(":")
    try:
        numbers = [int(float(p)) for p in parts if p != ""]
    except ValueError:
        return 0
    seconds = 0
    for number in numbers[-3:]:
        seconds = seconds * 60 + number
    return seconds


def parse_date(text):
    """Date RFC 822 -> secondes depuis 1970 (0 si illisible)."""
    try:
        return int(parsedate_to_datetime(text).timestamp())
    except (TypeError, ValueError, IndexError):
        return 0


def plain_text(html, limit=600):
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def episode_id(audio_url, guid=""):
    return hashlib.sha1((guid or audio_url).encode("utf-8")).hexdigest()[:16]


def _text(node, tag):
    child = node.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _image(node):
    picture = node.find(ITUNES_NS + "image")
    if picture is not None and picture.get("href"):
        return picture.get("href")
    return _text(node.find("image"), "url") if node.find("image") is not None else ""


def _episode(item, fallback_image):
    enclosure = item.find("enclosure")
    audio = enclosure.get("url", "") if enclosure is not None else ""
    if not audio:
        return None
    description = _text(item, "description") or _text(item, ITUNES_NS + "summary")
    return {"id": episode_id(audio, _text(item, "guid")), "title": _text(item, "title") or "Épisode",
            "audio": audio, "duration": parse_duration(_text(item, ITUNES_NS + "duration")),
            "date": parse_date(_text(item, "pubDate")), "desc": plain_text(description),
            "image": _image(item) or fallback_image}


def parse_feed(data):
    """Octets d'un flux RSS -> {"title", "author", "image", "desc", "episodes": [...]} (récents d'abord)."""
    if b"<!ENTITY" in data:             # entités définies par le flux : risque d'explosion de mémoire
        raise FeedError("Flux refusé (déclarations XML non autorisées)")
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise FeedError("Flux illisible")
    channel = root.find("channel")
    if channel is None:
        raise FeedError("Ce n’est pas un flux de podcast")
    image = _image(channel)
    episodes = [e for e in (_episode(i, image) for i in channel.findall("item")) if e]
    episodes.sort(key=lambda e: -e["date"])
    return {"title": _text(channel, "title"), "author": _text(channel, ITUNES_NS + "author"), "image": image,
            "desc": plain_text(_text(channel, "description")), "episodes": episodes[:MAX_EPISODES],
            "language": _text(channel, "language").lower()}


# ---------- réseau ----------
def is_public_host(host):
    """Faux pour une adresse locale ou privée (on ne va pas lire le réseau de la maison à la demande d'une page)."""
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        return False
    return bool(addresses) and all(not _private(a) for a in addresses)


def _private(address):
    ip = ipaddress.ip_address(address.split("%")[0])
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast


def check_feed_url(url):
    parts = urllib.parse.urlsplit(url or "")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FeedError("Adresse de flux invalide")
    if not is_public_host(parts.hostname):
        raise FeedError("Adresse de flux refusée")


class FeedFetcher:
    def fetch(self, url, timeout=15):
        check_feed_url(url)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, */*"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                check_feed_url(response.geturl())          # une redirection ne doit pas mener ailleurs
                data = response.read(MAX_FEED_BYTES + 1)
        except OSError as error:
            raise FeedError("Flux injoignable (%s)" % getattr(error, "reason", error))
        if len(data) > MAX_FEED_BYTES:
            raise FeedError("Flux trop volumineux")
        return data


class TtlCache:
    """Petit cache en mémoire ; une valeur périmée reste utilisable si le réseau est en panne."""

    def __init__(self, ttl, max_items=200):
        self.ttl = ttl
        self.max_items = max_items
        self._items = {}

    def get(self, key, allow_stale=False):
        item = self._items.get(key)
        if item and (allow_stale or item[0] > time.time()):
            return item[1]
        return None

    def put(self, key, value):
        if len(self._items) >= self.max_items:
            self._items.pop(min(self._items, key=lambda k: self._items[k][0]))
        self._items[key] = (time.time() + self.ttl, value)


class FeedReader:
    """Flux lus, mis en cache une demi-heure."""

    def __init__(self, fetcher, cache=None):
        self.fetcher = fetcher
        self.cache = cache or TtlCache(1800)

    def read(self, url):
        cached = self.cache.get(url)
        if cached:
            return cached
        try:
            feed = parse_feed(self.fetcher.fetch(url))
        except FeedError:
            stale = self.cache.get(url, allow_stale=True)
            if stale:
                return stale
            raise
        self.cache.put(url, feed)
        return feed
