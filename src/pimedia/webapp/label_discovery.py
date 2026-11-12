"""Découverte des labels : diversité sans popularité, classements sourcés, pistes et bibliothèque prioritaire."""
import random
from collections import Counter
from dataclasses import replace

from ..shared.text import normalize
from .entities import ImportedTrack
from .label_entities import LabelAlbumTracks, LabelRanking, LabelScore, LabelTrack
from .music_metadata import MusicSourceError

SELECTION_SIZE = 15
RANK_BATCH = 5
TRACKS_PER_ALBUM = 2
MAX_EDITION_CHECKS = 10
SOURCES = ("discogs", "lastfm_listeners", "lastfm_plays")
MODES = ("discover", "top")


def varied_albums(albums, rng=random, size=SELECTION_SIZE):
    """À égalité, hasard ; privilégier les artistes et décennies les moins représentés. Aucun score de popularité."""
    pool = list(albums)
    rng.shuffle(pool)
    artists, periods, selected = Counter(), Counter(), []
    while pool and len(selected) < size:
        album = min(pool, key=lambda a: (artists[normalize(a.artist)], periods[a.year // 10]))
        pool.remove(album)
        selected.append(album)
        artists[normalize(album.artist)] += 1
        periods[album.year // 10] += 1
    return selected


def playable_tracks(tracks):
    """Ignorer les titres de face et les en-têtes, développer les pistes composées."""
    for track in tracks:
        if track.children:
            yield from playable_tracks(track.children)
        elif track.kind == "track" and track.title:
            yield track


def seconds(duration):
    try:
        parts = [int(p) for p in duration.split(":")]
        return sum(value * 60 ** i for i, value in enumerate(reversed(parts))) if len(parts) <= 3 else 0
    except ValueError:
        return 0


class LabelDiscovery:
    def __init__(self, catalogs, discogs, lastfm, imports, rng=random, youtube_versions=None):
        self.catalogs, self.discogs, self.lastfm = catalogs, discogs, lastfm
        self.imports, self.rng = imports, rng
        self.youtube_versions = youtube_versions

    def status(self):
        sources = SOURCES if self.lastfm.enabled else SOURCES[:1]
        return dict(enabled=self.discogs.enabled, sources=sources, selectionSize=SELECTION_SIZE,
                    tracksPerAlbum=TRACKS_PER_ALBUM)

    def discover(self, label):
        return varied_albums(self.catalogs.complete("label", label), self.rng)

    def ranking(self, label, source, offset):
        if source not in self.status()["sources"]:
            raise ValueError("ranking source")
        albums = self.catalogs.complete("label", label)
        if type(offset) is not int or not 0 <= offset <= len(albums):
            raise ValueError("offset")
        end = min(offset + RANK_BATCH, len(albums))
        scores = [self._score(label, album, source, cached=i < offset) for i, album in enumerate(albums[:end])]
        excluded = sum(s is None for s in scores)
        scores = sorted((s for s in scores if s is not None and s.value > 0), key=lambda s: (-s.value, -s.votes, s.album.id))
        return LabelRanking(scores[:SELECTION_SIZE], source, end, len(albums), excluded)

    def _score(self, label, album, source, cached=False):
        edition = self._edition(label, album, cached)
        if edition is None:
            return None
        album = self._verified_album(album, edition)
        if source == "discogs":
            return LabelScore(album, source, edition.rating if edition.votes else 0, edition.votes, edition=edition.id)
        popularity = self.lastfm.album(album.artist, album.title, cached=cached)
        if popularity is None:
            raise MusicSourceError("discovery.rank_restart")
        value = popularity.listeners if source == "lastfm_listeners" else popularity.plays
        return LabelScore(album, source, value, listeners=popularity.listeners, plays=popularity.plays)

    def tracks(self, user, label, album_id, mode):
        if mode not in MODES:
            raise ValueError("mode")
        album = next((a for a in self.catalogs.complete("label", label) if a.id == album_id), None)
        if album is None:
            raise ValueError("album")
        edition = self._edition(label, album)
        if edition is None:
            return LabelAlbumTracks(album, [], eligible=False)
        album = self._verified_album(album, edition)
        tracks = list(playable_tracks(edition.tracks))
        if mode == "discover":
            self.rng.shuffle(tracks)
        return LabelAlbumTracks(album, [self._match(user, album, track, edition) for track in tracks[:TRACKS_PER_ALBUM]])

    def versions(self, user, release, wanted):
        edition = self.discogs.release(release)
        tracks = [self._imported_track(t, edition) for t in playable_tracks(edition.tracks)]
        track = next((t for t in tracks if normalize(t.title) == normalize(wanted.title)
                      and normalize(t.artist) == normalize(wanted.artist)), None)
        if track is None:
            raise ValueError("track")
        return self.youtube_versions.find(user, track, edition.videos, labels=tuple(label.name for label in edition.labels))

    def _edition(self, label, album, cached=False):
        # Le catalogue Discogs inclut aussi les associations de sociétés (copyright, fabrication…).
        # Vérifier le vrai label et essayer les éditions suivantes avant d'écarter le disque.
        for candidate in album.editions[:MAX_EDITION_CHECKS]:
            edition = self.discogs.release(candidate.id, cached=cached)
            if edition is None:
                raise MusicSourceError("discovery.rank_restart")
            if str(label) in {l.id for l in edition.labels}:
                return edition
        return None

    @staticmethod
    def _verified_album(album, edition):
        first = next(e for e in album.editions if e.id == edition.id)
        editions = (first,) + tuple(e for e in album.editions if e.id != first.id)
        return replace(album, title=first.title, artist=first.artist, year=first.year, editions=editions,
                       format=first.format, image=first.image or album.image)

    @staticmethod
    def _imported_track(raw, edition):
        return ImportedTrack(raw.title, raw.artist or edition.artist, edition.title, seconds(raw.duration))

    def _match(self, user, album, raw, edition):
        track = self._imported_track(raw, edition)
        result = self.imports.match_all(user, [track])[0]
        return LabelTrack(track, album, result["choices"], result["status"], edition.id)
