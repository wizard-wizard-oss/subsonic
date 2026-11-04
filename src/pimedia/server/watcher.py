"""Surveillance de la bibliothèque : détection des nouveaux albums et préchauffage du cache."""
import json
import threading
import time

from .api import is_ok
from .constants import LIBRARY_ENDPOINTS
from .upstream import NotConfigured
from .folders import as_list


class LibraryCache:
    """Vidage ciblé du cache : seule la « bibliothèque » est concernée,
    jamais les pochettes, biographies ni paroles (qui ne changent pas)."""

    def __init__(self, cache):
        self.cache = cache

    def refresh(self):
        self.cache.invalidate(lambda meta: meta["ep"] in LIBRARY_ENDPOINTS)


class NewestAlbums:
    """Mémorise les derniers albums vus, pour repérer les nouveautés."""

    def __init__(self, path):
        self.path = path

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def save(self, ids):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(ids, f)
        except OSError:
            pass


class LibraryWatcher:
    NEWEST = [("type", "newest"), ("size", "40")]
    WARM_UP = [("getArtists", []), ("getGenres", []), ("getPlaylists", []), ("getStarred2", []),
               ("getAlbumList2", [("type", "newest"), ("size", "14")]),
               ("getAlbumList2", [("type", "newest"), ("size", "40"), ("offset", "0")]),
               ("getAlbumList2", [("type", "alphabeticalByName"), ("size", "40"), ("offset", "0")])]
    FIRST_DELAY = 3
    PERIOD = 1800
    RETRY_PERIOD = 600

    def __init__(self, api, library, newest):
        self.api = api
        self.library = library
        self.newest = newest
        self._started = False

    # --- détection ---
    def check_new(self, force=False):
        """Compare les 40 derniers albums du serveur à ceux déjà vus. Retourne True s'il y a des nouveautés."""
        result = self.api.call_fresh("getAlbumList2", self.NEWEST)
        if not is_ok(result.body):
            return False
        ids = self._ids(result.body)
        seen = self.newest.load()
        changed = seen is not None and any(i not in seen for i in ids)
        self.newest.save(ids)
        if changed or force:
            self.library.refresh()
        return changed

    @staticmethod
    def _ids(body):
        albums = json.loads(body)["subsonic-response"].get("albumList2", {}).get("album")
        return [a.get("id") for a in as_list(albums)]

    # --- préchauffage ---
    def warm_up(self):
        """Détection + préchauffage, une fois, au nom de l'utilisateur courant. Retourne False en cas d'échec."""
        failed = False
        try:
            self.check_new()
        except NotConfigured:
            raise
        except Exception:
            failed = True
        for endpoint, params in self.WARM_UP:
            try:
                self.api.call(endpoint, params)
            except NotConfigured:
                raise
            except Exception:
                failed = True
        return not failed

    def run_forever(self):
        """Boucle de fond : préchauffe le cache et détecte les nouveaux albums."""
        time.sleep(self.FIRST_DELAY)
        while True:
            try:
                ok = self.warm_up()
            except NotConfigured:
                return
            time.sleep(self.PERIOD if ok else self.RETRY_PERIOD)

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self.run_forever, daemon=True).start()
