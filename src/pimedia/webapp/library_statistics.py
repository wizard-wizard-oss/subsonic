"""Compteurs déjà calculés par Subsonic et enregistrés après son dernier scan.

Le fichier source est monté en lecture seule. Aucun parcours de bibliothèque, appel REST,
expiration ou recalcul : LastScanned décide seul du remplacement du dernier résultat valide.
"""
import os
import threading

from .entities import LibraryStatistics

MAX_PROPERTIES_BYTES = 1024 * 1024
MAX_SCAN_MS = 8_640_000_000_000_000  # limite des dates du navigateur
STATISTICS_KEYS = frozenset(("MediaLibraryStatistics", "LastScanned"))


def parse_statistics(content):
    """Les deux propriétés numériques utiles, jamais les autres réglages (qui contiennent des secrets)."""
    if not content.endswith(("\n", "\r")):
        return None  # Properties.store termine ses lignes : un dernier nombre peut être en cours d'écriture.
    values = {}
    for line in content.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() in STATISTICS_KEYS:
            values[key.strip()] = value.strip()
    counts = values.get("MediaLibraryStatistics", "").split()
    scanned = values.get("LastScanned", "")
    numbers = counts + [scanned]
    if len(counts) != 5 or not all(n.isascii() and n.isdecimal() and len(n) <= 19 for n in numbers):
        return None
    if not 0 < int(scanned) <= MAX_SCAN_MS:
        return None
    return LibraryStatistics(*(int(n) for n in numbers))


class SubsonicStatistics:
    def __init__(self, path):
        self.path = path
        self._signature = None
        self._cached = None
        self._lock = threading.Lock()

    def get(self):
        """Lecture minuscule si le fichier change ; une sauvegarde incomplète garde le dernier scan connu."""
        if not self.path:
            return None
        with self._lock:
            try:
                before = os.stat(self.path)
                signature = (before.st_ino, before.st_size, before.st_mtime_ns)
                if signature == self._signature:
                    return self._cached
                with open(self.path, encoding="iso-8859-1") as source:
                    content = source.read(MAX_PROPERTIES_BYTES + 1)
                after = os.stat(self.path)
                if len(content) > MAX_PROPERTIES_BYTES or signature != (after.st_ino, after.st_size, after.st_mtime_ns):
                    return self._cached
                found = parse_statistics(content)
                if found is None:
                    return self._cached
                self._signature = signature
                if self._cached is None or found.last_scan != self._cached.last_scan:
                    self._cached = found
            except OSError:
                pass
            return self._cached
