"""Étoiles 1 à 5 des albums, lues et écrites dans Subsonic avec le compte de la personne : rien n'est gardé ici.

Dans Subsonic d'origine (API 1.16.1), les notes sont posées sur les dossiers, pas sur les albums ID3 :
setRating attend l'identifiant d'un dossier, et seuls les dossiers (getMusicDirectory, getAlbumList) donnent
userRating (la note de la personne) et averageRating (la moyenne de tous les comptes). Le dossier d'un album ID3
est le « parent » de ses titres ; pour un album en plusieurs disques (CD1/, CD2/), le dossier qui les contient."""
from concurrent.futures import ThreadPoolExecutor

from .entities import RatingSummary
from .library import TtlCache, as_list, text
from .subsonic import Credentials

PARALLEL = 4            # appels Subsonic simultanés : on ménage le serveur


class InvalidRating(ValueError):
    pass


class Ratings:
    def __init__(self, subsonic, cache=None):
        self.subsonic = subsonic
        self.cache = cache or TtlCache(600)

    def _call(self, user, endpoint, params=()):
        return self.subsonic.call(Credentials.of(user), endpoint, params)

    def _directory(self, user, folder_id):
        return self._call(user, "getMusicDirectory", [("id", folder_id)]).get("directory") or {}

    def folder_of(self, user, album_id):
        """Dossier Subsonic d'un album ID3 (ne change pas : gardé en cache)."""
        def find():
            songs = as_list((self._call(user, "getAlbum", [("id", album_id)]).get("album") or {}).get("song"))
            parents = list(dict.fromkeys(s.get("parent") for s in songs if s.get("parent")))
            if len(parents) > 1:                  # un dossier par disque : on note le dossier qui les contient
                return self._directory(user, parents[0]).get("parent") or parents[0]
            return parents[0] if parents else ""
        return self.cache.get(("folder", album_id), find)

    def summary(self, user, album_id):
        folder = self.folder_of(user, album_id)
        if not folder:
            return RatingSummary(album_id)
        directory = self._directory(user, folder)
        return RatingSummary(album_id, int(directory.get("userRating") or 0), float(directory.get("averageRating") or 0))

    def rate(self, user, album_id, rating):
        """rating : 1 à 5, ou 0 pour retirer sa note. Renvoie la note relue dans Subsonic (moyenne à jour)."""
        if not isinstance(rating, int) or isinstance(rating, bool) or not 0 <= rating <= 5 or not album_id:
            raise InvalidRating(rating)
        folder = self.folder_of(user, album_id)
        if not folder:
            raise InvalidRating(album_id)
        self._call(user, "setRating", [("id", folder), ("rating", rating)])
        self.cache.forget("top")
        return self.summary(user, album_id)

    def top(self, user, limit=12, offset=0):
        """Albums les mieux notés de Subsonic (moyenne de tous les comptes), en cartes d'albums ID3."""
        def load():
            params = [("type", "highest"), ("size", limit), ("offset", offset)]
            folders = as_list((self._call(user, "getAlbumList", params).get("albumList") or {}).get("album"))
            with ThreadPoolExecutor(PARALLEL) as pool:
                return [card for card in pool.map(lambda folder: self._top_card(user, folder), folders) if card]
        return self.cache.get(("top", user.username, limit, offset), load)

    def _top_card(self, user, folder):
        """Carte d'album ID3 pour un dossier noté : l'identifiant ID3 vient du premier titre du dossier."""
        song = self._first_song(user, folder.get("id"))
        if not song or not song.get("albumId"):
            return None
        return {"id": song["albumId"], "name": text(folder.get("album") or folder.get("title"), "?"),
                "artist": text(folder.get("artist")), "artistId": song.get("artistId", ""), "year": folder.get("year"),
                "coverId": folder.get("coverArt", ""), "songCount": 0, "starred": bool(folder.get("starred")),
                "plays": int(folder.get("playCount") or 0),
                "rating": RatingSummary(song["albumId"], int(folder.get("userRating") or 0),
                                        float(folder.get("averageRating") or 0)).to_api()}

    def _first_song(self, user, folder_id, depth=2):
        """Premier titre d'un dossier, en descendant dans les sous-dossiers de disques si besoin."""
        children = as_list(self._directory(user, folder_id).get("child"))
        song = next((c for c in children if not c.get("isDir")), None)
        if song or depth == 0:
            return song
        sub = next((c for c in children if c.get("isDir")), None)
        return self._first_song(user, sub["id"], depth - 1) if sub else None
