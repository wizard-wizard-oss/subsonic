"""Contrats de l'éditeur de tags ; les chemins et sauvegardes restent internes au serveur."""
import re
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .sources import SourceRelease

TAG_FIELDS = ("title", "artist", "albumArtist", "album", "year", "genre", "track", "disc")
TAG_EDIT_RIGHT = "coverArt"
MAX_TAG_TEXT = 500
MAX_ALBUM_TRACKS = 500
MAX_TAG_NUMBER = 999
MIN_TAG_YEAR = 1000
MAX_TAG_YEAR = 9999
TAG_BODY_LIMIT = MAX_ALBUM_TRACKS * len(TAG_FIELDS) * (MAX_TAG_TEXT + 32)


class TagError(ValueError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


def tag_limits():
    return dict(text=MAX_TAG_TEXT, tracks=MAX_ALBUM_TRACKS, number=MAX_TAG_NUMBER,
                yearMin=MIN_TAG_YEAR, yearMax=MAX_TAG_YEAR)


def reference(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 100 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise TagError("tags.bad_request")
    return value


def tag_value(name, value):
    if name not in TAG_FIELDS or not isinstance(value, str):
        raise TagError("tags.bad_request")
    value = value.strip()
    if len(value) > MAX_TAG_TEXT or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise TagError("tags.bad_value")
    if value and name in ("track", "disc", "year"):
        minimum, maximum = (MIN_TAG_YEAR, MAX_TAG_YEAR) if name == "year" else (1, MAX_TAG_NUMBER)
        if not value.isascii() or not value.isdigit() or not minimum <= int(value) <= maximum:
            raise TagError("tags.bad_value")
        value = str(int(value))
    return value



class AudioTagError(ValueError):
    """Erreur publique exprimée par une clé i18n, sans chemin du serveur."""


@dataclass(frozen=True)
class AudioFileSnapshot:
    relative_path: str
    revision: str
    format: str
    editable: bool
    reason: str
    tags: dict


@dataclass(frozen=True)
class AudioFileEdit:
    relative_path: str
    expected_revision: str
    changes: dict

@dataclass(frozen=True)
class TagEditorStatus:
    """L'éditeur peut-il écrire ici ; sinon pourquoi (reprise inachevée, dossier absent), et ses sources et limites."""
    writable: bool
    reason: str | None
    providers: dict
    formats: tuple
    limits: dict

    def to_api(self):
        return dict(writable=self.writable, reason=self.reason, providers=self.providers, formats=list(self.formats),
                    limits=self.limits)

@dataclass(frozen=True)
class TagValues:
    title: str = ""
    artist: str = ""
    albumArtist: str = ""
    album: str = ""
    year: str = ""
    genre: str = ""
    track: str = ""
    disc: str = ""

    @classmethod
    def of(cls, values):
        return cls(**{name: str(values.get(name) or "") for name in TAG_FIELDS})

    def to_api(self):
        return asdict(self)


@dataclass(frozen=True)
class TagTrack:
    id: str
    format: str
    editable: bool
    reason: str
    tags: TagValues
    duration: int = 0

    def to_api(self):
        return dict(id=self.id, format=self.format, editable=self.editable, reason=self.reason,
                    tags=self.tags.to_api(), duration=self.duration)


@dataclass(frozen=True)
class AlbumTagSnapshot:
    album_id: str
    name: str
    artist: str
    revision: str
    tracks: tuple
    warnings: tuple = ()

    def to_api(self):
        return dict(albumId=self.album_id, name=self.name, artist=self.artist, revision=self.revision,
                    tracks=[track.to_api() for track in self.tracks], warnings=list(self.warnings))


@dataclass(frozen=True)
class FieldEdit:
    field: str
    value: str


@dataclass(frozen=True)
class TrackEdit:
    id: str
    changes: tuple


@dataclass(frozen=True)
class AlbumTagPatch:
    album_id: str
    revision: str
    tracks: tuple

    @classmethod
    def parse(cls, body):
        if not isinstance(body, dict) or set(body) - {"albumId", "revision", "tracks"}:
            raise TagError("tags.bad_request")
        album_id = reference(body.get("albumId"))
        revision = body.get("revision")
        tracks = body.get("tracks")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
            raise TagError("tags.bad_request")
        if not isinstance(tracks, list) or not 1 <= len(tracks) <= MAX_ALBUM_TRACKS:
            raise TagError("tags.bad_request")
        parsed, seen = [], set()
        for item in tracks:
            if not isinstance(item, dict) or set(item) != {"id", "changes"}:
                raise TagError("tags.bad_request")
            identity = reference(item.get("id"))
            changes = item.get("changes")
            if identity in seen or not isinstance(changes, dict) or not changes or set(changes) - set(TAG_FIELDS):
                raise TagError("tags.bad_request")
            seen.add(identity)
            parsed.append(TrackEdit(identity, tuple(FieldEdit(name, tag_value(name, value))
                                                    for name, value in changes.items())))
        return cls(album_id, revision, tuple(parsed))


@dataclass(frozen=True)
class TagDifference:
    id: str
    title: str
    field: str
    before: str
    after: str

    def to_api(self):
        return asdict(self)


@dataclass(frozen=True)
class TagPreview:
    changes: tuple

    def to_api(self):
        return dict(changes=[change.to_api() for change in self.changes],
                    trackCount=len({change.id for change in self.changes}))


@dataclass(frozen=True)
class TagReleaseProposal:
    release: "SourceRelease"
    mapping: tuple

    def to_api(self):
        return dict(self.release.to_api(), mapping=list(self.mapping))


@dataclass
class TagOperation:
    id: str
    owner_id: int
    album_id: str
    created_at: float
    state: str = "saving"
    phase: str = "preparing"
    completed: int = 0
    total: int = 0
    error: str = ""
    scan: str = "pending"
    warnings: list = field(default_factory=list)

    def to_api(self):
        return dict(operationId=self.id, state=self.state, phase=self.phase, completed=self.completed, total=self.total,
                    error=self.error, scan=self.scan, warnings=list(self.warnings))
