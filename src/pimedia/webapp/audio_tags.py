"""Lecture ciblée et écriture des tags audio, sans catalogue parallèle ni renommage.

Une préparation complète précède la publication. Les originaux restent dans un dossier technique
hors de la musique scannée ; un manifeste sans valeurs de tags permet de reprendre un lot interrompu.
"""
import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import mutagen
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError, TALB, TCON, TDRC, TPE1, TPE2, TIT2, TRCK, TPOS, TYER
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from .tag_entities import MAX_TAG_NUMBER, MAX_TAG_TEXT, TAG_FIELDS, TagError, tag_value

SUPPORTED_FORMATS = ("mp3", "flac", "m4a", "ogg", "opus", "wav", "aiff")
FIELDS = TAG_FIELDS
TEXT_LIMIT = MAX_TAG_TEXT
MAX_NUMBER = MAX_TAG_NUMBER
BACKUP_RETENTION_SECONDS = 86400
MAX_BACKUP_OPERATIONS = 8
MAX_BACKUP_BYTES = 4 * 1024 ** 3
SPACE_MARGIN = 65536
_ID3_FIELDS = {"title": TIT2, "artist": TPE1, "albumArtist": TPE2, "album": TALB,
               "genre": TCON, "track": TRCK, "disc": TPOS}
_COMMENT_FIELDS = {"title": "title", "artist": "artist", "albumArtist": "albumartist", "album": "album",
                   "year": "date", "genre": "genre", "track": "tracknumber", "disc": "discnumber"}
_MP4_FIELDS = {"title": "\xa9nam", "artist": "\xa9ART", "albumArtist": "aART", "album": "\xa9alb",
               "year": "\xa9day", "genre": "\xa9gen", "track": "trkn", "disc": "disk"}


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


def _identity(path):
    info = os.stat(path, follow_symlinks=False)
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid]


def _revision(path):
    info = os.stat(path, follow_symlinks=False)
    value = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
             stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid, info.st_ctime_ns)
    return hashlib.sha256(repr(value).encode("ascii")).hexdigest()


def _digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(values):
    return "; ".join(str(value) for value in (values or []) if str(value))


def _number(value):
    return str(value or "").split("/", 1)[0].strip()


def _date(value):
    value = str(value or "")
    return value[:4] if len(value) >= 4 and value[:4].isdigit() else value


def _with_total(value, previous):
    """Le champ numéro n'efface pas le nombre total de pistes/disques déjà présent."""
    parts = str(previous or "").split("/", 1)
    return value + "/" + parts[1] if value and len(parts) == 2 and parts[1].isdigit() else value


def _with_date(value, previous):
    previous = str(previous or "")
    return value + previous[4:] if value and len(previous) > 4 and previous[:4].isdigit() else value


def validate_changes(changes):
    if not isinstance(changes, dict) or not changes or any(key not in FIELDS for key in changes):
        raise AudioTagError("tags.invalid_changes")
    try:
        return {key: tag_value(key, value) for key, value in changes.items()}
    except TagError as error:
        raise AudioTagError(str(error)) from None


def _discard(tags, name):
    if name in tags:
        del tags[name]


def _load(path):
    audio = mutagen.File(path)
    if isinstance(audio, MP3):
        try:
            tags = ID3(path, translate=False)
        except ID3NoHeaderError:
            tags = ID3()
        return "mp3", tags
    for audio_type, kind in ((FLAC, "flac"), (MP4, "m4a"), (OggVorbis, "ogg"), (OggOpus, "opus"),
                             (WAVE, "wav"), (AIFF, "aiff")):
        if isinstance(audio, audio_type):
            if audio.tags is None:
                audio.add_tags()
            elif isinstance(audio.tags, ID3):
                # Les sous-classes WAVE/AIFF connaissent leur conteneur ; préserver ID3v2.3 à la lecture.
                audio.tags = type(audio.tags)(path, translate=False)
            return kind, audio
    raise AudioTagError("tags.unsupported_format")


def _read(kind, document):
    tags = document if kind == "mp3" else document.tags
    result = dict.fromkeys(FIELDS, "")
    if isinstance(tags, ID3):
        for key, frame in _ID3_FIELDS.items():
            result[key] = _text(value for item in tags.getall(frame.__name__) for value in item.text)
        year = tags.get("TDRC") or tags.get("TYER")
        result["year"] = _date(str(year)) if year else ""
    elif kind == "m4a":
        for key, atom in _MP4_FIELDS.items():
            values = tags.get(atom) or []
            result[key] = str(values[0][0]) if key in ("track", "disc") and values else _text(values)
        result["year"] = _date(result["year"])
    else:
        for key, name in _COMMENT_FIELDS.items():
            result[key] = _text(tags.get(name) or (tags.get("year") if key == "year" else []))
        result["year"] = _date(result["year"])
    result["track"], result["disc"] = _number(result["track"]), _number(result["disc"])
    return result


def _write(path, changes):
    kind, document = _load(path)
    tags = document if kind == "mp3" else document.tags
    if isinstance(tags, ID3):
        version = 3 if tags.version[1] == 3 else 4
        for key, value in changes.items():
            if key == "year":
                old = tags.get("TYER" if version == 3 else "TDRC")
                for name in ("TYER", "TDRC"):
                    tags.delall(name)
                if value:
                    frame = TYER if version == 3 else TDRC
                    tags.add(frame(encoding=1 if version == 3 else 3, text=[_with_date(value, str(old or ""))]))
                continue
            frame = _ID3_FIELDS[key]
            old = tags.get(frame.__name__)
            tags.delall(frame.__name__)
            if value:
                text = _with_total(value, str(old or "")) if key in ("track", "disc") else value
                tags.add(frame(encoding=1 if version == 3 else 3, text=[text]))
        if kind == "mp3":
            tags.save(path, v2_version=version, v1=1)
        else:
            document.save(v2_version=version)
    elif kind == "m4a":
        for key, value in changes.items():
            atom = _MP4_FIELDS[key]
            old = tags.get(atom) or []
            if not value:
                _discard(tags, atom)
            elif key in ("track", "disc"):
                tags[atom] = [(int(value), old[0][1] if old else 0)]
            else:
                tags[atom] = [_with_date(value, old[0] if old else "") if key == "year" else value]
            if key == "genre":
                _discard(tags, "gnre")
        document.save()
    else:
        for key, value in changes.items():
            name = _COMMENT_FIELDS[key]
            old = (tags.get(name) or [""])[0]
            if not value:
                _discard(tags, name)
            else:
                tags[name] = [_with_total(value, old) if key in ("track", "disc") else
                              _with_date(value, old) if key == "year" else value]
            if key == "year":
                _discard(tags, "year")
        document.save()


class AudioTags:
    """Écrivain unique, lots sérialisés, contrôles de concurrence et récupération conservatrice."""
    def __init__(self, music_dir, backup_dir):
        self.music_dir = os.path.realpath(music_dir) if music_dir else ""
        self.backup_dir = os.path.realpath(backup_dir)
        self.lock = threading.RLock()

    def _path(self, relative):
        if not self.music_dir or not os.path.isdir(self.music_dir):
            raise AudioTagError("tags.off")
        if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
            raise AudioTagError("tags.unsafe_path")
        parts = PurePosixPath(relative).parts
        if PurePosixPath(relative).is_absolute() or any(part in (".", "..") for part in relative.split("/")):
            raise AudioTagError("tags.unsafe_path")
        path = self.music_dir
        try:
            for part in parts:
                path = os.path.join(path, part)
                info = os.lstat(path)
                if stat.S_ISLNK(info.st_mode):
                    raise AudioTagError("tags.unsafe_path")
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise AudioTagError("tags.unsafe_path")
        except OSError:
            raise AudioTagError("tags.file_unavailable") from None
        if os.path.commonpath((self.music_dir, os.path.realpath(path))) != self.music_dir:
            raise AudioTagError("tags.unsafe_path")
        return path

    def inspect(self, relative_path):
        path = self._path(relative_path)
        try:
            revision = _revision(path)
            kind, document = _load(path)
            tags = _read(kind, document)
            editable = os.access(path, os.W_OK) and os.access(os.path.dirname(path), os.W_OK | os.X_OK)
            if isinstance(document if kind == "mp3" else document.tags, ID3):
                editable = editable and (document if kind == "mp3" else document.tags).version[1] in (3, 4)
            if _revision(path) != revision:
                raise AudioTagError("tags.conflict")
            return AudioFileSnapshot(relative_path, revision, kind, editable, "" if editable else "tags.not_writable", tags)
        except AudioTagError as error:
            if str(error) != "tags.unsupported_format":
                raise
            return AudioFileSnapshot(relative_path, _revision(path), Path(path).suffix.lstrip(".").lower(),
                                     False, str(error), dict.fromkeys(FIELDS, ""))
        except (mutagen.MutagenError, ValueError, OSError):
            return AudioFileSnapshot(relative_path, _revision(path), Path(path).suffix.lstrip(".").lower(),
                                     False, "tags.unreadable_file", dict.fromkeys(FIELDS, ""))

    @staticmethod
    def _copy(source, destination):
        shutil.copy2(source, destination)
        original, copied = os.stat(source), os.stat(destination)
        if (original.st_uid, original.st_gid) != (copied.st_uid, copied.st_gid):
            os.chown(destination, original.st_uid, original.st_gid)

    @staticmethod
    def _sync(path):
        with open(path, "rb") as item:
            os.fsync(item.fileno())

    @staticmethod
    def _sync_directory(path):
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @contextlib.contextmanager
    def _exclusive(self):
        if self.music_dir and os.path.commonpath((self.music_dir, self.backup_dir)) == self.music_dir:
            raise AudioTagError("tags.unsafe_backup")
        os.makedirs(self.backup_dir, mode=0o700, exist_ok=True)
        with self.lock, open(os.path.join(self.backup_dir, ".lock"), "a+b") as lockfile:
            fcntl.flock(lockfile, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lockfile, fcntl.LOCK_UN)

    def _manifest(self, operation, data):
        path = os.path.join(operation, "manifest.json")
        part = path + ".part"
        with open(part, "w", encoding="utf-8") as target:
            json.dump(data, target, ensure_ascii=False)
            target.flush()
            os.fsync(target.fileno())
        os.replace(part, path)
        self._sync_directory(operation)

    @staticmethod
    def _temporary(path):
        descriptor, name = tempfile.mkstemp(prefix=".pimedia-tags-", suffix=".part", dir=os.path.dirname(path))
        os.close(descriptor)
        return name

    def _matches_publication(self, path, entry):
        if entry.get("published_revision"):
            return _revision(path) == entry["published_revision"]
        return (_identity(path) == entry.get("prepared_identity")
                and _digest(path) == entry.get("prepared_digest"))

    @staticmethod
    def _backup_path(operation, entry):
        name = entry.get("backup", "")
        if not isinstance(name, str) or not name.endswith(".original") or not name[:-9].isdigit():
            raise AudioTagError("tags.recovery_required")
        path = os.path.join(operation, name)
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise AudioTagError("tags.recovery_required")
        return path

    def _rollback(self, operation, manifest):
        failed = False
        if manifest["state"] == "preparing":
            manifest["state"] = "rolled_back"
            self._manifest(operation, manifest)
            return
        for entry in reversed(manifest["entries"]):
            temporary = ""
            try:
                path = self._path(entry["relative"])
                if _revision(path) == entry["original_revision"] or entry.get("restored"):
                    continue
                if entry.get("original_digest") and _digest(path) == entry["original_digest"]:
                    # Une panne peut avoir précédé l'écriture de l'accusé de restauration.
                    entry["restored"] = True
                    continue
                if not self._matches_publication(path, entry):
                    failed = True
                    continue
                backup = self._backup_path(operation, entry)
                if _digest(backup) != entry["original_digest"]:
                    failed = True
                    continue
                temporary = self._temporary(path)
                self._copy(backup, temporary)
                self._sync(temporary)
                if not self._matches_publication(path, entry):
                    failed = True
                    continue
                os.replace(temporary, path)
                self._sync_directory(os.path.dirname(path))
                entry["restored"] = True
                self._manifest(operation, manifest)
            except (OSError, ValueError, KeyError):
                failed = True
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
        manifest["state"] = "needs_recovery" if failed else "rolled_back"
        self._manifest(operation, manifest)
        if failed:
            raise AudioTagError("tags.recovery_required")

    def _recover(self):
        for operation in Path(self.backup_dir).iterdir():
            if not operation.is_dir() or operation.is_symlink() or len(operation.name) != 32:
                continue
            try:
                if not (operation / "manifest.json").exists():
                    # Aucun fichier musical n'est publié avant le premier manifeste complet.
                    shutil.rmtree(operation)
                    continue
                if (operation / "manifest.json").is_symlink():
                    raise AudioTagError("tags.recovery_required")
                with open(operation / "manifest.json", encoding="utf-8") as source:
                    manifest = json.load(source)
                if manifest.get("version") != 1 or manifest.get("root") != self.music_dir:
                    continue
                if manifest.get("state") in ("committed", "rolled_back"):
                    self._cleanup_temporaries(manifest)
                    continue
                self._rollback(str(operation), manifest)
                self._cleanup_temporaries(manifest)
            except (OSError, ValueError, KeyError, TypeError):
                raise AudioTagError("tags.recovery_required") from None
        self._prune()

    def recover(self):
        try:
            with self._exclusive():
                self._recover()
        except AudioTagError:
            raise
        except OSError:
            raise AudioTagError("tags.backup_failed") from None

    def _cleanup_temporaries(self, manifest):
        for entry in manifest["entries"]:
            name = entry.get("temporary", "")
            if name and os.path.basename(name) == name and name.startswith(".pimedia-tags-") and name.endswith(".part"):
                try:
                    folder = os.path.dirname(self._path(entry["relative"]))
                    path = os.path.join(folder, name)
                    if os.path.isfile(path) and not os.path.islink(path):
                        os.unlink(path)
                except (OSError, AudioTagError):
                    pass

    def _prune(self):
        finished = []
        for operation in Path(self.backup_dir).iterdir():
            if not operation.is_dir() or operation.is_symlink() or len(operation.name) != 32:
                continue
            try:
                manifest = json.loads((operation / "manifest.json").read_text(encoding="utf-8"))
                if manifest.get("root") == self.music_dir and manifest.get("state") in ("committed", "rolled_back"):
                    size = sum(item.stat().st_size for item in operation.iterdir() if item.is_file())
                    finished.append((operation.stat().st_mtime, operation, size))
            except (OSError, ValueError):
                continue
        finished.sort(reverse=True)
        total = 0
        for index, (modified, operation, size) in enumerate(finished):
            total += size
            if index >= MAX_BACKUP_OPERATIONS or total > MAX_BACKUP_BYTES or time.time() - modified > BACKUP_RETENTION_SECONDS:
                try:
                    shutil.rmtree(operation)
                except OSError:
                    pass

    def _space(self, paths):
        required = sum(os.path.getsize(path) for path in paths)
        same_disk = os.stat(self.music_dir).st_dev == os.stat(self.backup_dir).st_dev
        if shutil.disk_usage(self.backup_dir).free < required * (2 if same_disk else 1) + SPACE_MARGIN:
            raise AudioTagError("tags.no_space")
        if not same_disk and shutil.disk_usage(self.music_dir).free < required + SPACE_MARGIN:
            raise AudioTagError("tags.no_space")

    def apply(self, edits, progress=None):
        edits = tuple(edits)
        if not edits or len({edit.relative_path for edit in edits}) != len(edits):
            raise AudioTagError("tags.invalid_changes")
        edits = tuple(AudioFileEdit(edit.relative_path, edit.expected_revision, validate_changes(edit.changes))
                      for edit in edits)
        try:
            with self._exclusive():
                self._recover()
                self._apply(edits, progress)
        except AudioTagError:
            raise
        except (OSError, mutagen.MutagenError, ValueError):
            raise AudioTagError("tags.write_failed") from None

    def _apply(self, edits, progress):
        if progress:
            progress("preparing", 0, len(edits))
        snapshots = tuple(self.inspect(edit.relative_path) for edit in edits)
        if any(not snapshot.editable for snapshot in snapshots):
            raise AudioTagError(next(snapshot.reason for snapshot in snapshots if not snapshot.editable))
        if any(edit.expected_revision != snapshot.revision for edit, snapshot in zip(edits, snapshots)):
            raise AudioTagError("tags.conflict")
        paths = tuple(self._path(edit.relative_path) for edit in edits)
        self._space(paths)
        operation = os.path.join(self.backup_dir, uuid.uuid4().hex)
        os.mkdir(operation, mode=0o700)
        manifest = {"version": 1, "root": self.music_dir, "state": "preparing", "entries": []}
        self._manifest(operation, manifest)
        try:
            for index, (edit, path) in enumerate(zip(edits, paths)):
                entry = {"relative": edit.relative_path, "original_revision": edit.expected_revision,
                         "backup": str(index) + ".original"}
                manifest["entries"].append(entry)
                backup = os.path.join(operation, entry["backup"])
                self._copy(path, backup)
                self._sync(backup)
                entry["original_digest"] = _digest(backup)
                temporary = self._temporary(path)
                entry["temporary"] = os.path.basename(temporary)
                self._manifest(operation, manifest)
                self._copy(backup, temporary)
                _write(temporary, edit.changes)
                kind, document = _load(temporary)
                actual = _read(kind, document)
                if any(actual[key] != value for key, value in edit.changes.items()):
                    raise AudioTagError("tags.verification_failed")
                self._sync(temporary)
                entry["prepared_identity"] = _identity(temporary)
                entry["prepared_digest"] = _digest(temporary)
                self._manifest(operation, manifest)
                if progress:
                    progress("preparing", index + 1, len(edits))
            if any(_revision(self._path(edit.relative_path)) != edit.expected_revision for edit in edits):
                raise AudioTagError("tags.conflict")
            manifest["state"] = "publishing"
            self._manifest(operation, manifest)
            if progress:
                progress("publishing", 0, len(edits))
            for index, (edit, entry) in enumerate(zip(edits, manifest["entries"])):
                path = self._path(edit.relative_path)
                if _revision(path) != edit.expected_revision:
                    raise AudioTagError("tags.conflict")
                temporary = os.path.join(os.path.dirname(path), entry["temporary"])
                os.replace(temporary, path)
                self._sync_directory(os.path.dirname(path))
                entry["published_revision"] = _revision(path)
                self._manifest(operation, manifest)
                if progress:
                    progress("publishing", index + 1, len(edits))
            manifest["state"] = "committed"
            self._manifest(operation, manifest)
        except BaseException:
            self._rollback(operation, manifest)
            raise
        finally:
            self._cleanup_temporaries(manifest)
        self._prune()
