"""Mode « dossiers » : traduit les appels de l'API par tags (ID3) en appels de l'API par dossiers,
pour retrouver le classement de l'interface Subsonic d'origine."""
from ..shared.text import normalize
from .constants import API_VERSION


# ---------- fonctions pures ----------
def as_list(value):
    """Subsonic renvoie un objet seul ou une liste : on veut toujours une liste."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def normalize_name(name):
    """Nom comparable : sans accents, sans majuscules, sans « the », sans ponctuation."""
    parts = (name or "").split(maxsplit=1)
    if len(parts) == 2 and normalize(parts[0]) == "the":
        return normalize(parts[1])
    return normalize(name)


def merge_artists(artists):
    """Le même artiste présent dans plusieurs dossiers (FLAC et MP3, Abba / ABBA) ne forme qu'une entrée.
    L'identifiant fusionné est « id1|id2 » ; getArtist rassemble alors les albums de chaque dossier."""
    groups, order = {}, []
    for artist in artists:
        key = normalize_name(artist.get("name")) or artist.get("id")
        if key not in groups:
            groups[key] = dict(artist)
            order.append(key)
        elif artist["id"] not in groups[key]["id"].split("|"):
            groups[key]["id"] += "|" + artist["id"]
    return [groups[key] for key in order]


def first_id(merged_id):
    return merged_id.split("|")[0]


def pick_params(params, *names):
    return [(k, v) for k, v in params if k in names]


def with_first_id(params):
    """Remplace un identifiant fusionné par son premier élément (appels qui n'en acceptent qu'un)."""
    return [(k, first_id(v) if k == "id" else v) for k, v in params]


def to_album(child, artist=None, artist_id=None):
    """Un dossier (ou une entrée d'album) Subsonic, au format « album » de l'API ID3."""
    album = {"id": child["id"], "name": child.get("title") or child.get("album") or child.get("name") or "",
             "artist": child.get("artist") or artist or "", "artistId": artist_id or child.get("parent"),
             "coverArt": child.get("coverArt") or child["id"], "year": child.get("year"),
             "songCount": child.get("songCount"), "duration": child.get("duration"),
             "starred": child.get("starred")}
    return {k: v for k, v in album.items() if v is not None}


def sort_tracks(songs):
    songs.sort(key=lambda c: (c.get("discNumber") or 0, c.get("track") or 0))
    return songs


# ---------- adaptateur ----------
class FolderAdapter:
    MAX_SUBFOLDERS = 20          # sous-dossiers explorés pour un album en plusieurs CD
    MAX_DEPTH = 2

    def __init__(self, api):
        self.api = api
        self._handlers = {
            "getArtists": self._artists, "getArtist": self._artist, "getAlbum": self._album,
            "getAlbumList2": self._album_list, "getStarred2": self._starred, "search3": self._search,
            "getArtistInfo2": self._artist_info, "getSimilarSongs2": self._similar_songs,
        }

    def translate(self, endpoint, params):
        """Contenu de « subsonic-response » pour l'appel ID3 demandé."""
        handler = self._handlers.get(endpoint)
        if handler is None:
            raise RuntimeError("non géré")
        return dict(handler(params), status="ok", version=API_VERSION)

    # --- accès ---
    def _call(self, endpoint, params=()):
        return self.api.call_json(endpoint, params)

    def _directory(self, dir_id):
        return self._call("getMusicDirectory", [("id", dir_id)])["directory"]

    def _songs_in(self, dir_id, depth=0):
        """Titres d'un dossier ; s'il n'en contient pas, on descend dans ses sous-dossiers (CD1, CD2…)."""
        directory = self._directory(dir_id)
        kids = as_list(directory.get("child"))
        songs = [c for c in kids if not c.get("isDir")]
        if not songs and depth < self.MAX_DEPTH:
            for sub in [c for c in kids if c.get("isDir")][:self.MAX_SUBFOLDERS]:
                songs += self._songs_in(sub["id"], depth + 1)[1]
        return directory, songs

    # --- artistes ---
    def _artists(self, params):
        indexes = self._call("getIndexes").get("indexes") or {}
        groups = as_list(indexes.get("index"))
        everyone = [{"id": a["id"], "name": a.get("name", "")}
                    for g in groups for a in as_list(g.get("artist"))]
        merged = {first_id(a["id"]): a for a in merge_artists(everyone)}
        return {"artists": {"index": self._regroup(groups, merged)}}

    @staticmethod
    def _regroup(groups, merged):
        result = []
        for group in groups:
            kept = [merged[a["id"]] for a in as_list(group.get("artist")) if a["id"] in merged]
            if kept:
                result.append({"name": group.get("name", "#"), "artist": kept})
        return result

    def _artist(self, params):
        artist_id = dict(params)["id"]
        albums, name, seen = [], "", set()
        for folder_id in artist_id.split("|"):
            directory = self._directory(folder_id)
            name = name or directory.get("name", "")
            for album in self._albums_of_folder(directory, folder_id, artist_id):
                key = normalize_name(album.get("name"))
                if key not in seen:                 # même album présent dans deux dossiers
                    seen.add(key)
                    albums.append(album)
        return {"artist": {"id": artist_id, "name": name, "albumCount": len(albums), "album": albums}}

    @staticmethod
    def _albums_of_folder(directory, folder_id, artist_id):
        kids = as_list(directory.get("child"))
        albums = [to_album(c, directory.get("name"), artist_id) for c in kids if c.get("isDir")]
        if any(not c.get("isDir") for c in kids):   # titres posés directement dans le dossier de l'artiste
            albums.append(to_album({"id": folder_id, "title": "Titres seuls"}, directory.get("name"), artist_id))
        return albums

    # --- albums ---
    def _album(self, params):
        album_id = dict(params)["id"]
        directory, songs = self._songs_in(album_id)
        artist_id = directory.get("parent")
        for song in sort_tracks(songs):
            song.setdefault("artistId", artist_id)
            song.setdefault("albumId", album_id)
        first = songs[0] if songs else {}
        return {"album": {
            "id": album_id, "name": directory.get("name", ""), "artist": first.get("artist", ""),
            "artistId": artist_id, "coverArt": directory.get("coverArt") or album_id, "year": first.get("year"),
            "songCount": len(songs), "duration": sum(c.get("duration") or 0 for c in songs), "song": songs}}

    def _album_list(self, params):
        wanted = pick_params(params, "type", "size", "offset", "genre", "fromYear", "toYear")
        result = self._call("getAlbumList", wanted).get("albumList") or {}
        return {"albumList2": {"album": [to_album(c) for c in as_list(result.get("album"))]}}

    # --- favoris et recherche ---
    def _starred(self, params):
        found = self._call("getStarred").get("starred") or {}
        return {"starred2": self._library_sections(found)}

    def _search(self, params):
        wanted = pick_params(params, "query", "artistCount", "albumCount", "songCount")
        found = self._call("search2", wanted).get("searchResult2") or {}
        return {"searchResult3": self._library_sections(found)}

    @staticmethod
    def _library_sections(found):
        return {"artist": merge_artists(as_list(found.get("artist"))),
                "album": [to_album(c) for c in as_list(found.get("album"))],
                "song": as_list(found.get("song"))}

    # --- informations ---
    def _artist_info(self, params):
        wanted = pick_params(with_first_id(params), "id", "count", "includeNotPresent")
        return {"artistInfo2": self._call("getArtistInfo", wanted).get("artistInfo") or {}}

    def _similar_songs(self, params):
        wanted = pick_params(with_first_id(params), "id", "count")
        return {"similarSongs2": self._call("getSimilarSongs", wanted).get("similarSongs") or {}}
