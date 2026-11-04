"""Règles de cache : durée de vie de chaque appel et ce qu'il faut vider après une modification."""
from .constants import (FOREVER, LIBRARY_TTL, PLAYLIST_AFFECTED, SHORT_TTL, STAR_AFFECTED,
                        WRITE_ENDPOINTS)


class CachePolicy:
    TTLS = {
        "getArtists": LIBRARY_TTL, "getArtist": LIBRARY_TTL, "getAlbum": LIBRARY_TTL,
        "getGenres": LIBRARY_TTL, "getArtistInfo2": FOREVER, "getTopSongs": FOREVER,
        "getInternetRadioStations": 3600, "getPlaylists": SHORT_TTL, "getPlaylist": SHORT_TTL,
        "getStarred2": SHORT_TTL, "search3": SHORT_TTL,
    }
    RECENT_ALBUM_LISTS = ("recent", "frequent")     # changent à chaque écoute : cache très court

    def ttl_for(self, endpoint, params):
        """Durée de validité en secondes (0 = jamais en cache). params : dict."""
        if endpoint == "getAlbumList2":
            return self._album_list_ttl(params.get("type"))
        return self.TTLS.get(endpoint, 0)

    def _album_list_ttl(self, list_type):
        if list_type == "random":
            return 0
        if list_type in self.RECENT_ALBUM_LISTS:
            return 30
        return LIBRARY_TTL          # « newest » inclus : vidé quand de nouveaux albums sont détectés

    def is_write(self, endpoint):
        return endpoint in WRITE_ENDPOINTS

    def stale_rule(self, endpoint, params):
        """Après une modification, retourne le filtre des entrées de cache devenues fausses (ou None)."""
        if endpoint in ("star", "unstar"):
            return lambda meta: meta["ep"] in STAR_AFFECTED
        if endpoint in ("createPlaylist", "updatePlaylist", "deletePlaylist"):
            return lambda meta: meta["ep"] in PLAYLIST_AFFECTED
        if endpoint == "scrobble" and params.get("submission") == "true":
            return lambda meta: (meta["ep"] == "getAlbumList2"
                                 and meta["q"].get("type") in self.RECENT_ALBUM_LISTS)
        return None
