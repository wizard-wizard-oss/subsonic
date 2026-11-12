"""Attribution des albums : le chemin Subsonic confirme toujours le dossier reçu, jamais les tags seuls."""
from concurrent.futures import ThreadPoolExecutor
import posixpath
import unicodedata

from .layout import is_disc
from .library import TtlCache, as_list, text
from .subsonic import Credentials, SubsonicError, SubsonicUnreachable


def path_key(path):
    return unicodedata.normalize("NFC", path.replace("\\", "/").strip("/"))


def album_path(raw):
    for song in as_list(raw.get("song")):
        path = text(song.get("path"))
        if not path:
            continue
        folder = posixpath.dirname(path_key(path))
        if is_disc(posixpath.basename(folder)):
            folder = posixpath.dirname(folder)
        if folder:
            return folder
    return ""


class UploadAttribution:
    def __init__(self, uploads, subsonic):
        self.uploads = uploads
        self.subsonic = subsonic
        self.paths = TtlCache(600)

    def _path(self, user, identity):
        def load():
            raw = self.subsonic.call(Credentials.of(user), "getAlbum", [("id", identity)]).get("album") or {}
            return album_path(raw)
        return self.paths.get((self.uploads.library_key, user.id, identity), load)

    def annotate(self, user, albums):
        origins = {path_key(entry.path): entry for entry in self.uploads.history.origins(self.uploads.library_key)}
        if not origins:
            return

        def resolve(album):
            try:
                return origins.get(path_key(self._path(user, album["id"])))
            except (SubsonicError, SubsonicUnreachable):
                return None                           # l'attribution ne doit pas empêcher d'écouter l'album

        # Listes limitées à l'accueil : quatre lectures simultanées au plus, chemins gardés dix minutes.
        if len(albums) > 1:
            with ThreadPoolExecutor(max_workers=4) as pool:
                found = list(pool.map(resolve, albums))
        else:
            found = [resolve(album) for album in albums]
        for album, origin in zip(albums, found):
            if origin:
                album["uploadedBy"] = origin.to_api()
