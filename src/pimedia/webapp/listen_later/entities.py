"""Personal listening intentions and recommendations, independent of playback."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ListeningTarget:
    kind: str
    source: str
    library_key: str
    source_id: str
    title: str
    artist: str = ""
    image_ref: str = ""

    @property
    def key(self):
        return self.kind, self.source, self.library_key, self.source_id

    @classmethod
    def from_row(cls, row):
        return cls(*(row[name] for name in ("kind", "source", "library_key", "source_id",
                                            "title", "artist", "image_ref")))

    def to_api(self):
        return dict(kind=self.kind, source=self.source, sourceId=self.source_id,
                    title=self.title, artist=self.artist, imageRef=self.image_ref)


@dataclass(frozen=True)
class ListenLaterEntry:
    id: int
    user_id: int
    target: ListeningTarget
    created_at: int

    @classmethod
    def from_row(cls, row):
        return cls(row["id"], row["user_id"], ListeningTarget.from_row(row), row["created_at"])

    def to_api(self):
        return dict(id=self.id, target=self.target.to_api(), createdAt=self.created_at)
