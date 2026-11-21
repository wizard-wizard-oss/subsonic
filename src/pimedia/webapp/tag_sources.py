"""Outil de métadonnées : une source choisie, des résultats typés, aucune écriture musicale."""
import re
from dataclasses import asdict, dataclass
from typing import Optional

from .discogs import discogs_id, image_url
from .musicbrainz import ExplorationUnavailable, mbid
from .music_metadata import MusicSourceError

SOURCES = ("musicbrainz", "discogs")
MAX_SEARCH_LENGTH = 300


@dataclass(frozen=True)
class SourceCandidate:
    id: str
    title: str
    artist: str
    date: str
    country: str
    format: str
    track_count: int
    url: str
    cover_url: str = ""
    genres: tuple = ()
    styles: tuple = ()

    def to_api(self):
        return dict(id=self.id, title=self.title, artist=self.artist, date=self.date, country=self.country,
                    format=self.format, trackCount=self.track_count, url=self.url, coverUrl=self.cover_url,
                    genres=list(self.genres), styles=list(self.styles))


@dataclass(frozen=True)
class SourceMatches:
    source: str
    candidates: tuple

    def to_api(self):
        return dict(source=self.source, candidates=[item.to_api() for item in self.candidates])


@dataclass(frozen=True)
class SourceTrack:
    position: str
    track: Optional[int]
    disc: Optional[int]
    title: str
    artist: str
    duration: Optional[int]

    def to_api(self):
        return asdict(self)


@dataclass(frozen=True)
class SourceRelease:
    source: str
    id: str
    title: str
    artist: str
    date: str
    year: str
    country: str
    format: str
    genre: str
    genres: tuple
    styles: tuple
    tracks: tuple

    def to_api(self):
        return dict(source=self.source, id=self.id, title=self.title, artist=self.artist, date=self.date,
                    year=self.year, country=self.country, format=self.format, genre=self.genre,
                    genres=list(self.genres), styles=list(self.styles), tracks=[track.to_api() for track in self.tracks])


class TagSources:
    def __init__(self, musicbrainz, discogs):
        self.musicbrainz, self.discogs = musicbrainz, discogs

    def status(self):
        return {source: bool(getattr(getattr(self, source), "enabled", False)) for source in SOURCES}

    def _source(self, source):
        if not isinstance(source, str) or source.strip().lower() not in SOURCES:
            raise ValueError("tags.bad_source")
        source = source.strip().lower()
        provider = getattr(self, source)
        if not self.status()[source]:
            raise ValueError("tags.source_disabled")
        return source, provider

    @staticmethod
    def _term(value):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= MAX_SEARCH_LENGTH or \
                any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("tags.bad_search")
        return value.strip()

    def search(self, source, artist, album):
        source, provider = self._source(source)
        artist, album = self._term(artist), self._term(album)
        try:
            found = provider.search_releases(artist, album)
            candidates = tuple(SourceCandidate(item.id, item.title, item.artist, item.date, item.country,
                                                item.format, item.track_count, _url(source, item.id),
                                                cover_url=image_url(item.image) if source == "discogs" else "",
                                                genres=tuple(item.genres) if source == "discogs" else (),
                                                styles=tuple(item.styles) if source == "discogs" else ()) for item in found)
        except (ExplorationUnavailable, MusicSourceError, OSError, ValueError, TypeError, KeyError, AttributeError):
            raise ValueError("tags.source_unavailable") from None
        return SourceMatches(source, candidates)

    def release(self, source, release_id):
        source, provider = self._source(source)
        try:
            identity = mbid(release_id) if source == "musicbrainz" else discogs_id(release_id)
        except (ValueError, TypeError):
            raise ValueError("tags.bad_release") from None
        try:
            release = provider.release(identity)
            genres = tuple(release.genres)
            styles = tuple(release.styles) if source == "discogs" else ()
            tracks = tuple(_discogs_tracks(release.tracks, release.artist)) if source == "discogs" else \
                tuple(SourceTrack(track.position, track.track, track.disc, track.title, track.artist, track.duration)
                      for track in release.tracks)
            year = re.match(r"[0-9]{4}", release.date)
            return SourceRelease(source, release.id, release.title, release.artist, release.date,
                                 year[0] if year else "", release.country, release.format,
                                 (styles or genres or ("",))[0], genres, styles, tracks)
        except (ExplorationUnavailable, MusicSourceError, OSError, ValueError, TypeError, KeyError, AttributeError):
            raise ValueError("tags.source_unavailable") from None


def _url(source, identity):
    return "https://musicbrainz.org/release/" + identity if source == "musicbrainz" else \
        "https://www.discogs.com/release/" + identity


def _discogs_tracks(tracks, album_artist):
    """Développer les suites, conserver les positions et les artistes hérités sans numéro inventé pour le vinyle."""
    for item in tracks:
        artist = item.artist or album_artist
        if item.children:
            yield from _discogs_tracks(item.children, artist)
        elif item.kind == "track" and item.title:
            yield SourceTrack(item.position, item.track, item.disc, item.title, artist, item.duration_seconds)
