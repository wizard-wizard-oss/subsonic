"""Entités de l'exploration musicale : identités externes et crédits, sans dépendance HTTP ou SQL."""
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class MusicLink:
    id: str
    name: str
    kind: str = "artist"
    role: str = "artist"
    detail: str = ""
    begin: str = ""
    end: str = ""
    ended: bool = False

    def to_api(self):
        return asdict(self)


@dataclass(frozen=True)
class MusicEdition:
    id: str
    title: str
    artist: str
    date: str = ""
    country: str = ""
    format: str = ""
    labels: tuple = ()

    def to_api(self):
        return asdict(self)


@dataclass(frozen=True)
class MusicArtist:
    id: str
    name: str
    type: str = ""
    country: str = ""
    description: str = ""

    def to_api(self):
        return asdict(self)


@dataclass
class ArtistMatches:
    artists: list
    stale: bool = False

    def to_api(self):
        return dict(artists=[a.to_api() for a in self.artists], stale=self.stale)


@dataclass
class ArtistConnections:
    id: str
    name: str
    relations: list
    stale: bool = False

    def to_api(self):
        return dict(id=self.id, name=self.name, relations=[r.to_api() for r in self.relations], stale=self.stale)


@dataclass
class AlbumCredits:
    editions: list = field(default_factory=list)
    selected: str = ""
    labels: list = field(default_factory=list)
    people: list = field(default_factory=list)
    stale: bool = False

    def to_api(self):
        return {"editions": [e.to_api() for e in self.editions], "selected": self.selected,
                "labels": [e.to_api() for e in self.labels], "people": [e.to_api() for e in self.people],
                "stale": self.stale}


@dataclass(frozen=True)
class MusicWork:
    id: str
    title: str
    artist: str
    kind: str
    date: str = ""
    role: str = "artist"

    def to_api(self):
        return asdict(self)


@dataclass
class MusicProfile:
    id: str
    name: str
    kind: str
    description: str
    relations: list
    works: list
    more: bool
    offset: int
    next_offset: int
    stale: bool = False

    def to_api(self):
        return dict(id=self.id, name=self.name, kind=self.kind, description=self.description,
                    relations=[r.to_api() for r in self.relations], works=[w.to_api() for w in self.works],
                    more=self.more, offset=self.offset, nextOffset=self.next_offset, stale=self.stale)
