"""Un envoi réussi et son résultat au moment de la réception."""
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class UploadOrigin:
    path: str
    username: str
    uploaded_at: int

    def to_api(self):
        return {"username": self.username, "uploadedAt": self.uploaded_at}


@dataclass(frozen=True)
class UploadEntry:
    id: int
    user_id: int | None
    username: str
    filename: str
    byte_count: int
    file_count: int
    skipped_count: int
    placed: tuple[str, ...]
    waiting: tuple[str, ...]
    uploaded_at: int

    @classmethod
    def from_row(cls, row):
        return cls(row["id"], row["user_id"], row["username"], row["filename"], row["byte_count"],
                   row["file_count"], row["skipped_count"], tuple(json.loads(row["placed"])),
                   tuple(json.loads(row["waiting"])), row["uploaded_at"])

    def to_api(self):
        return {"id": self.id, "userId": self.user_id, "username": self.username, "filename": self.filename,
                "bytes": self.byte_count, "files": self.file_count, "skipped": self.skipped_count,
                "placed": list(self.placed), "waiting": list(self.waiting), "uploadedAt": self.uploaded_at}
