"""Résultats composés par l'exploration (homonymes, éditions et crédits) ; les entités MusicBrainz sont dans
shared/providers/musicbrainz/entities.py."""
from dataclasses import dataclass, field


@dataclass
class ArtistMatches:
    artists: list
    stale: bool = False

    def to_api(self):
        return dict(artists=[a.to_api() for a in self.artists], stale=self.stale)


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
