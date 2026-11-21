"""Édition d'un album : Subsonic fournit la bibliothèque, les fichiers conservent les tags."""
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import PurePosixPath

from .audio_tags import AudioFileEdit, AudioTagError, SUPPORTED_FORMATS
from .controllers.base import MissingRight
from .subsonic import Credentials
from .tag_entities import (AlbumTagSnapshot, MAX_ALBUM_TRACKS, TAG_EDIT_RIGHT, TagDifference, TagError, TagOperation, TagPreview,
                           TagReleaseProposal, TagTrack, TagValues, reference, tag_limits)
from .tag_matching import propose_mapping, rank_candidates
from .tag_sources import SourceMatches

LOG = logging.getLogger(__name__)
OPERATION_SECONDS = 3600
MAX_OPERATIONS = 32
MAX_ACTIVE_OPERATIONS = 2
PARALLEL_READS = 4


@dataclass(frozen=True)
class _ResolvedTrack:
    track: TagTrack
    relative_path: str
    file_revision: str
    album_id: str
    index_outdated: bool = False


@dataclass(frozen=True)
class _ResolvedAlbum:
    snapshot: AlbumTagSnapshot
    files: tuple


class AlbumTags:
    def __init__(self, folders, subsonic, audio, sources, scanner, refresh=None, clock=time.monotonic):
        self.folders, self.subsonic, self.audio, self.sources = folders, subsonic, audio, sources
        self.scanner, self.refresh, self.clock = scanner, refresh or (lambda: None), clock
        self._lock = threading.Lock()
        self._operations = {}
        self._active = {}
        self._recovery_error = ""
        if self.audio.music_dir and os.path.isdir(self.audio.music_dir):
            try:
                self.audio.recover()
            except AudioTagError:
                self._recovery_error = "tags.recovery_required"

    @staticmethod
    def _check_right(user):
        if not user.can(TAG_EDIT_RIGHT):
            raise MissingRight(TAG_EDIT_RIGHT)

    def status(self, user):
        self._check_right(user)
        return dict(writable=not self._recovery_error and bool(self.audio.music_dir) and os.path.isdir(self.audio.music_dir),
                    reason=self._recovery_error,
                    providers=self.sources.status(), formats=list(SUPPORTED_FORMATS), limits=tag_limits())

    def _read_song(self, user, song, album_path):
        identity = reference(str(song["id"]))
        raw = self.subsonic.call(Credentials.of(user), "getSong", [("id", identity)]).get("song") or {}
        if str(raw.get("id", "")) != identity:
            raise TagError("tags.not_found", 404)
        # L'API fournit l'inventaire et les champs disponibles ; l'éditeur vérifie leur fraîcheur avant toute écriture.
        values = {"title": raw.get("title"), "artist": raw.get("artist"), "album": raw.get("album"),
                  "year": raw.get("year"), "genre": raw.get("genre"), "track": raw.get("track"),
                  "disc": raw.get("discNumber"), "albumArtist": raw.get("albumArtist")}
        relative = raw.get("path")
        if not isinstance(relative, str) or not relative:
            track = TagTrack(identity, str(raw.get("suffix") or ""), False, "tags.no_path", TagValues.of(values),
                             int(raw.get("duration") or 0))
            return _ResolvedTrack(track, "", "", str(raw.get("albumId") or ""))
        target, directory = PurePosixPath(relative), PurePosixPath(album_path)
        if target.is_absolute() or ".." in target.parts or not target.is_relative_to(directory):
            raise TagError("tags.bad_track")
        try:
            file = self.audio.inspect(relative)
        except AudioTagError as error:
            code = error.args[0] if error.args else "tags.file_unavailable"
            raise TagError(code, 409 if code == "tags.conflict" else 400) from None
        outdated = False
        if file.reason not in ("tags.unsupported_format", "tags.unreadable_file"):
            for name, indexed in values.items():
                actual = file.tags.get(name, "")
                if indexed is not None and str(indexed) != actual:
                    outdated = True
                # L'aperçu doit décrire la valeur qui sera remplacée, même avant le prochain scan Subsonic.
                values[name] = actual
        track = TagTrack(identity, file.format, file.editable, file.reason, TagValues.of(values),
                         int(raw.get("duration") or 0))
        return _ResolvedTrack(track, relative, file.revision, str(raw.get("albumId") or ""), outdated)

    def _resolve(self, user, album_id):
        self._check_right(user)
        if self._recovery_error:
            raise TagError(self._recovery_error)
        album = self.folders.album(user, reference(album_id))
        songs = album.get("songs") or []
        if not 1 <= len(songs) <= MAX_ALBUM_TRACKS:
            raise TagError("tags.too_many_tracks" if songs else "tags.not_found")
        album_path = self.folders.album_path(user, album_id)
        if not album_path or PurePosixPath(album_path).is_absolute() or ".." in PurePosixPath(album_path).parts:
            raise TagError("tags.no_path")
        with ThreadPoolExecutor(max_workers=PARALLEL_READS) as pool:
            files = tuple(pool.map(lambda song: self._read_song(user, song, album_path), songs))
        ids = [item.track.id for item in files]
        paths = [item.relative_path for item in files if item.relative_path]
        if len(set(ids)) != len(ids) or len(set(paths)) != len(paths):
            raise TagError("tags.bad_album")
        canonical = str(album.get("folderId") or album_id)
        revision_data = [(item.track.id, item.relative_path, item.file_revision, item.track.tags.to_api()) for item in files]
        revision = hashlib.sha256(json.dumps((canonical, revision_data), sort_keys=True,
                                              ensure_ascii=False).encode("utf-8")).hexdigest()
        snapshot = AlbumTagSnapshot(canonical, album["name"], album["artist"], revision,
                                    tuple(item.track for item in files),
                                    ("tags.index_outdated",) if any(item.index_outdated for item in files) else ())
        return _ResolvedAlbum(snapshot, files)

    def snapshot(self, user, album_id):
        return self._resolve(user, album_id).snapshot

    def search(self, user, album_id, source, artist, album):
        self._check_right(user)
        context = self.folders.album(user, reference(album_id))
        result = self._source_call(self.sources.search, source, artist, album)
        return SourceMatches(result.source, rank_candidates(result.candidates, artist, album, context.get("year")))

    def release(self, user, album_id, source, release_id):
        snapshot = self.snapshot(user, album_id)
        release = self._source_call(self.sources.release, source, release_id)
        return TagReleaseProposal(release, propose_mapping(snapshot.tracks, release.tracks))

    @staticmethod
    def _source_call(method, *args):
        try:
            return method(*args)
        except ValueError as error:
            code = str(error.args[0]) if error.args else "tags.source_unavailable"
            raise TagError(code, 503 if code == "tags.source_unavailable" else 400) from None

    def _prepare(self, user, patch):
        resolved = self._resolve(user, patch.album_id)
        if patch.revision != resolved.snapshot.revision:
            raise TagError("tags.conflict", 409)
        by_id = {item.track.id: item for item in resolved.files}
        differences, edits = [], []
        for change in patch.tracks:
            item = by_id.get(change.id)
            if item is None:
                raise TagError("tags.bad_track")
            if not item.track.editable:
                raise TagError(item.track.reason or "tags.not_writable")
            effective = {}
            for field in change.changes:
                before = getattr(item.track.tags, field.field)
                if field.value != before:
                    effective[field.field] = field.value
                    differences.append(TagDifference(change.id, item.track.tags.title, field.field, before, field.value))
            if effective:
                edits.append(AudioFileEdit(item.relative_path, item.file_revision, effective))
        if not edits:
            raise TagError("tags.no_changes")
        return resolved, tuple(edits), TagPreview(tuple(differences))

    def preview(self, user, patch):
        return self._prepare(user, patch)[2]

    def save(self, user, patch):
        resolved, edits, preview = self._prepare(user, patch)
        with self._lock:
            self._expire()
            folder = resolved.snapshot.album_id
            if folder in self._active or len(self._active) >= MAX_ACTIVE_OPERATIONS:
                raise TagError("tags.busy", 409)
            operation = TagOperation(uuid.uuid4().hex, user.id, folder, self.clock(), total=preview.to_api()["trackCount"])
            self._operations[operation.id] = operation
            self._active[folder] = operation.id
            response = replace(operation, warnings=list(operation.warnings))
        threading.Thread(target=self._save, args=(user, operation, resolved, edits, preview), daemon=True).start()
        return response

    def _expire(self):
        now = self.clock()
        completed = sorted((op for op in self._operations.values() if op.id not in self._active.values()),
                           key=lambda op: op.created_at)
        for operation in completed:
            if now - operation.created_at >= OPERATION_SECONDS or len(self._operations) >= MAX_OPERATIONS:
                del self._operations[operation.id]

    def operation(self, user, operation_id):
        self._check_right(user)
        with self._lock:
            self._expire()
            operation = self._operations.get(reference(operation_id))
            if operation is None or operation.owner_id != user.id:
                raise TagError("tags.operation_not_found", 404)
            return replace(operation, warnings=list(operation.warnings))

    def _progress(self, operation, phase, completed, total):
        with self._lock:
            operation.phase, operation.completed, operation.total = phase, completed, total

    def _save(self, user, operation, resolved, edits, preview):
        try:
            self.audio.apply(edits, progress=lambda phase, done, total: self._progress(operation, phase, done, total))
        except Exception as error:
            code = str(error.args[0]) if isinstance(error, AudioTagError) and error.args else "tags.write_failed"
            LOG.warning("Album tag edit failed: %s", type(error).__name__)
            with self._lock:
                operation.state, operation.error, operation.scan = "failed", code, "failed"
                if code == "tags.recovery_required":
                    self._recovery_error = code
                self._active.pop(operation.album_id, None)
            return
        with self._lock:
            operation.state = "saved"
        try:
            self.refresh()
            self._scan_result(operation, "started")
            synchronized = self.scanner.synchronize(user)
            if synchronized is False:
                self._scan_result(operation, "failed", "tags.scan_failed")
            elif synchronized is None:
                self._scan_result(operation, "failed", "tags.scan_unconfirmed")
            else:
                self.refresh()
                if not self._verify_index(user, preview, resolved, operation):
                    self._scan_result(operation, "failed", "tags.scan_unconfirmed")
                else:
                    self._scan_result(operation, "updated")
        except Exception as error:
            LOG.warning("Tags saved; Subsonic refresh could not be confirmed: %s", type(error).__name__)
            self._scan_result(operation, "failed", "tags.scan_unconfirmed")
        finally:
            with self._lock:
                self._active.pop(operation.album_id, None)

    def _scan_result(self, operation, state, warning=""):
        with self._lock:
            operation.scan = state
            if warning and warning not in operation.warnings:
                operation.warnings.append(warning)

    def _verify_index(self, user, preview, resolved, operation):
        old_albums = {item.track.id: item.album_id for item in resolved.files}
        raw_by_id = {}
        fields = {"title": "title", "artist": "artist", "albumArtist": "albumArtist", "album": "album", "year": "year", "genre": "genre",
                  "track": "track", "disc": "discNumber"}
        for identity in {change.id for change in preview.changes}:
            raw = self.subsonic.call(Credentials.of(user), "getSong", [("id", identity)]).get("song") or {}
            if str(raw.get("id") or "") != identity:
                return False
            raw_by_id[identity] = raw
            if str(raw.get("albumId") or "") != old_albums[identity]:
                with self._lock:
                    if "tags.identity_changed" not in operation.warnings:
                        operation.warnings.append("tags.identity_changed")
        verified = True
        for change in preview.changes:
            raw = raw_by_id[change.id]
            if change.field == "albumArtist" and "albumArtist" not in raw:
                with self._lock:
                    if "tags.verification_partial" not in operation.warnings:
                        operation.warnings.append("tags.verification_partial")
            elif str(raw.get(fields[change.field]) or "") != change.after:
                verified = False
        return verified
