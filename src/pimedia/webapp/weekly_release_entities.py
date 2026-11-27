"""Genres suivis et groupes de sorties affichés dans Actualités."""
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class ReleaseGenre:
    id: str
    name: str

    @classmethod
    def from_name(cls, name):
        return cls("genre:" + name, name)

    def to_api(self):
        return {"id": self.id, "name": self.name}


@dataclass(frozen=True)
class WeeklyRelease:
    id: str
    title: str
    artist: str
    released_on: date
    kind: str

    def to_api(self):
        return {"id": self.id, "title": self.title, "artist": self.artist,
                "date": self.released_on.isoformat(), "type": self.kind}


@dataclass(frozen=True)
class WeeklyReleasePage:
    albums: tuple[WeeklyRelease, ...]
    next_offset: Optional[int]
    stale: bool

    def to_api(self):
        return {"albums": [album.to_api() for album in self.albums], "next": self.next_offset, "stale": self.stale}
