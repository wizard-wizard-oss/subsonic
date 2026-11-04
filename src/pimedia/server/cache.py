"""Caches sur disque : réponses JSON de Subsonic et pochettes."""
import json
import os
import shutil
import threading
import time


class CacheEntry:
    """Une réponse mise en cache : métadonnées (échéance, type, utilisateur…) et corps."""

    def __init__(self, meta, body):
        self.meta = meta
        self.body = body

    @property
    def ctype(self):
        return self.meta["ctype"]

    def expired(self, now=None):
        return self.meta["exp"] < (now or time.time())


class JsonCache:
    """Réponses JSON : un index en mémoire, les corps sur disque (les plus récents aussi en mémoire)."""

    EXPIRED_KEEP_SECONDS = 30 * 86400      # une entrée périmée depuis plus longtemps est supprimée au démarrage

    def __init__(self, directory, max_entries=200000, max_memory=300):
        self.directory = directory
        self.max_entries = max_entries
        self.max_memory = max_memory
        self._index = {}                   # clé -> métadonnées
        self._memory = {}                  # clé -> CacheEntry
        self._lock = threading.Lock()

    # --- chemins ---
    def _paths(self, key):
        base = os.path.join(self.directory, key)
        return base + ".json", base + ".bin"

    def _remove_files(self, key):
        for path in self._paths(key):
            try:
                os.remove(path)
            except OSError:
                pass

    # --- démarrage ---
    def load(self):
        """Reconstruit l'index à partir des fichiers du disque."""
        os.makedirs(self.directory, exist_ok=True)
        now = time.time()
        for name in os.listdir(self.directory):
            if name.endswith(".json"):
                self._load_one(name[:-5], now)

    def _load_one(self, key, now):
        try:
            with open(self._paths(key)[0], encoding="utf-8") as f:
                meta = json.load(f)
            if meta["exp"] < now - self.EXPIRED_KEEP_SECONDS:
                self._remove_files(key)
            else:
                self._index[key] = meta
        except (OSError, ValueError, KeyError):
            self._remove_files(key)

    # --- lecture / écriture ---
    def get(self, key, allow_stale=False):
        with self._lock:
            entry = self._memory.get(key) or self._read_from_disk(key)
        if entry is None or (entry.expired() and not allow_stale):
            return None
        return entry

    def _read_from_disk(self, key):
        meta = self._index.get(key)
        if meta is None:
            return None
        try:
            with open(self._paths(key)[1], "rb") as f:
                entry = CacheEntry(meta, f.read())
        except OSError:
            self._index.pop(key, None)
            return None
        self._memory[key] = entry
        return entry

    def put(self, key, endpoint, params, ttl, ctype, body):
        meta = {"ep": endpoint, "q": dict(params), "exp": time.time() + ttl, "ctype": ctype}
        if not self._write_files(key, meta, body):
            return
        with self._lock:
            self._index[key] = meta
            self._memory[key] = CacheEntry(meta, body)
            self._trim()

    def _write_files(self, key, meta, body):
        meta_path, body_path = self._paths(key)
        try:
            for path, data, mode in ((body_path, body, "wb"), (meta_path, json.dumps(meta), "w")):
                tmp = path + ".tmp"
                with open(tmp, mode) as f:
                    f.write(data)
                os.replace(tmp, path)
        except OSError:
            return False
        return True

    def _trim(self):
        while len(self._memory) > self.max_memory:
            self._memory.pop(next(iter(self._memory)))
        if len(self._index) > self.max_entries:
            oldest = sorted(self._index, key=lambda k: self._index[k]["exp"])[:500]
            for key in oldest:
                self._drop(key)

    def _drop(self, key):
        self._index.pop(key, None)
        self._memory.pop(key, None)
        self._remove_files(key)

    # --- invalidation ---
    def invalidate(self, predicate):
        """Supprime toutes les entrées dont les métadonnées satisfont predicate."""
        with self._lock:
            for key in [k for k, meta in self._index.items() if predicate(meta)]:
                self._drop(key)

    def clear(self):
        with self._lock:
            self._index.clear()
            self._memory.clear()
        shutil.rmtree(self.directory, ignore_errors=True)
        os.makedirs(self.directory, exist_ok=True)


class CoverCache:
    """Pochettes : un fichier image et un fichier de type par pochette."""

    def __init__(self, directory, ttl):
        self.directory = directory
        self.ttl = ttl
        os.makedirs(directory, exist_ok=True)

    def _paths(self, key):
        return os.path.join(self.directory, key + ".img"), os.path.join(self.directory, key + ".ct")

    def get(self, key, allow_stale=False):
        """Retourne (type, octets) ou None."""
        image, ctype_file = self._paths(key)
        if not os.path.exists(image):
            return None
        if not allow_stale and time.time() - os.path.getmtime(image) >= self.ttl:
            return None
        with open(image, "rb") as f:
            body = f.read()
        try:
            with open(ctype_file, encoding="utf-8") as f:
                ctype = f.read()
        except OSError:
            ctype = "image/jpeg"
        return ctype, body

    def put(self, key, ctype, body):
        image, ctype_file = self._paths(key)
        try:
            with open(image, "wb") as f:
                f.write(body)
            with open(ctype_file, "w", encoding="utf-8") as f:
                f.write(ctype)
        except OSError:
            pass

    def clear(self):
        shutil.rmtree(self.directory, ignore_errors=True)
        os.makedirs(self.directory, exist_ok=True)
