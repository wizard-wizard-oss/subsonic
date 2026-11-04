#!/usr/bin/env python3
"""Fabrique l'archive à déployer sur le Pi : dist/pi-media-<version>.tar.gz, avec install.sh (Pi neuf),
deploy.sh (mises à jour) et migration.sh à côté.

Usage : python3 deploy/pi/build_archive.py [version]      (par défaut : date et heure, ex. 2026.10.25-1530)
Contenu : le code et les fichiers nécessaires, jamais de données ni de secrets (.env, *.db, config.json)."""
import io
import os
import shutil
import sys
import tarfile
import time

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.join(PROJECT, "deploy", "pi")
# (chemin dans le projet, chemin dans l'archive) : sur le Pi, tout est à plat dans le dossier du code
INCLUDED = (("src/pimedia", "pimedia"), ("src/web", "web"), ("src/i18n", "i18n"), ("src/themes", "themes"),
            ("src/launcher.py", "launcher.py"), ("src/launcher_classic.py", "launcher_classic.py"),
            ("src/subsonic-web.py", "subsonic-web.py"), ("deploy/pi", "deploy"), ("deploy/pi/env.example", ".env.example"))
EXCLUDED_DIRS = {"__pycache__", "dist", "webapp"}       # webapp : édition PC, livrée à part
EXCLUDED_SUFFIXES = (".pyc", ".db", ".db-wal", ".db-shm", ".importe")
EXCLUDED_NAMES = {".env", "config.json", "env.example"}    # env.example : livré en .env.example


def wanted(path):
    name = os.path.basename(path)
    return name not in EXCLUDED_NAMES and not name.endswith(EXCLUDED_SUFFIXES)


def files():
    """(fichier du projet, nom dans l'archive)"""
    for source, target in INCLUDED:
        full = os.path.join(PROJECT, source)
        if os.path.isfile(full):
            yield full, target
            continue
        for directory, subdirs, names in os.walk(full):
            subdirs[:] = sorted(d for d in subdirs if d not in EXCLUDED_DIRS)
            for name in sorted(names):
                path = os.path.join(directory, name)
                if wanted(path):
                    yield path, os.path.join(target, os.path.relpath(path, full))


def build(version):
    dist = os.path.join(PROJECT, "dist")
    os.makedirs(dist, exist_ok=True)
    archive = os.path.join(dist, "pi-media-%s.tar.gz" % version)
    with tarfile.open(archive, "w:gz") as tar:
        for path, name in files():
            tar.add(path, arcname=name, recursive=False)
        data = (version + "\n").encode()
        info = tarfile.TarInfo("VERSION")
        info.size, info.mtime, info.mode = len(data), int(time.time()), 0o644
        tar.addfile(info, io.BytesIO(data))
    shutil.copy(os.path.join(HERE, "deploy.sh"), os.path.join(dist, "deploy.sh"))
    shutil.copy(os.path.join(HERE, "bin", "migration.sh"), os.path.join(dist, "migration.sh"))
    shutil.copy(os.path.join(HERE, "install.sh"), os.path.join(dist, "install.sh"))
    return archive


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y.%m.%d-%H%M")))
