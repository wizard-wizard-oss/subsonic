"""Entités du radar des sorties."""
import json
from dataclasses import dataclass
from datetime import date
from typing import Optional


class RadarError(Exception):
    """Refus expliqué à la page : code (clé de texte i18n) et statut HTTP."""

    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


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


@dataclass(frozen=True)
class RadarFilter:
    """Pastille de la page : « all », « style:<nom> », « labels », « artists » ou « discoveries »."""
    key: str
    count: int
    name: Optional[str] = None

    def to_api(self):
        return {"key": self.key, "count": self.count, "name": self.name}


@dataclass(frozen=True)
class RadarWeek:
    monday: date
    cards: tuple = ()
    filters: tuple = ()
    selected: str = "all"
    next_offset: Optional[int] = None
    updated_at: Optional[int] = None
    refresh_after: Optional[int] = None
    out_of_window: bool = False
    empty: Optional[str] = None
    default_style: str = ""

    def to_api(self):
        return {"monday": self.monday.isoformat(), "cards": [card.to_api() for card in self.cards],
                "filters": [f.to_api() for f in self.filters], "filter": self.selected, "next": self.next_offset,
                "updatedAt": self.updated_at, "refreshAfter": self.refresh_after, "outOfWindow": self.out_of_window,
                "empty": self.empty, "defaultStyle": self.default_style}


@dataclass(frozen=True)
class RadarSettings:
    """Sources visibles d'un compte et réglages du panneau « Mes sources »."""
    sources: tuple
    discoveries_enabled: bool
    discoveries_available: bool
    refresh_cooldown: int
    kinds: tuple = ()
    addable: tuple = ()
    refresh_after: Optional[int] = None

    def to_api(self):
        return {"sources": [s.to_api() for s in self.sources], "discoveriesEnabled": self.discoveries_enabled,
                "discoveriesAvailable": self.discoveries_available, "refreshCooldown": self.refresh_cooldown,
                "kinds": list(self.kinds), "addable": list(self.addable), "refreshAfter": self.refresh_after}


@dataclass(frozen=True)
class RadarRefresh:
    refresh_after: int

    def to_api(self):
        return {"refreshAfter": self.refresh_after}


@dataclass(frozen=True)
class RadarSearch:
    results: tuple
    stale: bool = False

    def to_api(self):
        return {"results": [found.to_api() for found in self.results], "stale": self.stale}
