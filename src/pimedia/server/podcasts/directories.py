"""Annuaires de podcasts : iTunes (sans clé) et Podcast Index (clé gratuite, facultative)."""
import hashlib
import json
import time
import urllib.parse
import urllib.request

from .feeds import TtlCache, USER_AGENT

ITUNES_SEARCH = "https://itunes.apple.com/search"
INDEX_API = "https://api.podcastindex.org/api/1.0/"
MAX_AGE_DAYS = 400              # un podcast sans nouvel épisode depuis plus longtemps est considéré abandonné
MIN_EPISODES = 3


class DirectoryError(Exception):
    pass


# ---------- fonctions pures ----------
def podcast_card(feed, title, author="", image="", desc="", genre="", count=None, lang=""):
    """Forme commune d'un podcast, quel que soit l'annuaire."""
    return {"feed": feed, "title": (title or "").strip(), "author": (author or "").strip(), "image": image or "",
            "desc": (desc or "").strip()[:300], "genre": genre or "", "count": count,
            "lang": (lang or "").strip().lower()}


def index_auth_headers(key, secret, now=None):
    """En-têtes d'authentification de Podcast Index : sha1(clé + secret + date)."""
    stamp = str(int(now if now is not None else time.time()))
    digest = hashlib.sha1((key + secret + stamp).encode("utf-8")).hexdigest()
    return {"User-Agent": USER_AGENT, "X-Auth-Date": stamp, "X-Auth-Key": key, "Authorization": digest}


def is_active(feed, now=None):
    """Écarte les flux manifestement abandonnés ou vides (quand l'annuaire donne l'information)."""
    now = now if now is not None else time.time()
    newest = feed.get("newestItemPublishTime") or feed.get("lastUpdateTime")
    if newest and now - newest > MAX_AGE_DAYS * 86400:
        return False
    count = feed.get("episodeCount")
    return not (count is not None and count < MIN_EPISODES)


def from_itunes(result):
    return podcast_card(result.get("feedUrl", ""), result.get("collectionName"), result.get("artistName"),
                        result.get("artworkUrl600") or result.get("artworkUrl100"), "",
                        result.get("primaryGenreName"), result.get("trackCount"))


def from_index(feed):
    categories = feed.get("categories") or {}
    return podcast_card(feed.get("url", ""), feed.get("title"), feed.get("author"),
                        feed.get("artwork") or feed.get("image"), feed.get("description"),
                        ", ".join(list(categories.values())[:2]), feed.get("episodeCount"), feed.get("language"))


def merge_cards(*groups):
    """Concatène plusieurs listes en ôtant les doublons (même flux ou même titre) et les cartes inutilisables."""
    seen, merged = set(), []
    for group in groups:
        for card in group:
            key = card["feed"] or card["title"].lower()
            if card["feed"] and card["title"] and key not in seen and card["title"].lower() not in seen:
                seen.add(key)
                seen.add(card["title"].lower())
                merged.append(card)
    return merged


# ---------- accès réseau ----------
class JsonHttp:
    def get(self, url, headers=None, timeout=12):
        request = urllib.request.Request(url, headers=dict({"User-Agent": USER_AGENT}, **(headers or {})))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except (OSError, ValueError) as error:
            raise DirectoryError(str(getattr(error, "reason", error)))


class ItunesDirectory:
    """Annuaire d'Apple : aucune clé, bonne recherche par mot."""

    def __init__(self, http, country="fr"):
        self.http = http
        self.country = country

    def search(self, term, limit=30):
        query = urllib.parse.urlencode([("media", "podcast"), ("entity", "podcast"), ("country", self.country),
                                        ("limit", limit), ("term", term)])
        data = self.http.get(ITUNES_SEARCH + "?" + query)
        return [from_itunes(r) for r in data.get("results", []) if r.get("feedUrl")]


class PodcastIndexDirectory:
    """Podcast Index : annuaire ouvert avec catégories et tendances. Inactif tant qu'aucune clé n'est donnée."""

    def __init__(self, http, config):
        self.http = http
        self.config = config

    @property
    def enabled(self):
        return bool(self.config.get("podcastindex_key") and self.config.get("podcastindex_secret"))

    def _call(self, path, params):
        headers = index_auth_headers(self.config.get("podcastindex_key"), self.config.get("podcastindex_secret"))
        data = self.http.get(INDEX_API + path + "?" + urllib.parse.urlencode(params), headers)
        return [f for f in data.get("feeds", []) if is_active(f)]

    def trending(self, category, language="fr", limit=40):
        feeds = self._call("podcasts/trending", [("max", limit), ("lang", language), ("cat", category)])
        return [from_index(f) for f in feeds]

    def search(self, term, limit=30):
        return [from_index(f) for f in self._call("search/byterm", [("q", term), ("max", limit)])]


class DirectoryHub:
    """Interroge les annuaires disponibles et présente un résultat propre. Une panne d'un annuaire
    n'empêche pas d'utiliser l'autre."""

    def __init__(self, itunes, index, cache=None):
        self.itunes = itunes
        self.index = index
        self.cache = cache or TtlCache(3600)

    @property
    def sources(self):
        return {"itunes": True, "podcastindex": self.index.enabled}

    def search(self, term):
        return self._cached("s:" + term, lambda: self._gather(
            lambda: self.index.search(term), lambda: self.itunes.search(term)))

    def theme(self, theme):
        return self._cached("t:" + theme.key, lambda: self._gather(
            lambda: self.index.trending(theme.index_category), lambda: self.itunes.search(theme.search_terms)))

    def _gather(self, from_index, from_itunes):
        """Podcast Index d'abord (s'il est actif), puis iTunes ; la liste vide n'est pas une erreur."""
        groups, failures = [], 0
        for enabled, fetch in ((self.index.enabled, from_index), (True, from_itunes)):
            if not enabled:
                continue
            try:
                groups.append(fetch())
            except DirectoryError:
                failures += 1
        if failures and not groups:
            raise DirectoryError("Annuaires injoignables")
        return merge_cards(*groups)

    def _cached(self, key, build):
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        try:
            result = build()
        except DirectoryError:
            stale = self.cache.get(key, allow_stale=True)
            if stale is not None:
                return stale
            raise
        self.cache.put(key, result)
        return result
