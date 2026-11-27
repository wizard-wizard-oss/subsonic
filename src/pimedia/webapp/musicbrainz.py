"""Client MusicBrainz : transport existant, cache et éditions publiques typées."""
import logging
import re
import threading
import time
import urllib.error
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime
from uuid import UUID

from ..shared.external import JsonFetcher, query_url
from .exploration_entities import CachedMetadata
from .musicbrainz_entities import MusicBrainzEdition, MusicBrainzRelease, MusicBrainzTrack
from .weekly_release_entities import ReleaseGenre, WeeklyRelease, WeeklyReleasePage

BASE = "https://musicbrainz.org/ws/2/"
TTL = 7 * 86400
GENRE_CATALOG_TTL = 86400
STALE_TTL = 30 * 86400
RETRY_DELAY = 2
TRANSIENT_ERRORS = {429, 500, 502, 503, 504}
SEARCH_LIMIT = 25
LOG = logging.getLogger(__name__)


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
                   for c in raw.get("artist-credit") or []
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

    def _fetch(self, url, read):
        for attempt in range(2):
            try:
                data = read(url)
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

    def get(self, path, *, cache_seconds=TTL, fmt="json", read=None, **params):
        url = query_url(BASE + path, sorted(dict(params, fmt=fmt).items()))
        cached = self.repository.get(url)
        if cached and self.clock() - cached.fetched_at < cache_seconds:
            return MetadataResult(cached.data)
        with self.lock:
            # Une autre requête a pu remplir le cache pendant l'attente. Les lectures déjà en cache ne patientent pas.
            cached = self.repository.get(url)
            if cached and self.clock() - cached.fetched_at < cache_seconds:
                return MetadataResult(cached.data)
            if self.clock() < self.retry_at.get(url, 0):
                return self._fallback(cached)
            try:
                data = self._fetch(url, read or self.fetcher.get)
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


    @property
    def enabled(self):
        return True

    def release_genres(self) -> tuple[ReleaseGenre, ...]:
        result = self.get("genre/all", cache_seconds=GENRE_CATALOG_TTL, fmt="txt", read=self._read_genre_catalog)
        return tuple(ReleaseGenre(name) for name in result.data["names"])

    def _read_genre_catalog(self, url):
        names = dict.fromkeys(name.strip() for name in self.fetcher.get_text(url).splitlines())
        names.pop("", None)
        if not names:
            raise ValueError("Empty MusicBrainz genre catalog")
        return {"names": list(names)}

    def weekly_groups(self, genre, monday, sunday, limit, offset) -> WeeklyReleasePage:
        query = (f'tag:{search_phrase(genre)} AND (primarytype:album OR primarytype:ep) '
                 f'AND firstreleasedate:[{monday} TO {sunday}]')
        response = self.get("release-group", cache_seconds=3600, query=query, limit=limit, offset=offset)
        rows = response.data["release-groups"]
        albums = []
        for row in rows:
            value = row.get("first-release-date")
            if not isinstance(value, str) or len(value) != 10:
                continue
            try:
                released_on = date.fromisoformat(value)
            except ValueError:
                continue
            albums.append(WeeklyRelease(mbid(row["id"]), row["title"], artist_name(row),
                                        released_on, row.get("primary-type", "")))
        end = offset + len(rows)
        next_offset = end if rows and end < response.data["count"] else None
        return WeeklyReleasePage(tuple(albums), next_offset, response.stale)

    def search_releases(self, artist, album):
        """Candidats classés par MusicBrainz, sans imposer une égalité des tags à réparer."""
        query = "release:(%s) AND artist:(%s)" % (_search_terms(album), _search_terms(artist))
        response = self.get("release", query=query, limit=SEARCH_LIMIT)
        return tuple(self._edition(raw) for raw in response.data.get("releases", [])
                     if raw.get("id") and raw.get("title"))

    @staticmethod
    def _edition(raw):
        media = raw.get("media") or []
        count = _number(raw.get("track-count")) or sum(_number(m.get("track-count")) or 0 for m in media)
        return MusicBrainzEdition(mbid(raw["id"]), str(raw["title"])[:1000], artist_name(raw)[:1000],
                                  str(raw.get("date") or "")[:20], str(raw.get("country") or "")[:100],
                                  _formats(media), count)

    def release(self, identity):
        identity = mbid(identity)
        raw = self.get("release/" + identity, inc="artist-credits+recordings+release-groups+genres").data
        if mbid(raw.get("id")) != identity:
            raise ValueError("MusicBrainz release")
        artist = artist_name(raw)[:1000]
        media = raw.get("media") or []
        tracks = []
        for medium_index, medium in enumerate(media, 1):
            disc = _number(medium.get("position")) or medium_index
            for item in medium.get("tracks") or []:
                recording = item.get("recording") or {}
                length = item.get("length")
                if length is None:
                    length = recording.get("length")
                length = _number(length, zero=True)
                tracks.append(MusicBrainzTrack(str(item.get("number") or item.get("position") or "")[:30],
                    _number(item.get("position")), disc, str(item.get("title") or recording.get("title") or "")[:1000],
                    (artist_name(item) or artist_name(recording) or artist)[:1000],
                    round(length / 1000) if length is not None else None))
        genres = self._release_genres(raw)
        return MusicBrainzRelease(identity, str(raw.get("title") or "")[:1000], artist,
                                  str(raw.get("date") or "")[:20], str(raw.get("country") or "")[:100],
                                  _formats(media), genres, tuple(tracks))

    def _release_genres(self, raw):
        genres = _genres(raw)
        if genres:
            return genres
        group = raw.get("release-group") or {}
        if not isinstance(group, dict):
            return ()
        genres = _genres(group)
        if genres:
            return genres
        try:
            identity = mbid(group.get("id"))
            details = self.get("release-group/" + identity, inc="genres").data
            if mbid(details.get("id")) == identity:
                return _genres(details)
        except (ExplorationUnavailable, OSError, ValueError, TypeError, AttributeError):
            # Le genre complète l'édition : une panne de cet enrichissement ne doit pas retirer ses pistes.
            pass
        return ()


def _genres(raw):
    ranked = []
    for genre in raw.get("genres") or []:
        if not isinstance(genre, dict) or not isinstance(genre.get("name"), str) or not genre["name"].strip():
            continue
        try:
            count = int(genre.get("count") or 0)
        except (TypeError, ValueError, OverflowError):
            continue
        if count >= 0:
            ranked.append((count, genre["name"].strip()[:100]))
    ranked.sort(key=lambda item: -item[0])
    return tuple(dict.fromkeys(name for _, name in ranked))


def _number(value, zero=False):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
        return number if number >= (0 if zero else 1) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _formats(media):
    return ", ".join(dict.fromkeys(str(m["format"]) for m in media if m.get("format")))[:300]


def _search_terms(value):
    # Les mots seuls évitent les opérateurs Lucene fournis par l'entrée ; une faute reste une suggestion possible.
    words = re.findall(r"[^\W_]+", str(value), re.UNICODE)
    return " ".join(word + "~1" if len(word) > 3 else '"' + word + '"' for word in words) or search_phrase(value)
