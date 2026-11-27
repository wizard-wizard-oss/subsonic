"""Entités du radar des sorties."""
import json
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class RadarSource:
    """Ce qu'un compte suit : un style (nom exact du catalogue), un label ou un artiste (MBID), un proche."""
    id: int
    kind: str
    identity: str
    name: str
    origin: str
    hidden: bool = False
    via: Optional[str] = None

    @classmethod
    def from_row(cls, row):
        return cls(row["id"], row["kind"], row["identity"], row["name"], row["origin"], bool(row["hidden"]),
                   row["via"])

    @property
    def key(self):
        return self.kind, self.identity

    def to_api(self):
        return {"id": self.id, "kind": self.kind, "identity": self.identity, "name": self.name,
                "origin": self.origin, "via": self.via}


@dataclass(frozen=True)
class RadarRelease:
    """Groupe de sorties MusicBrainz trouvé par la synchronisation (première sortie datée du jour exact)."""
    id: str
    title: str
    artist: str
    released_on: date
    kind: str
    tags: tuple = ()

    @classmethod
    def from_row(cls, row):
        return cls(row["id"], row["title"], row["artist"], date.fromisoformat(row["released_on"]), row["kind"],
                   tuple(json.loads(row["tags"])))

    def to_api(self):
        return {"id": self.id, "title": self.title, "artist": self.artist,
                "date": self.released_on.isoformat(), "type": self.kind}


@dataclass(frozen=True)
class RadarCard:
    """Une sortie telle qu'un compte la voit : pourquoi elle est là, sa ressemblance avec ses goûts, sa copie locale."""
    release: RadarRelease
    reasons: tuple
    score: float = 0.0
    local: Optional[dict] = None

    def to_api(self):
        return dict(self.release.to_api(), reasons=[reason.to_api() for reason in self.reasons],
                    score=round(self.score, 3), local=self.local)
