"""Lecture ciblée et écriture des tags audio, sans catalogue parallèle ni renommage.

Une préparation complète précède la publication. Les originaux restent dans un dossier technique
hors de la musique scannée ; un manifeste sans valeurs de tags permet de reprendre un lot interrompu.
Formats : formats.py ; chemins et copies : files.py ; manifeste et reprise : journal.py.
"""
import os
import uuid
from pathlib import Path

import mutagen

from . import files, formats
from .entities import AudioFileEdit, AudioFileSnapshot, AudioTagError
from .formats import FIELDS, SUPPORTED_FORMATS, validate_changes  # noqa: F401  (interface publique)
from .journal import MAX_BACKUP_OPERATIONS, Journal  # noqa: F401


class AudioTags:
    """Écrivain unique, lots sérialisés, contrôles de concurrence et récupération conservatrice."""
    # Étapes de fichiers remplaçables une à une (les tests y simulent des pannes).
    _copy = staticmethod(files.copy)
    _sync = staticmethod(files.sync)
    _sync_directory = staticmethod(files.sync_directory)

    def __init__(self, music_dir, backup_dir):
        self.backup_dir = os.path.realpath(backup_dir)
        self.journal = Journal(os.path.realpath(music_dir) if music_dir else "", self.backup_dir, self._path)

    @property
    def music_dir(self):
        """Racine de la musique, partagée avec le journal (qui ne reprend que les lots de cette racine)."""
        return self.journal.music_dir

    @music_dir.setter
    def music_dir(self, value):
        self.journal.music_dir = value

    def _path(self, relative):
        return files.safe_path(self.music_dir, relative)

    def inspect(self, relative_path):
        path = self._path(relative_path)
        try:
            revision = files.revision(path)
            kind, document = formats.load(path)
            tags = formats.read(kind, document)
            editable = os.access(path, os.W_OK) and os.access(os.path.dirname(path), os.W_OK | os.X_OK)
            editable = editable and formats.is_supported_id3(kind, document)
            if files.revision(path) != revision:
                raise AudioTagError("tags.conflict")
            return AudioFileSnapshot(relative_path, revision, kind, editable, "" if editable else "tags.not_writable", tags)
        except AudioTagError as error:
            if str(error) != "tags.unsupported_format":
                raise
            return self._unreadable(relative_path, path, str(error))
        except (mutagen.MutagenError, ValueError, OSError):
            return self._unreadable(relative_path, path, "tags.unreadable_file")

    @staticmethod
    def _unreadable(relative_path, path, reason):
        return AudioFileSnapshot(relative_path, files.revision(path), Path(path).suffix.lstrip(".").lower(),
                                 False, reason, dict.fromkeys(FIELDS, ""))

    def _rollback(self, operation, manifest):
        self.journal.rollback(operation, manifest)

    def recover(self):
        try:
            with self.journal.exclusive():
                self.journal.recover()
        except AudioTagError:
            raise
        except OSError:
            raise AudioTagError("tags.backup_failed") from None

    def apply(self, edits, progress=None):
        edits = tuple(edits)
        if not edits or len({edit.relative_path for edit in edits}) != len(edits):
            raise AudioTagError("tags.invalid_changes")
        edits = tuple(AudioFileEdit(edit.relative_path, edit.expected_revision, validate_changes(edit.changes))
                      for edit in edits)
        try:
            with self.journal.exclusive():
                self.journal.recover()
                self._apply(edits, progress or (lambda *step: None))
        except AudioTagError:
            raise
        except (OSError, mutagen.MutagenError, ValueError):
            raise AudioTagError("tags.write_failed") from None

    def _apply(self, edits, progress):
        progress("preparing", 0, len(edits))
        snapshots = tuple(self.inspect(edit.relative_path) for edit in edits)
        if any(not snapshot.editable for snapshot in snapshots):
            raise AudioTagError(next(snapshot.reason for snapshot in snapshots if not snapshot.editable))
        if any(edit.expected_revision != snapshot.revision for edit, snapshot in zip(edits, snapshots)):
            raise AudioTagError("tags.conflict")
        paths = tuple(self._path(edit.relative_path) for edit in edits)
        files.check_space(self.music_dir, self.backup_dir, paths)
        operation = os.path.join(self.backup_dir, uuid.uuid4().hex)
        os.mkdir(operation, mode=0o700)
        manifest = {"version": 1, "root": self.music_dir, "state": "preparing", "entries": []}
        self.journal.write(operation, manifest)
        try:
            self._prepare(operation, manifest, edits, paths, progress)
            self._publish(operation, manifest, edits, progress)
        except BaseException:
            self._rollback(operation, manifest)
            raise
        finally:
            self.journal.cleanup_temporaries(manifest)
        self.journal.prune()

    def _prepare(self, operation, manifest, edits, paths, progress):
        """Original sauvegardé puis copie modifiée et relue, à côté de chaque fichier ; rien n'est encore publié."""
        for index, (edit, path) in enumerate(zip(edits, paths)):
            entry = {"relative": edit.relative_path, "original_revision": edit.expected_revision,
                     "backup": str(index) + ".original"}
            manifest["entries"].append(entry)
            backup = os.path.join(operation, entry["backup"])
            self._copy(path, backup)
            self._sync(backup)
            entry["original_digest"] = files.digest(backup)
            temporary = files.temporary(path)
            entry["temporary"] = os.path.basename(temporary)
            self.journal.write(operation, manifest)
            self._copy(backup, temporary)
            formats.write(temporary, edit.changes)
            actual = formats.read(*formats.load(temporary))
            if any(actual[key] != value for key, value in edit.changes.items()):
                raise AudioTagError("tags.verification_failed")
            self._sync(temporary)
            entry["prepared_identity"] = files.identity(temporary)
            entry["prepared_digest"] = files.digest(temporary)
            self.journal.write(operation, manifest)
            progress("preparing", index + 1, len(edits))
        if any(files.revision(self._path(edit.relative_path)) != edit.expected_revision for edit in edits):
            raise AudioTagError("tags.conflict")

    def _publish(self, operation, manifest, edits, progress):
        manifest["state"] = "publishing"
        self.journal.write(operation, manifest)
        progress("publishing", 0, len(edits))
        for index, (edit, entry) in enumerate(zip(edits, manifest["entries"])):
            path = self._path(edit.relative_path)
            if files.revision(path) != edit.expected_revision:
                raise AudioTagError("tags.conflict")
            os.replace(os.path.join(os.path.dirname(path), entry["temporary"]), path)
            self._sync_directory(os.path.dirname(path))
            entry["published_revision"] = files.revision(path)
            self.journal.write(operation, manifest)
            progress("publishing", index + 1, len(edits))
        manifest["state"] = "committed"
        self.journal.write(operation, manifest)
