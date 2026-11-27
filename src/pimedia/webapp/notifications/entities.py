"""Messages privés de l’administration, indépendants des envois musicaux."""
from dataclasses import dataclass

PAGE_SIZE = 40
TITLE_MAX_LENGTH = 120
BODY_MAX_LENGTH = 2000


class NotificationError(ValueError):
    pass


@dataclass(frozen=True)
class Notification:
    id: int
    recipient_id: int
    title: str
    body: str
    created_at: int
    read_at: int | None

    @classmethod
    def from_row(cls, row):
        return cls(*(row[key] for key in ("id", "recipient_id", "title", "body", "created_at", "read_at")))

    def to_api(self):
        return dict(id=self.id, title=self.title, body=self.body, createdAt=self.created_at, readAt=self.read_at)


@dataclass(frozen=True)
class NotificationStatus:
    unread: int

    def to_api(self):
        return dict(unread=self.unread)


@dataclass(frozen=True)
class NotificationPage:
    entries: tuple
    before: int | None
    unread: int

    def to_api(self):
        return dict(entries=[entry.to_api() for entry in self.entries], before=self.before, unread=self.unread,
                    limits=dict(title=TITLE_MAX_LENGTH, body=BODY_MAX_LENGTH))


@dataclass(frozen=True)
class NotificationDelivery:
    notification: Notification
    created: bool
