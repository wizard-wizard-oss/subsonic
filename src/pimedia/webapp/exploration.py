"""Labels et collaborations MusicBrainz. Aucun enrichissement ne modifie la bibliothèque.

Les éditions sont proposées par titre ET artiste exacts ; plusieurs éditions restent un choix explicite.
Les métadonnées publiques sont partagées, les recherches Subsonic sont toujours faites au nom du lecteur.
"""
import re
import logging
import threading
import time
import urllib.error
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from uuid import UUID

from ..shared.external import JsonFetcher, query_url
from ..shared.text import normalize
from .exploration_entities import (AlbumCredits, ArtistConnections, ArtistMatches, CachedMetadata, MusicArtist, MusicEdition,
                                   MusicLink, MusicProfile, MusicWork)

BASE = "https://musicbrainz.org/ws/2/"
PAGE_SIZE = 25
TTL = 7 * 86400
STALE_TTL = 30 * 86400
RETRY_DELAY = 2
TRANSIENT_ERRORS = {429, 500, 502, 503, 504}
LOG = logging.getLogger(__name__)
ROLES = {"producer": "producer", "executive producer": "producer", "co-producer": "producer",
         "instrument": "musician", "vocal": "vocals", "performer": "musician", "guest performer": "musician",
         "composer": "composer", "writer": "composer", "lyricist": "lyricist", "conductor": "conductor",
         "mix": "mix", "recording": "engineer", "engineer": "engineer", "mastering": "mastering"}


class ExplorationUnavailable(Exception):
    pass


@dataclass(frozen=True)
class MetadataResult:
    data: dict
    stale: bool = False


def mbid(value):
    try:
        parsed = str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("MusicBrainz ID") from None
    if str(value).lower() != parsed:
        raise ValueError("MusicBrainz ID")
    return parsed


def artist_name(raw):
    return "".join((c.get("name") or c.get("artist", {}).get("name", "")) + c.get("joinphrase", "")
                   for c in raw.get("artist-credit", [])
                   if isinstance(c, dict))


def artist_names(raw):
    """Noms canoniques et crédit complet, qui peut employer des noms d'usage."""
    credits = raw.get("artist-credit") or []
    names = [c.get("artist", {}).get("name", c.get("name", "")) for c in credits if isinstance(c, dict)]
    credit = artist_name(raw) if credits else ""
    return [*names, credit] if credit else names


def search_phrase(text):
    """Expression littérale MusicBrainz, sans guillemet ni échappement fourni par le nom."""
    return '"' + re.sub(r'["\\]', " ", str(text))[:300] + '"'


class MusicBrainzMetadata:
    """Réponses de MusicBrainz : cache durable, reprises bornées et déduplication des appels concurrents."""
    def __init__(self, repository, fetcher=None, clock=time.time, sleep=time.sleep):
        self.repository = repository
        self.fetcher = fetcher or JsonFetcher()
        self.clock = clock
        self.sleep = sleep
        self.lock = threading.Lock()
        self.retry_at = {}

    def _retry_delay(self, error):
        if not isinstance(error, urllib.error.HTTPError):
            return RETRY_DELAY
        if error.code not in TRANSIENT_ERRORS:
            return None
        value = (error.headers or {}).get("Retry-After", "")
        if value:
            try:
                return max(0, float(value))
            except ValueError:
                try:
                    return max(0, parsedate_to_datetime(value).timestamp() - self.clock())
                except (TypeError, ValueError, OverflowError):
                    pass
        return 60 if error.code == 429 else RETRY_DELAY

    def _fetch(self, url):
        for attempt in range(2):
            try:
                data = self.fetcher.get(url)
                if not isinstance(data, dict):
                    raise ValueError("MusicBrainz response")
                return data
            except (OSError, ValueError) as error:
                delay = self._retry_delay(error)
                # Une seule reprise, bornée ; une consigne d'attente plus longue revient au prochain clic.
                if attempt or delay is None or delay > RETRY_DELAY:
                    raise
                self.sleep(max(RETRY_DELAY, delay))

    def _fallback(self, cached):
        if cached and self.clock() - cached.fetched_at < STALE_TTL:
            return MetadataResult(cached.data, stale=True)
        raise ExplorationUnavailable()

    def get(self, path, **params):
        url = query_url(BASE + path, sorted(dict(params, fmt="json").items()))
        cached = self.repository.get(url)
        if cached and self.clock() - cached.fetched_at < TTL:
            return MetadataResult(cached.data)
        with self.lock:
            # Une autre requête a pu remplir le cache pendant l'attente. Les lectures déjà en cache ne patientent pas.
            cached = self.repository.get(url)
            if cached and self.clock() - cached.fetched_at < TTL:
                return MetadataResult(cached.data)
            if self.clock() < self.retry_at.get(url, 0):
                return self._fallback(cached)
            try:
                data = self._fetch(url)
            except (OSError, ValueError) as error:
                LOG.warning("MusicBrainz %s : %s", path.split("/")[0],
                            "HTTP %d" % error.code if isinstance(error, urllib.error.HTTPError) else type(error).__name__)
                delay = self._retry_delay(error)
                if delay is None:
                    raise ExplorationUnavailable() from error
                self.retry_at = {key: date for key, date in self.retry_at.items() if date > self.clock()}
                self.retry_at[url] = self.clock() + max(60, delay)
                return self._fallback(cached)
            self.repository.save(CachedMetadata(url, data, int(self.clock())))
            self.retry_at.pop(url, None)
            return MetadataResult(data)


class Exploration:
    def __init__(self, metadata, folders, library):
        self.metadata, self.folders, self.library = metadata, folders, library

    def artists(self, name):
        """Identités exactes, sans choisir un homonyme à la place de la personne."""
        name = str(name or "").strip()
        if not name or len(name) > 300:
            raise ValueError("artist")
        name_key = normalize(name)
        response = self.metadata.get("artist", query="artist:" + search_phrase(name), limit=25)
        artists = [MusicArtist(mbid(a["id"]), a["name"], a.get("type") or "", a.get("country") or "",
                               a.get("disambiguation") or "") for a in response.data.get("artists", [])
                   if normalize(a.get("name", "")) == name_key]
        return ArtistMatches(artists, response.stale)

    @staticmethod
    def _connections(raw):
        """Relations musicales explicites uniquement ; conserver les périodes, dédupliquer les doublons exacts."""
        roles = {"member of band": ("group", "member"), "collaboration": ("project", "collaborator"),
                 "subgroup": ("parent_group", "subgroup"),
                 "instrumental supporting musician": ("supporting_for", "supporting_member"),
                 "vocal supporting musician": ("supporting_for", "supporting_member")}
        found = {}
        for relation in raw.get("relations", []):
            artist = relation.get("artist") or {}
            if not artist.get("id") or relation.get("type") not in roles:
                continue
            forward, backward = roles[relation["type"]]
            role = backward if relation.get("direction") == "backward" else forward
            link = MusicLink(mbid(artist["id"]), artist["name"], "artist", role,
                             ", ".join(sorted(relation.get("attributes") or [])),
                             relation.get("begin") or "", relation.get("end") or "", bool(relation.get("ended")))
            found[(link.id, link.role, link.detail, link.begin, link.end, link.ended)] = link
        return sorted(found.values(), key=lambda link: (link.name.casefold(), link.role, link.begin, link.end))

    def connections(self, identity):
        """Un seul appel léger, sans catalogue : chargé à la demande pour chaque musicien."""
        identity = mbid(identity)
        response = self.metadata.get("artist/" + identity, inc="artist-rels")
        return ArtistConnections(identity, response.data.get("name", ""), self._connections(response.data), response.stale)

    def album(self, user, album_id, release=""):
        # Les noms viennent de l'album accessible par ce compte, pas d'un nom fourni par le navigateur.
        album = self.folders.album(user, album_id)
        title, artist = album["name"], album["artist"]
        response = self.metadata.get("release", query='release:%s AND artist:%s' % (search_phrase(title), search_phrase(artist)),
                                     limit=100)
        data = response.data
        title_key, artist_key = normalize(title), normalize(artist)
        candidates = [r for r in data.get("releases", []) if normalize(r.get("title", "")) == title_key
                      and artist_key in {normalize(a) for a in artist_names(r)}]
        editions = [MusicEdition(mbid(r["id"]), r["title"], artist_name(r), r.get("date", ""),
                                r.get("country", ""), ", ".join(m.get("format", "") for m in r.get("media", [])),
                                tuple(i.get("label", {}).get("name", "") for i in r.get("label-info", [])
                                      if i.get("label"))) for r in candidates]
        result = AlbumCredits(editions=editions, stale=response.stale)
        if not release:
            return result
        release = mbid(release)
        if release not in {e.id for e in editions}:
            raise ValueError("edition")
        details = self.metadata.get("release/" + release,
                                    inc="labels+artist-credits+recordings+artist-rels+recording-level-rels")
        raw = details.data
        result.stale = result.stale or details.stale
        result.selected = release
        result.labels = list({i["label"]["id"]: MusicLink(mbid(i["label"]["id"]), i["label"]["name"], "label",
                                                        "label", i.get("catalog-number", ""))
                              for i in raw.get("label-info", []) if i.get("label", {}).get("id")}.values())
        people = {}
        for credit in raw.get("artist-credit", []):
            if isinstance(credit, dict) and credit.get("artist", {}).get("id"):
                a = credit["artist"]
                people[(a["id"], "artist", "")] = MusicLink(mbid(a["id"]), a["name"])
        self._credits(raw, people)
        for medium in raw.get("media", []):
            for track in medium.get("tracks", []):
                self._credits(track.get("recording") or {}, people)
        result.people = sorted(people.values(), key=lambda p: (p.role, p.name.casefold(), p.detail))
        return result

    @staticmethod
    def _credits(raw, people):
        for relation in raw.get("relations", []):
            artist = relation.get("artist") or {}
            role = ROLES.get(relation.get("type"))
            if artist.get("id") and role:
                detail = ", ".join(relation.get("attributes") or [])
                key = (artist["id"], role, detail)
                people[key] = MusicLink(mbid(artist["id"]), artist["name"], "artist", role, detail)

    def profile(self, kind, identity, offset=0):
        if kind not in ("artist", "label") or not 0 <= offset <= 25000:
            raise ValueError("profile")
        identity = mbid(identity)
        identity_response = self.metadata.get(kind + "/" + identity, **({"inc": "artist-rels+release-rels+recording-rels"}
                                                                        if kind == "artist" else {}))
        raw = identity_response.data
        relations, works = self._connections(raw), {}
        for relation in raw.get("relations", []):
            for target in ("recording", "release"):
                item = relation.get(target) or {}
                if item.get("id") and relation.get("type") in ROLES:
                    key = (item["id"], ROLES[relation["type"]])
                    works[key] = MusicWork(mbid(item["id"]), item["title"], artist_name(item), target,
                                           item.get("date", ""), key[1])
        endpoint = "release" if kind == "label" else "release-group"
        catalog_response = self.metadata.get(endpoint, **{kind: identity, "inc": "artist-credits", "limit": PAGE_SIZE,
                                                         "offset": offset})
        data = catalog_response.data
        catalog = [MusicWork(mbid(r["id"]), r["title"], artist_name(r), endpoint,
                             r.get("first-release-date", r.get("date", ""))) for r in data.get(endpoint + "s", [])]
        # Les crédits sont séparés du catalogue principal : produire un disque n'en fait pas son artiste principal.
        all_works = catalog + (sorted(works.values(), key=lambda w: (w.date, w.title, w.role)) if offset == 0 else [])
        # MusicBrainz peut renvoyer moins que la limite (plafond du nombre de pistes par réponse).
        next_offset = offset + len(catalog)
        return MusicProfile(identity, raw.get("name", ""), kind, raw.get("disambiguation", ""), relations,
                            all_works, bool(catalog) and data.get(endpoint + "-count", 0) > next_offset,
                            offset, next_offset, stale=identity_response.stale or catalog_response.stale)

    def local(self, user, title, artist=""):
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 300 or len(artist) > 300:
            raise ValueError("search")
        # Recherche limitée aux résultats autorisés pour cette personne. Pas de cache public de disponibilité.
        found = self.library.search(user, title)
        title_key, artist_key = normalize(title), normalize(artist)
        return {"albums": [a for a in found["albums"] if normalize(a["name"]) == title_key
                           and (not artist or normalize(a["artist"]) == artist_key)],
                "songs": [s for s in found["songs"] if normalize(s["title"]) == title_key
                          and (not artist or normalize(s["artist"]) == artist_key)]}
