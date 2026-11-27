"""Fichiers audio sous la racine de la musique : chemin sûr (ni lien, ni sortie de la racine), empreintes,
copies, synchronisation sur disque et espace libre."""
import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import PurePosixPath

from .entities import AudioTagError

SPACE_MARGIN = 65536


def safe_path(music_dir, relative):
    """Chemin réel d'un fichier ordinaire de la musique (un seul lien physique, aucun lien symbolique)."""
    if not music_dir or not os.path.isdir(music_dir):
        raise AudioTagError("tags.off")
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        raise AudioTagError("tags.unsafe_path")
    if PurePosixPath(relative).is_absolute() or any(part in (".", "..") for part in relative.split("/")):
        raise AudioTagError("tags.unsafe_path")
    path = music_dir
    try:
        for part in PurePosixPath(relative).parts:
            path = os.path.join(path, part)
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode):
                raise AudioTagError("tags.unsafe_path")
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise AudioTagError("tags.unsafe_path")
    except OSError:
        raise AudioTagError("tags.file_unavailable") from None
    if os.path.commonpath((music_dir, os.path.realpath(path))) != music_dir:
        raise AudioTagError("tags.unsafe_path")
    return path


def identity(path):
    info = os.stat(path, follow_symlinks=False)
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid]


def revision(path):
    info = os.stat(path, follow_symlinks=False)
    value = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
             stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid, info.st_ctime_ns)
    return hashlib.sha256(repr(value).encode("ascii")).hexdigest()


def digest(path):
    found = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            found.update(chunk)
    return found.hexdigest()


def copy(source, destination):
    shutil.copy2(source, destination)
    original, copied = os.stat(source), os.stat(destination)
    if (original.st_uid, original.st_gid) != (copied.st_uid, copied.st_gid):
        os.chown(destination, original.st_uid, original.st_gid)


def sync(path):
    with open(path, "rb") as item:
        os.fsync(item.fileno())


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def temporary(path):
    descriptor, name = tempfile.mkstemp(prefix=".pimedia-tags-", suffix=".part", dir=os.path.dirname(path))
    os.close(descriptor)
    return name


def check_space(music_dir, backup_dir, paths):
    required = sum(os.path.getsize(path) for path in paths)
    same_disk = os.stat(music_dir).st_dev == os.stat(backup_dir).st_dev
    if shutil.disk_usage(backup_dir).free < required * (2 if same_disk else 1) + SPACE_MARGIN:
        raise AudioTagError("tags.no_space")
    if not same_disk and shutil.disk_usage(music_dir).free < required + SPACE_MARGIN:
        raise AudioTagError("tags.no_space")
