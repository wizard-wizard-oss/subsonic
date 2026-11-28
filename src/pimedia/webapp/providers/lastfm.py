"""La seule classe Last.fm du site : popularité d'un album (découverte par label), pochettes proposées et artistes
proches (radar des sorties)."""
from dataclasses import asdict, dataclass
from typing import Optional
import urllib.parse

from ...shared.external import query_url
from ...shared.providers.metadata import PublicMetadata
from ...shared.providers.musicbrainz.parsing import mbid
from ...shared.text import normalize

LASTFM_BLANK = "2a96cbd8b46e442fc41c2b86b821562f"  # Visuel vide renvoyé par Last.fm.
SIZES = ("mega", "extralarge", "large", "medium")     # du plus grand au plus petit
MAX_CANDIDATES = 12
COVER_SIZES = ("extralarge", "large", "mega", "medium")   # une carte du radar fait 180 px : 300 px d'abord


@dataclass(frozen=True)
class AlbumPopularity:
    listeners: int = 0
    plays: int = 0


@dataclass(frozen=True)
class CoverCandidate:
    url: str
    thumb: str
    name: str
    artist: str

    def to_api(self):
        return asdict(self)


@dataclass(frozen=True)
class SimilarArtist:
    """Artiste proche selon Last.fm ; mbid vide quand Last.fm ne le connaît pas."""
    name: str
    mbid: Optional[str]
    match: float


def _text(value):
    return value.strip() if isinstance(value, str) else ""


class LastFm(PublicMetadata):
    prefix = "lastfm:"
    interval = 0.25
    base = "https://ws.audioscrobbler.com/2.0/"
    image_host = "lastfm.freetls.fastly.net"
    legacy_image_hosts = frozenset(("lastfm-img2.akamaized.net",))

    def __init__(self, store, api_key, http=None, **options):
        super().__init__(store, http, **options)
        self.api_key = api_key

    @property
    def enabled(self):
        return bool(self.api_key)

    @staticmethod
    def canonical_image_url(value):
        """L'ancien CDN HTTPS donne les mêmes fichiers Last.fm ; seul son hôte a changé."""
        try:
            parts = urllib.parse.urlsplit(value)
            if parts.hostname not in LastFm.legacy_image_hosts:
                return value
            if parts.scheme != "https" or parts.username or parts.password or parts.port is not None \
                    or parts.query or parts.fragment or not parts.path.startswith("/i/u/"):
                return ""
        except ValueError:
            return ""
        return urllib.parse.urlunsplit(("https", LastFm.image_host, parts.path, "", ""))

    def _call(self, name, params, project=lambda raw: raw):
        params = dict(params, format="json")
        key = query_url(name, sorted(params.items()))
        url = query_url(self.base, dict(params, api_key=self.api_key))
        return self.fetch(key, url, read=lambda address: project(self.http.get_json(address))).data

    def similar_artists(self, name, limit):
        """Proches d'un artiste, du plus proche au moins proche (gardés 7 jours) ; () sans clé Last.fm."""
        if not self.enabled:
            return ()
        params = {"method": "artist.getsimilar", "artist": name, "limit": limit, "autocorrect": 1}
        return tuple(SimilarArtist(**found) for found in self._call("similar", params, self._similar)["artists"])

    @staticmethod
    def _similar(raw):
        if raw.get("error"):
            if str(raw["error"]) == "6":
                return {"artists": []}
            raise ValueError("Last.fm")
        found = (raw.get("similarartists") or {}).get("artist") or []
        found = [found] if isinstance(found, dict) else found
        return {"artists": [{"name": _text(a.get("name")), "mbid": _valid_mbid(a.get("mbid")),
                             "match": float(a.get("match") or 0)}
                            for a in found if isinstance(a, dict) and _text(a.get("name"))]}

    def album(self, artist, title, cached=False):
        params = dict(method="album.getInfo", artist=artist, album=title, autocorrect=0, format="json")
        key = query_url("album", sorted(params.items()))
        if cached:
            data = self.cached(key)
        else:
            data = self.fetch(key, query_url(self.base, dict(params, api_key=self.api_key)), read=lambda address:
                              asdict(self._popularity(self.http.get_json(address), artist, title))).data
        return AlbumPopularity(**data) if data is not None else None

    @staticmethod
    def _popularity(raw, artist, title):
        if raw.get("error"):
            if str(raw["error"]) == "6":
                return AlbumPopularity()
            raise ValueError("Last.fm")
        album = raw.get("album") or {}
        if normalize(album.get("name")) != normalize(title) or normalize(album.get("artist")) != normalize(artist):
            return AlbumPopularity()
        return AlbumPopularity(int(album.get("listeners") or 0), int(album.get("playcount") or 0))

    def album_cover(self, artist, title):
        """Pochette de cet album précis (artiste et titre égaux après normalisation), 300 px de préférence ; "" sinon.
        Sert au radar des sorties quand Cover Art Archive n'a encore rien."""
        if not self.enabled:
            return ""
        raw = self._call("cover", {"method": "album.getinfo", "artist": artist, "album": title, "autocorrect": 0})
        album = raw.get("album") or {}
        if normalize(_text(album.get("name"))) != normalize(title) or \
                normalize(_text(album.get("artist"))) != normalize(artist):
            return ""
        images = {i.get("size"): _text(i.get("#text")) for i in album.get("image") or [] if isinstance(i, dict)}
        found = [images[size] for size in COVER_SIZES if images.get(size) and LASTFM_BLANK not in images[size]]
        return found[0] if found else ""

    def album_images(self, artist, album):
        """Pochettes : l'album exact d'abord (album.getinfo), puis les albums de ce nom, ceux du même artiste en tête."""
        exact = self._call("images-info", {"method": "album.getinfo", "artist": artist, "album": album})
        found = self._call("images-search", {"method": "album.search", "album": album, "limit": 30})
        matches = ((found.get("results") or {}).get("albummatches") or {}).get("album") or []
        matches = [matches] if isinstance(matches, dict) else list(matches)
        matches.sort(key=lambda m: normalize(_text(m.get("artist"))) != normalize(artist))     # tri stable
        candidates, seen = [], set()
        for match in [exact.get("album") or {}] + matches:
            candidate = self._candidate(match)
            if candidate and candidate.url not in seen:
                seen.add(candidate.url)
                candidates.append(candidate)
        return candidates[:MAX_CANDIDATES]

    @staticmethod
    def _candidate(match):
        if not isinstance(match, dict):
            return None
        images = {i.get("size"): _text(i.get("#text")) for i in match.get("image") or [] if isinstance(i, dict)}
        urls = [images[size] for size in SIZES if images.get(size) and LASTFM_BLANK not in images[size]]
        if not urls:
            return None
        return CoverCandidate(urls[0], urls[min(1, len(urls) - 1)], _text(match.get("name")), _text(match.get("artist")))


def _valid_mbid(value):
    try:
        return mbid(value)
    except ValueError:
        return None
