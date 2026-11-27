"""Entités MusicBrainz, indépendantes de la bibliothèque, du site et du Pi."""
from dataclasses import asdict, dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class Result:
    """Valeur lue chez MusicBrainz ; stale signale une copie de secours pendant une panne."""
    value: object
    stale: bool = False


@dataclass(frozen=True)
class MusicLink:
    """Lien vers une identité MusicBrainz, avec son rôle et la période de la relation."""
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
class MusicArtist:
    """Identité MusicBrainz ; les homonymes restent des choix distincts."""
    id: str
    name: str
    type: str = ""
    country: str = ""
    description: str = ""

    def to_api(self):
        return asdict(self)


@dataclass(frozen=True)
class MusicLabel:
    """Label MusicBrainz trouvé par une recherche ; les homonymes restent des choix distincts."""
    id: str
    name: str
    country: str = ""
    description: str = ""

    def to_api(self):
        return asdict(self)


@dataclass(frozen=True)
class AlbumLabel:
    """Label d'un album et édition MusicBrainz d'où il a été lu."""
    label: MusicLabel
    release_id: str


@dataclass(frozen=True)
class MusicWork:
    """Sortie ou enregistrement MusicBrainz figurant dans un catalogue ou un crédit."""
    id: str
    title: str
    artist: str
    kind: str
    date: str = ""
    role: str = "artist"

    def to_api(self):
        return asdict(self)


@dataclass(frozen=True)
class Edition:
    """Édition d'un album : la même entité pour l'exploration et pour l'édition des tags."""
    id: str
    title: str
    artist: str
    date: str = ""
    country: str = ""
    format: str = ""
    track_count: int = 0
    labels: tuple = ()

    def to_api(self):
        return dict(id=self.id, title=self.title, artist=self.artist, date=self.date, country=self.country,
                    format=self.format, labels=list(self.labels))


@dataclass(frozen=True)
class Track:
    position: str
    track: Optional[int]
    disc: Optional[int]
    title: str
    artist: str
    duration: Optional[int] = None


@dataclass(frozen=True)
class Release:
    id: str
    title: str
    artist: str
    date: str
    country: str
    format: str
    genres: tuple
    tracks: tuple


@dataclass
class ArtistConnections:
    id: str
    name: str
    relations: list
    stale: bool = False

    def to_api(self):
        return dict(id=self.id, name=self.name, relations=[r.to_api() for r in self.relations], stale=self.stale)


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


@dataclass(frozen=True)
class ReleaseGenre:
    """Un style est identifié par son nom exact dans le catalogue MusicBrainz : la valeur envoyée dans les recherches."""
    name: str

    def to_api(self):
        return {"name": self.name}


@dataclass(frozen=True)
class WeeklyRelease:
    id: str
    title: str
    artist: str
    released_on: date
    kind: str
    tags: tuple = ()

    def to_api(self):
        return {"id": self.id, "title": self.title, "artist": self.artist,
                "date": self.released_on.isoformat(), "type": self.kind}


@dataclass(frozen=True)
class WeeklyReleasePage:
    albums: tuple
    next_offset: Optional[int]
    stale: bool

    def to_api(self):
        return {"albums": [album.to_api() for album in self.albums], "next": self.next_offset, "stale": self.stale}
