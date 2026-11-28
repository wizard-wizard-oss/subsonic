"""Projections de l’accueil ; seules les références des écoutes sont persistées."""
from dataclasses import asdict, dataclass
from typing import Optional

PAGE_SIZE = 12
SEED_ATTEMPTS = 6
SUGGESTION_PAGES = 2


@dataclass(frozen=True)
class ListeningPolicy:
    minimum_duration: int = 30
    maximum_seconds: int = 240
    fraction: float = 0.5

    def to_api(self):
        return asdict(self)


@dataclass(frozen=True)
class Album:
    id: str
    name: str
    artist: str
    artist_id: str = ""
    cover_id: str = ""
    genre: str = ""
    year: Optional[int] = None

    @classmethod
    def of(cls, data):
        return cls(str(data["id"]), data["name"], data.get("artist", ""), str(data.get("artistId") or ""),
                   data.get("coverId") or "", data.get("genre") or "", data.get("year"))

    def to_api(self):
        return dict(id=self.id, name=self.name, artist=self.artist, artistId=self.artist_id,
                    coverId=self.cover_id, genre=self.genre, year=self.year)


@dataclass(frozen=True)
class Seed:
    id: str
    title: str
    artist_id: str
    artist: str
    album_id: str
    album: str
    genre: str
    cover_id: str

    @classmethod
    def of(cls, data):
        return cls(str(data["id"]), data.get("title") or "", str(data.get("artistId") or ""),
                   data.get("artist") or "", str(data.get("albumId") or ""), data.get("album") or "",
                   data.get("genre") or "", data.get("coverId") or "")

    def to_api(self):
        return dict(id=self.id, title=self.title, artistId=self.artist_id, artist=self.artist,
                    albumId=self.album_id, album=self.album, genre=self.genre, coverId=self.cover_id)


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    song_id: str
    played_at: int

    def to_api(self):
        return dict(id=self.id, songId=self.song_id, playedAt=self.played_at)


@dataclass(frozen=True)
class HistoryPage:
    entries: tuple
    next_before: Optional[int] = None

    def to_api(self):
        return dict(entries=[entry.to_api() for entry in self.entries], nextBefore=self.next_before)


@dataclass(frozen=True)
class PersonalPage:
    basis: str
    seed: Optional[Seed]
    recent: tuple
    suggestions: tuple
    next_before: Optional[int] = None

    def to_api(self):
        return dict(basis=self.basis, seed=self.seed.to_api() if self.seed else None,
                    recent=[album.to_api() for album in self.recent],
                    suggestions=[album.to_api() for album in self.suggestions], nextBefore=self.next_before)
