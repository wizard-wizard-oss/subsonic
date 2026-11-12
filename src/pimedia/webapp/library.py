"""Bibliothèque Subsonic (API ID3 ; pages artiste et album : voir folders.py) vue par l'utilisateur connecté : notes et écoutes viennent de Subsonic,
les commentaires de la base du site."""
import threading
import time
from datetime import date

from .entities import album_topic
from .subsonic import Credentials, SubsonicError, SubsonicUnreachable


class TtlCache:
    """Petit cache mémoire : la liste des artistes ne change pas à chaque clic."""

    def __init__(self, seconds, clock=time.time):
        self.seconds, self.clock = seconds, clock
        self._items = {}
        self._lock = threading.Lock()

    def get(self, key, compute):
        now = self.clock()
        with self._lock:
            hit = self._items.get(key)
            if hit and now - hit[0] < self.seconds:
                return hit[1]
        value = compute()
        with self._lock:
            self._items[key] = (now, value)
            if len(self._items) > 2000:
                self._items.clear()
        return value

    def forget(self, prefix):
        with self._lock:
            for key in [k for k in self._items if k[0] == prefix]:
                del self._items[key]


def as_list(value):
    """Subsonic renvoie une liste, un seul élément, ou rien (absent, ou {} : liste vide, ex. sans Last.fm)."""
    if not value:
        return []
    return value if isinstance(value, list) else [value]


PAGE_SIZE = 40
DECADES = tuple(range(1950, date.today().year // 10 * 10 + 1, 10))
# onglet de la page Albums -> type de getAlbumList2 (« highest » et « decade »/« genre » à part)
ALBUM_LISTS = {"newest": "newest", "frequent": "frequent", "recent": "recent", "random": "random",
               "starred": "starred", "alphabetical": "alphabeticalByName"}
ALBUM_KINDS = tuple(ALBUM_LISTS) + ("highest", "decade", "genre")


class InvalidAlbumList(ValueError):
    pass


def text(value, default=""):
    """Subsonic d'origine renvoie en JSON les noms qui ressemblent à des nombres comme des nombres
    (album « 1989 », artiste « 311 ») : on les remet toujours en texte."""
    return default if value is None or value == "" else str(value)


def mac_leftover(raw):
    """Restes du Finder de macOS copiés avec la musique : dossier « __MACOSX », fichiers « ._… » (ni vrai son ni vraie
    image). Subsonic montre les dossiers « __MACOSX » comme un artiste ou un album ; le site ne les montre nulle part."""
    names = text(raw.get("path")).replace("\\", "/").split("/")
    names += [text(raw.get(key)) for key in ("name", "title", "album")]
    return any(name == "__MACOSX" or name.startswith("._") for name in names)


def visible(items):
    """as_list sans les restes de macOS."""
    return [item for item in as_list(items) if not mac_leftover(item)]


def album_card(raw):
    return {"id": raw.get("id"), "name": text(raw.get("name") or raw.get("title"), "?"), "artist": text(raw.get("artist")),
            "artistId": raw.get("artistId", ""), "year": raw.get("year"), "coverId": raw.get("coverArt", ""),
            "songCount": raw.get("songCount", 0), "starred": bool(raw.get("starred")),
            "plays": int(raw.get("playCount") or 0)}


def song_row(raw):
    return {"id": raw.get("id"), "title": text(raw.get("title"), "?"), "artist": text(raw.get("artist")),
            "album": text(raw.get("album")), "albumId": raw.get("albumId", ""), "track": raw.get("track"),
            "disc": raw.get("discNumber"), "duration": raw.get("duration", 0), "suffix": raw.get("suffix", ""),
            "bitRate": raw.get("bitRate"), "coverId": raw.get("coverArt", ""), "starred": bool(raw.get("starred")),
            "year": raw.get("year"), "genre": text(raw.get("genre")), "artistId": raw.get("artistId", "")}


class Library:
    def __init__(self, subsonic, ratings, messages, cache=None):
        self.subsonic = subsonic
        self.ratings = ratings
        self.messages = messages
        self.cache = cache or TtlCache(600)
        self.top_cache = TtlCache(3600)

    def _call(self, user, endpoint, params=()):
        return self.subsonic.call(Credentials.of(user), endpoint, params)

    def _with_site_data(self, user, albums):
        """Ajoute à chaque album son nombre de commentaires sur le site."""
        comments = self.messages.counts([album_topic(a["id"]) for a in albums])
        for album in albums:
            album["comments"] = comments.get(album_topic(album["id"]), 0)
        return albums

    def _album_list(self, user, kind, size, offset=0, extra=()):
        """Tel que Subsonic le donne (la page Albums compte ce qu'il a renvoyé) : filtrer avec visible() après."""
        params = [("type", kind), ("size", size), ("offset", offset)] + list(extra)
        return [album_card(a) for a in as_list(
            (self._call(user, "getAlbumList2", params).get("albumList2") or {}).get("album"))]

    def albums(self, user, kind, value="", page=0):
        """Une page (40 albums) d'un onglet de la page Albums. value : décennie (1990) ou genre."""
        if kind not in ALBUM_KINDS or not isinstance(page, int) or not 0 <= page <= 1000:
            raise InvalidAlbumList(kind)
        offset = page * PAGE_SIZE
        if kind == "highest":
            albums = [dict(card) for card in self.ratings.top(user, PAGE_SIZE, offset)]
        elif kind == "decade":
            if not str(value).isdigit() or int(value) not in DECADES:
                raise InvalidAlbumList(value)
            albums = self._album_list(user, "byYear", PAGE_SIZE, offset,
                                      [("fromYear", int(value)), ("toYear", int(value) + 9)])
        elif kind == "genre":
            if not value or len(value) > 100:
                raise InvalidAlbumList(value)
            albums = self._album_list(user, "byGenre", PAGE_SIZE, offset, [("genre", value)])
        else:
            albums = self._album_list(user, ALBUM_LISTS[kind], PAGE_SIZE, offset)
        return {"kind": kind, "value": value, "page": page, "albums": self._with_site_data(user, visible(albums)),
                "hasMore": len(albums) == PAGE_SIZE}

    def genres(self, user):
        """Genres qui ont des albums, les plus fournis d'abord (gardé 10 minutes)."""
        def load():
            genres = as_list((self._call(user, "getGenres").get("genres") or {}).get("genre"))
            found = [{"name": text(g.get("value")), "albums": int(g.get("albumCount") or 0)} for g in genres]
            return sorted((g for g in found if g["name"] and g["albums"]), key=lambda g: (-g["albums"], g["name"]))
        return self.cache.get(("genres", user.username), load)

    # --- pages ---
    def top_songs(self, user, artist_name):
        """Titres les plus populaires d'un artiste (Last.fm, par Subsonic) présents dans la bibliothèque ;
        vide sans Last.fm. Gardé une heure : ça ne bouge pas souvent."""
        def load():
            try:
                raw = self._call(user, "getTopSongs", [("artist", artist_name), ("count", 10)]).get("topSongs") or {}
            except (SubsonicError, SubsonicUnreachable):
                return []
            return [song_row(s) for s in visible(raw.get("song"))]
        return self.top_cache.get(("top-songs", artist_name.lower()), load)

    def similar_artists(self, user, artist_id):
        """Artistes proches présents dans la bibliothèque (Last.fm, par Subsonic) ; vide sans Last.fm.
        Gardé une heure."""
        def load():
            try:
                raw = self._call(user, "getArtistInfo2", [("id", artist_id), ("count", 15)]).get("artistInfo2") or {}
            except (SubsonicError, SubsonicUnreachable):
                return []
            return [{"id": a["id"], "name": text(a.get("name"), "?"), "coverId": a.get("coverArt", ""),
                     "albumCount": a.get("albumCount", 0)} for a in as_list(raw.get("similarArtist")) if a.get("id")]
        return self.top_cache.get(("similar", artist_id), load)

    def album(self, user, album_id):
        raw = self._call(user, "getAlbum", [("id", album_id)]).get("album") or {}
        album = album_card(raw)
        album.update(genre=raw.get("genre", ""), duration=raw.get("duration", 0),
                     songs=[song_row(s) for s in visible(raw.get("song"))])
        album["rating"] = self.ratings.summary(user, album_id).to_api()
        self._with_site_data(user, [album])
        return album

    def album_brief(self, user, album_id):
        """Titre, artiste, pochette : pour une carte partagée dans le salon."""
        return self.cache.get(("album", album_id), lambda: album_card(
            self._call(user, "getAlbum", [("id", album_id)]).get("album") or {}))

    def home(self, user):
        return {"newest": self._with_site_data(user, visible(self._album_list(user, "newest", 18))),
                "mostPlayed": self._with_site_data(user, visible(self._album_list(user, "frequent", 12))),
                "topRated": self._with_site_data(user, [dict(card) for card in self.ratings.top(user, limit=12)]),
                "discussed": [a.to_api() for a in self.messages.discussed_albums()]}

    def search(self, user, query):
        query = (query or "").strip()[:100]
        if not query:
            return {"artists": [], "albums": [], "songs": []}
        result = self._call(user, "search3", [("query", query), ("artistCount", 8), ("albumCount", 12),
                                              ("songCount", 30)]).get("searchResult3") or {}
        return {"artists": [{"id": a["id"], "name": text(a.get("name"), "?")} for a in visible(result.get("artist"))],
                "albums": self._with_site_data(user, [album_card(a) for a in visible(result.get("album"))]),
                "songs": [song_row(s) for s in visible(result.get("song"))]}

    def starred(self, user):
        result = self._call(user, "getStarred2").get("starred2") or {}
        return {"albums": self._with_site_data(user, [album_card(a) for a in visible(result.get("album"))]),
                "songs": [song_row(s) for s in visible(result.get("song"))]}

    # --- favoris (cœur Subsonic) ---
    def set_favorite(self, user, kind, item_id, on):
        """kind « folder » : un dossier (« f123 », page artiste), étoilé avec son identifiant de dossier."""
        key = {"album": "albumId", "artist": "artistId", "song": "id", "folder": "id"}[kind]
        if kind == "folder":
            if not item_id.startswith("f"):
                raise ValueError("dossier")
            item_id = item_id[1:]
        self._call(user, "star" if on else "unstar", [(key, item_id)])
        return on
