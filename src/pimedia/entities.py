"""Entités : les objets métier que les dépôts (storage/) renvoient.

Chaque entité sait se convertir au format JSON attendu par la page (to_api) ; les noms d'attributs
suivent les colonnes de la base (en anglais), les clés du JSON restent celles que la page utilise déjà."""
from dataclasses import dataclass, field
from typing import List, Optional

from .tracks import clean_track


@dataclass(frozen=True)
class Track:
    """Un titre (Subsonic, Jamendo, YouTube…). Ses champs varient selon la source : on garde le dictionnaire validé."""
    fields: dict

    @classmethod
    def from_api(cls, raw):
        """Titre reçu de la page : seuls les champs connus sont gardés, les adresses douteuses refusées."""
        return cls(clean_track(raw))

    @property
    def id(self):
        return self.fields["id"]

    @property
    def title(self):
        return self.fields["title"]

    @property
    def youtube_id(self):
        return self.fields.get("youtubeId")

    def to_api(self):
        return dict(self.fields)


@dataclass(frozen=True)
class PodcastSubscription:
    feed_url: str
    title: str
    image_url: str = ""
    author: str = ""
    subscribed_at: int = 0

    def to_api(self):
        return {"feed": self.feed_url, "title": self.title, "image": self.image_url, "author": self.author,
                "added": self.subscribed_at}


@dataclass(frozen=True)
class EpisodeProgress:
    episode_id: str
    feed_url: str = ""
    title: str = ""
    podcast_title: str = ""
    image_url: str = ""
    audio_url: str = ""
    position_s: float = 0.0
    duration_s: float = 0.0
    played: bool = False
    updated_at: int = 0

    def to_api(self):
        return {"id": self.episode_id, "feed": self.feed_url, "title": self.title, "podcast": self.podcast_title,
                "image": self.image_url, "audio": self.audio_url, "pos": self.position_s, "dur": self.duration_s,
                "played": self.played, "t": self.updated_at}


@dataclass(frozen=True)
class PlaylistSummary:
    id: str
    name: str
    track_count: int

    def to_api(self):
        return {"id": self.id, "name": self.name, "count": self.track_count}


@dataclass(frozen=True)
class Playlist:
    id: str
    name: str
    created_at: int = 0
    tracks: List[Track] = field(default_factory=list)

    def to_api(self):
        return {"id": self.id, "name": self.name, "songs": [t.to_api() for t in self.tracks]}


@dataclass(frozen=True)
class QueueItem:
    """Un titre de la file d'attente commune du Pi, et qui l'a ajouté (écran, téléphone…)."""
    id: int
    position: int
    track: Track
    added_by: str = "screen"
    added_at: int = 0

    def to_api(self):
        return {"itemId": self.id, "position": self.position, "addedBy": self.added_by, "track": self.track.to_api()}


@dataclass(frozen=True)
class QueueSnapshot:
    """La file entière à un instant : titres, titre en cours, numéro de version (change à chaque modification)."""
    items: List[QueueItem]
    current_item_id: Optional[int]
    version: int

    @property
    def current_index(self):
        return next((i for i, item in enumerate(self.items) if item.id == self.current_item_id), -1)

    @property
    def current(self):
        index = self.current_index
        return self.items[index] if index >= 0 else None

    def to_api(self):
        return {"items": [i.to_api() for i in self.items], "currentItemId": self.current_item_id,
                "currentIndex": self.current_index, "version": self.version}


@dataclass(frozen=True)
class QueueRequest:
    """Demande d'ajout à la file faite depuis un téléphone : « après ce titre » (next) ou « à la fin » (end)."""
    id: int
    track: Track
    mode: str
    added_by: str

    def to_api(self):
        return {"requestId": self.id, "mode": self.mode, "addedBy": self.added_by, "track": self.track.to_api()}
