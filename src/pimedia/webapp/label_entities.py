"""Catalogue et sélections de labels, sans dépendance aux transports ni au stockage."""
from dataclasses import dataclass, field
from .catalog_entities import CatalogAlbum
from .entities import ImportedTrack


@dataclass(frozen=True)
class LabelScore:
    album: CatalogAlbum
    source: str
    value: float
    votes: int = 0
    listeners: int = 0
    plays: int = 0
    edition: str = ""

    def to_api(self):
        return dict(album=self.album.to_api(), source=self.source, value=self.value, votes=self.votes,
                    listeners=self.listeners, plays=self.plays, edition=self.edition)


@dataclass
class LabelTrack:
    track: ImportedTrack
    album: CatalogAlbum
    choices: list = field(default_factory=list)
    status: str = "missing"
    edition: str = ""

    def to_api(self):
        return dict(track=self.track.to_api(), album=self.album.to_api(), choices=self.choices, status=self.status, edition=self.edition)


@dataclass
class LabelRanking:
    scores: list
    source: str
    analyzed: int
    total: int
    excluded: int = 0

    def to_api(self):
        return dict(scores=[s.to_api() for s in self.scores], source=self.source,
                    analyzed=self.analyzed, total=self.total, excluded=self.excluded, complete=self.analyzed >= self.total)


@dataclass
class LabelAlbumTracks:
    album: CatalogAlbum
    tracks: list
    eligible: bool = True

    def to_api(self):
        return dict(album=self.album.to_api(), tracks=[t.to_api() for t in self.tracks], eligible=self.eligible)
