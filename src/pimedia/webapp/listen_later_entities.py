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


@dataclass(frozen=True)
class Recommendation:
    id: int
    sender_id: int
    sender_name: str
    recipient_id: int
    target: ListeningTarget
    created_at: int
    unread_token: str | None = None

    @classmethod
    def from_row(cls, row):
        return cls(row["id"], row["sender_id"], row["sender_name"], row["recipient_id"],
                   ListeningTarget.from_row(row), row["created_at"], row["unread_token"])

    def to_api(self):
        return dict(id=self.id, sender=self.sender_name, target=self.target.to_api(), createdAt=self.created_at)


@dataclass(frozen=True)
class RecommendationGroup:
    target: ListeningTarget
    recommendations: tuple

    @property
    def created_at(self):
        return max(r.created_at for r in self.recommendations)

    def to_api(self):
        return dict(target=self.target.to_api(),
                    unreadTokens=[r.unread_token for r in self.recommendations if r.unread_token is not None],
                    senders=[dict(id=r.sender_id, username=r.sender_name) for r in self.recommendations],
                    createdAt=self.created_at)
