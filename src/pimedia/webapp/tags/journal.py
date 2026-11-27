"""Journal des lots de tags : originaux et manifeste (sans valeurs de tags) hors de la musique scannée, restauration
conservatrice après une panne et purge des lots terminés."""
import contextlib
import fcntl
import json
import os
import shutil
import stat
import threading
import time
from pathlib import Path

from . import files
from .entities import AudioTagError

BACKUP_RETENTION_SECONDS = 86400
MAX_BACKUP_OPERATIONS = 8
MAX_BACKUP_BYTES = 4 * 1024 ** 3


class Journal:
    def __init__(self, music_dir, backup_dir, resolve):
        """resolve(chemin relatif) -> chemin sûr dans la musique (AudioTags.path)."""
        self.music_dir, self.backup_dir, self.resolve = music_dir, backup_dir, resolve
        self.lock = threading.RLock()

    @contextlib.contextmanager
    def exclusive(self):
        if self.music_dir and os.path.commonpath((self.music_dir, self.backup_dir)) == self.music_dir:
            raise AudioTagError("tags.unsafe_backup")
        os.makedirs(self.backup_dir, mode=0o700, exist_ok=True)
        with self.lock, open(os.path.join(self.backup_dir, ".lock"), "a+b") as lockfile:
            fcntl.flock(lockfile, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lockfile, fcntl.LOCK_UN)

    @staticmethod
    def write(operation, data):
        path = os.path.join(operation, "manifest.json")
        part = path + ".part"
        with open(part, "w", encoding="utf-8") as target:
            json.dump(data, target, ensure_ascii=False)
            target.flush()
            os.fsync(target.fileno())
        os.replace(part, path)
        files.sync_directory(operation)

    @staticmethod
    def matches_publication(path, entry):
        if entry.get("published_revision"):
            return files.revision(path) == entry["published_revision"]
        return files.identity(path) == entry.get("prepared_identity") and files.digest(path) == entry.get("prepared_digest")

    @staticmethod
    def backup_path(operation, entry):
        name = entry.get("backup", "")
        if not isinstance(name, str) or not name.endswith(".original") or not name[:-9].isdigit():
            raise AudioTagError("tags.recovery_required")
        path = os.path.join(operation, name)
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise AudioTagError("tags.recovery_required")
        return path

    def rollback(self, operation, manifest):
        if manifest["state"] == "preparing":
            manifest["state"] = "rolled_back"
            self.write(operation, manifest)
            return
        failed = False
        for entry in reversed(manifest["entries"]):
            failed = not self._restore(operation, manifest, entry) or failed
        manifest["state"] = "needs_recovery" if failed else "rolled_back"
        self.write(operation, manifest)
        if failed:
            raise AudioTagError("tags.recovery_required")

    def _restore(self, operation, manifest, entry):
        """Remet l'original d'un fichier publié par ce lot ; False si l'état du fichier ne permet pas de conclure."""
        temporary = ""
        try:
            path = self.resolve(entry["relative"])
            if files.revision(path) == entry["original_revision"] or entry.get("restored"):
                return True
            if self._never_published(path, entry):
                return True               # jamais remplacé par ce lot : un changement venu d'ailleurs n'est pas à défaire
            if entry.get("original_digest") and files.digest(path) == entry["original_digest"]:
                entry["restored"] = True       # Une panne peut avoir précédé l'écriture de l'accusé de restauration.
                return True
            backup = self.backup_path(operation, entry)
            if not self.matches_publication(path, entry) or files.digest(backup) != entry["original_digest"]:
                return False
            temporary = files.temporary(path)
            files.copy(backup, temporary)
            files.sync(temporary)
            if not self.matches_publication(path, entry):
                return False
            os.replace(temporary, path)
            files.sync_directory(os.path.dirname(path))
            entry["restored"] = True
            self.write(operation, manifest)
            return True
        except (OSError, ValueError, KeyError):
            return False
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _never_published(path, entry):
        """La copie préparée attend encore à côté du fichier : la publication de cette entrée n'a pas eu lieu."""
        name = entry.get("temporary", "")
        return not entry.get("published_revision") and bool(name) and \
            os.path.isfile(os.path.join(os.path.dirname(path), name))

    def _operations(self):
        return [operation for operation in Path(self.backup_dir).iterdir()
                if operation.is_dir() and not operation.is_symlink() and len(operation.name) == 32]

    def recover(self):
        for operation in self._operations():
            try:
                if not (operation / "manifest.json").exists():
                    shutil.rmtree(operation)   # Aucun fichier musical n'est publié avant le premier manifeste complet.
                    continue
                if (operation / "manifest.json").is_symlink():
                    raise AudioTagError("tags.recovery_required")
                with open(operation / "manifest.json", encoding="utf-8") as source:
                    manifest = json.load(source)
                if manifest.get("version") != 1 or manifest.get("root") != self.music_dir:
                    continue
                if manifest.get("state") not in ("committed", "rolled_back"):
                    self.rollback(str(operation), manifest)
                self.cleanup_temporaries(manifest)
            except (OSError, ValueError, KeyError, TypeError):
                raise AudioTagError("tags.recovery_required") from None
        self.prune()

    def cleanup_temporaries(self, manifest):
        for entry in manifest["entries"]:
            name = entry.get("temporary", "")
            if name and os.path.basename(name) == name and name.startswith(".pimedia-tags-") and name.endswith(".part"):
                try:
                    path = os.path.join(os.path.dirname(self.resolve(entry["relative"])), name)
                    if os.path.isfile(path) and not os.path.islink(path):
                        os.unlink(path)
                except (OSError, AudioTagError):
                    pass

    def prune(self):
        finished = []
        for operation in self._operations():
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
                shutil.rmtree(operation, ignore_errors=True)
