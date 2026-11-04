"""Pages artiste et album tirées des DOSSIERS de la bibliothèque (getMusicDirectory), pas des tags ID3 : un dossier par
artiste (Artiste/Album/titre, voir layout.py), donc un seul « Dälek » même si les tags disent aussi « Dalek ».

Les identifiants de dossier sont préfixés « f » (« f123 ») : dans Subsonic d'origine, dossiers et éléments ID3 ont des
numéros indépendants qui peuvent se croiser. Un identifiant ID3 (lien venu d'une liste d'albums, d'une recherche, d'un
titre) est accepté aussi : il est ramené à son dossier. Ce qui reste attaché à l'ID3 dans Subsonic le reste : l'album
garde son identifiant ID3 (commentaires, favori, note, téléchargement, partage), l'artiste donne le sien (« id3Id ») pour
la radio, le mix et les artistes proches."""
from concurrent.futures import ThreadPoolExecutor

from .library import TtlCache, song_row, text, visible
from .subsonic import Credentials, SubsonicError, SubsonicUnreachable

PREFIX = "f"
NOT_FOUND = 70
PARALLEL = 4            # appels Subsonic simultanés pour les pochettes à chercher plus bas : on ménage le serveur


class FolderNotFound(LookupError):
    pass


def is_folder(item_id):
    return item_id.startswith(PREFIX)


def folder_ref(folder_id):
    return PREFIX + str(folder_id)


class Folders:
    def __init__(self, subsonic, library, ratings, cache=None):
        self.subsonic = subsonic
        self.library = library
        self.ratings = ratings
        self.cache = cache or TtlCache(600)

    def _call(self, user, endpoint, params=()):
        return self.subsonic.call(Credentials.of(user), endpoint, params)

    def _directory(self, user, folder_id):
        try:
            return self._call(user, "getMusicDirectory", [("id", folder_id)]).get("directory") or {}
        except SubsonicError as error:
            if error.code == NOT_FOUND:
                raise FolderNotFound(folder_id)
            raise

    # --- artiste : le dossier qui contient les albums ---
    def artist(self, user, artist_id):
        folder = artist_id[len(PREFIX):] if is_folder(artist_id) else self._artist_folder(user, artist_id)
        directory = self._directory(user, folder)
        albums = [self._album_card(child, directory, folder) for child in visible(directory.get("child"))
                  if child.get("isDir")]
        albums.sort(key=lambda a: (a["year"] or 0, a["name"].casefold()))
        missing = [a for a in albums if not a["coverId"]]
        if missing:
            with ThreadPoolExecutor(PARALLEL) as pool:
                covers = pool.map(lambda a: self._cover_below(user, a["id"][len(PREFIX):]), missing)
                for album, cover in zip(missing, covers):
                    album["coverId"] = cover
        song = self._first_song(user, folder, depth=2)
        return {"id": folder_ref(folder), "name": text(directory.get("name"), "?"),
                "id3Id": (song or {}).get("artistId", "") if is_folder(artist_id) else artist_id,
                "coverId": albums[0]["coverId"] if albums else "", "starred": bool(directory.get("starred")),
                "albums": albums}

    @staticmethod
    def _album_card(child, artist_dir, artist_folder):
        return {"id": folder_ref(child["id"]), "name": text(child.get("title") or child.get("album"), "?"),
                "artist": text(artist_dir.get("name")), "artistId": folder_ref(artist_folder), "year": child.get("year"),
                "coverId": child.get("coverArt", ""), "songCount": 0, "starred": bool(child.get("starred")),
                "plays": int(child.get("playCount") or 0), "comments": 0}

    def _artist_folder(self, user, id3_artist):
        """Dossier d'un artiste ID3 : celui qui contient le dossier de son premier album."""
        def find():
            albums = visible((self._call(user, "getArtist", [("id", id3_artist)]).get("artist") or {}).get("album"))
            album_folder = self.ratings.folder_of(user, albums[0]["id"]) if albums else ""
            parent = self._directory(user, album_folder).get("parent") if album_folder else ""
            if not parent:
                raise FolderNotFound(id3_artist)
            return str(parent)
        return self.cache.get(("artist-folder", id3_artist), find)

    # --- album : le dossier qui contient les titres (et les dossiers de disques) ---
    def _album_folder(self, user, album_id):
        folder = album_id[len(PREFIX):] if is_folder(album_id) else self.ratings.folder_of(user, album_id)
        if not folder:
            raise FolderNotFound(album_id)
        return folder

    def album_path(self, user, album_id):
        """Chemin du dossier de l'album dans la musique de Subsonic (« Artiste/Album »), lu sur le chemin de ses titres ou de
        ses dossiers de disques ; vide si Subsonic n'en donne aucun."""
        children = visible(self._directory(user, self._album_folder(user, album_id)).get("child"))
        paths = [text(c.get("path")).replace("\\", "/") for c in children]
        return next((path.rsplit("/", 1)[0] for path in paths if "/" in path), "")

    def album(self, user, album_id):
        folder = self._album_folder(user, album_id)
        directory = self._directory(user, folder)
        songs = self._songs(user, directory)
        id3_album = next((s["albumId"] for s in songs if s["albumId"]), "") if is_folder(album_id) else album_id
        if not id3_album:
            raise FolderNotFound(album_id)
        album = self.library.album(user, id3_album)          # note, favori, écoutes, commentaires : côté ID3
        parent = str(directory.get("parent") or "")
        album.update(folderId=folder_ref(folder), name=text(directory.get("name"), album["name"]), songs=songs,
                     duration=sum(s["duration"] or 0 for s in songs))
        if parent:
            album.update(artist=self._name(user, parent) or album["artist"], artistId=folder_ref(parent))
        if not album.get("coverId"):
            album["coverId"] = self._cover_below(user, folder)
        return album

    def _cover_below(self, user, folder_id, depth=2):
        """Pochette d'un dossier d'album qui n'en a pas : celle de son premier sous-dossier qui en a une. Beaucoup
        d'albums en plusieurs disques (« Disc 1 », « Vol. 1 ») n'ont leur image que là, et Subsonic ne la remonte pas
        (328 albums sur music.foos.fr, dont la plupart des compilations). Vide si rien ; gardée 10 minutes."""
        def find(folder, depth):
            try:
                children = visible(self._directory(user, folder).get("child"))
            except (FolderNotFound, SubsonicError, SubsonicUnreachable):
                return ""
            subs = sorted((c for c in children if c.get("isDir")), key=lambda c: text(c.get("title")).casefold())
            found = next((s["coverArt"] for s in subs if s.get("coverArt")), "")
            for sub in subs if not found and depth > 1 else ():
                found = find(sub["id"], depth - 1)
                if found:
                    break
            return found
        return self.cache.get(("cover-below", str(folder_id)), lambda: find(folder_id, depth))

    def _songs(self, user, directory):
        """Titres du dossier, puis ceux de chaque sous-dossier (disques), dans l'ordre des noms."""
        children = visible(directory.get("child"))
        songs = [song_row(c) for c in children if not c.get("isDir")]
        for sub in sorted((c for c in children if c.get("isDir")), key=lambda c: text(c.get("title")).casefold()):
            songs += [song_row(c) for c in visible(self._directory(user, sub["id"]).get("child")) if not c.get("isDir")]
        return songs

    def _name(self, user, folder_id):
        def load():
            try:
                return text(self._directory(user, folder_id).get("name"))
            except FolderNotFound:
                return ""                              # dossier racine de la musique : pas un artiste
        return self.cache.get(("name", folder_id), load)

    def _first_song(self, user, folder_id, depth):
        """Premier titre sous un dossier, en descendant d'au plus depth niveaux (artiste → album → disque)."""
        children = visible(self._directory(user, folder_id).get("child"))
        song = next((c for c in children if not c.get("isDir")), None)
        if song or depth == 0:
            return song
        for sub in (c for c in children if c.get("isDir")):
            found = self._first_song(user, sub["id"], depth - 1)
            if found:
                return found
        return None
