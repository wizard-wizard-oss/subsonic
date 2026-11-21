"""Éditions MusicBrainz, indépendantes de la bibliothèque et de ses fichiers."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MusicBrainzEdition:
    id: str
    title: str
    artist: str
    date: str = ""
    country: str = ""
    format: str = ""
    track_count: int = 0


@dataclass(frozen=True)
class MusicBrainzTrack:
    position: str
    track: Optional[int]
    disc: Optional[int]
    title: str
    artist: str
    duration: Optional[int] = None


@dataclass(frozen=True)
class MusicBrainzRelease:
    id: str
    title: str
    artist: str
    date: str
    country: str
    format: str
    genres: tuple
    tracks: tuple
