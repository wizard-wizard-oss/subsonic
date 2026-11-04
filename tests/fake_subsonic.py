"""Faux serveur Subsonic pour les tests : vérifie le jeton, sert une petite bibliothèque, compte les appels."""
import hashlib
import json
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

USERS = {"alice": "secret", "bob": "pw2"}
USER_ROLES = ("settingsRole", "downloadRole", "uploadRole", "playlistRole", "coverArtRole", "commentRole",
              "podcastRole", "streamRole", "jukeboxRole", "shareRole", "videoConversionRole")
AUDIO = bytes(range(256)) * 40                   # 10 240 octets
LOCAL_ANY_PORT = ("127.0.0.1", 0)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32

SONGS = {
    "s1": {"id": "s1", "title": "Dancing Queen", "artist": "ABBA", "track": 2, "discNumber": 1, "duration": 230},
    "s2": {"id": "s2", "title": "Knowing Me", "artist": "ABBA", "track": 1, "discNumber": 1, "duration": 240},
    "s3": {"id": "s3", "title": "Waterloo", "artist": "Abba", "track": 1, "duration": 170},
    "s4": {"id": "s4", "title": "Army of Me", "artist": "Björk", "track": 1, "duration": 235},
}
DIRECTORIES = {
    "ar1": {"id": "ar1", "name": "ABBA", "child": [
        {"id": "al1", "isDir": True, "title": "Arrival", "parent": "ar1"}]},
    "ar2": {"id": "ar2", "name": "Abba", "child": [
        {"id": "al2", "isDir": True, "title": "Waterloo", "parent": "ar2"},
        {"id": "al1b", "isDir": True, "title": "arrival", "parent": "ar2"}]},
    "ar3": {"id": "ar3", "name": "Björk", "child": [
        {"id": "al3", "isDir": True, "title": "Post", "parent": "ar3"}]},
    "al1": {"id": "al1", "name": "Arrival", "parent": "ar1", "child": [SONGS["s1"], SONGS["s2"]]},
    "al2": {"id": "al2", "name": "Waterloo", "parent": "ar2", "child": [SONGS["s3"]]},
    "al3": {"id": "al3", "name": "Post", "parent": "ar3", "child": [SONGS["s4"]]},
}
INDEXES = [{"name": "A", "artist": [{"id": "ar1", "name": "ABBA"}, {"id": "ar2", "name": "Abba"}]},
           {"name": "B", "artist": [{"id": "ar3", "name": "Björk"}]}]


class FakeSubsonic:
    """À utiliser dans un test : start() puis .url ; calls compte les appels par méthode.
    address : (adresse, port) d'écoute ; par défaut la machine seule, port libre choisi par le système."""

    def __init__(self, address=LOCAL_ANY_PORT):
        self.calls = Counter()
        self.posts = Counter()                # appels reçus en POST (paramètres dans le corps)
        self.users = dict(USERS)
        self.newest = ["al1", "al2"]
        owner = self
        self._server = ThreadingHTTPServer(address, self._make_handler(owner))
        self._server.daemon_threads = True

    @property
    def port(self):
        return self._server.server_address[1]

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def start(self):
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self._server.shutdown()
        self._server.server_close()

    @staticmethod
    def _make_handler(owner):
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self, body=""):
                parts = urlsplit(self.path)
                if parts.path.startswith("/radio/"):          # flux d'une radio Internet (hors API)
                    return self.reply(200, AUDIO, "audio/mpeg")
                name = parts.path.rsplit("/", 1)[-1].replace(".view", "")
                self.all_params = parse_qsl(parts.query) + parse_qsl(body)
                owner.posts[name] += bool(body)
                params = dict(self.all_params)
                owner.calls[name] += 1
                if not owner.token_valid(params):
                    return self.reply_json({"status": "failed", "error": {"code": 40, "message": "Wrong credentials"}})
                getattr(owner, "api_" + name, owner.api_unknown)(self, params)

            def do_POST(self):
                """Paramètres dans le corps (formulaire), comme le vrai Subsonic les accepte."""
                self.do_GET(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("ascii"))

            def values(self, name):
                """Paramètre répété (songId=…&songId=…)."""
                return [v for k, v in self.all_params if k == name]

            def reply_json(self, content):
                content.setdefault("version", "1.16.1")
                self.reply(200, json.dumps({"subsonic-response": dict(content, status=content.get("status", "ok"))}).encode(),
                           "application/json")

            def reply(self, status, body, ctype, extra=None):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)
        return Handler

    # --- authentification ---
    def token_valid(self, params):
        password = self.users.get(params.get("u", ""))
        if password is None:
            return False
        return params.get("t") == hashlib.md5((password + params.get("s", "")).encode()).hexdigest()

    # --- méthodes de l'API ---
    def api_unknown(self, h, p):
        h.reply_json({"status": "failed", "error": {"code": 70, "message": "inconnu"}})

    def api_ping(self, h, p):
        h.reply_json({})

    def api_getIndexes(self, h, p):
        h.reply_json({"indexes": {"index": INDEXES}})

    def api_getMusicDirectory(self, h, p):
        directory = DIRECTORIES.get(p.get("id"))
        if directory is None:
            return h.reply_json({"status": "failed", "error": {"code": 70, "message": "introuvable"}})
        h.reply_json({"directory": directory})

    def api_getAlbumList(self, h, p):
        h.reply_json({"albumList": {"album": [DIRECTORIES[i] and
                                              {"id": i, "title": DIRECTORIES[i]["name"], "parent": DIRECTORIES[i]["parent"]}
                                              for i in self.newest]}})

    def api_getAlbumList2(self, h, p):
        h.reply_json({"albumList2": {"album": [{"id": i, "name": DIRECTORIES[i]["name"]} for i in self.newest]}})

    def api_getStarred(self, h, p):
        h.reply_json({"starred": {"song": [SONGS["s1"]]}})

    def api_search2(self, h, p):
        query = (p.get("query") or "").lower()
        songs = [s for s in SONGS.values() if query and (query in s["title"].lower() or query in s["artist"].lower())]
        h.reply_json({"searchResult2": {"artist": [{"id": "ar1", "name": "ABBA"}, {"id": "ar2", "name": "Abba"}], "song": songs}})

    def api_getArtistInfo(self, h, p):
        h.reply_json({"artistInfo": {"biography": "ABBA est un groupe suédois de pop formé à Stockholm en 1972."}})

    def api_getLyrics(self, h, p):
        h.reply_json({"lyrics": {"value": ""}})

    def api_startScan(self, h, p):
        h.reply_json({"scanStatus": {"scanning": True}})

    def api_star(self, h, p):
        h.reply_json({})

    def api_getPlaylists(self, h, p):
        h.reply_json({"playlists": {}})

    def api_getGenres(self, h, p):
        h.reply_json({"genres": {}})

    def api_getCoverArt(self, h, p):
        h.reply(200, PNG, "image/png")

    def api_stream(self, h, p):
        wanted = h.headers.get("Range")
        if not wanted:
            return h.reply(200, AUDIO, "audio/mpeg", {"Accept-Ranges": "bytes"})
        start, _, end = wanted.replace("bytes=", "").partition("-")
        first, last = int(start), int(end) if end else len(AUDIO) - 1
        h.reply(206, AUDIO[first:last + 1], "audio/mpeg",
                {"Content-Range": "bytes %d-%d/%d" % (first, last, len(AUDIO)), "Accept-Ranges": "bytes"})


# --- API ID3 (édition PC) ---
ID3_ARTISTS = {
    "ar1": {"id": "ar1", "name": "ABBA", "albumCount": 2, "album": [
        {"id": "al1", "name": "Arrival", "artist": "ABBA", "artistId": "ar1", "year": 1976, "coverArt": "al1",
         "songCount": 2, "genre": "Pop"},
        {"id": "al2", "name": "Waterloo", "artist": "ABBA", "artistId": "ar1", "year": 1974, "coverArt": "al2",
         "songCount": 1, "genre": "Pop"}]},
    "ar3": {"id": "ar3", "name": "Björk", "albumCount": 1, "album": [
        {"id": "al3", "name": "Post", "artist": "Björk", "artistId": "ar3", "year": 1995, "coverArt": "al3",
         "songCount": 1, "genre": "Electronic"}]},
}
ID3_SONGS = {"al1": ["s1", "s2"], "al2": ["s3"], "al3": ["s4"]}
PLAY_COUNTS = {"al1": 12, "al2": 3, "al3": 7}       # écoutes par album (playCount, compté par Subsonic)
DISC_FOLDERS = {"s1": "dir-al1-cd1", "s2": "dir-al1-cd2"}   # Arrival : un sous-dossier par disque


# Dossiers d'artistes de l'édition PC (getIndexes) : « dir-<artiste ID3> » ; Incoming est un dossier de la racine aussi.
PC_INDEXES = [{"name": "A", "artist": [{"id": "dir-ar1", "name": "ABBA"}]},
              {"name": "B", "artist": [{"id": "dir-ar3", "name": "Björk"}]},
              {"name": "I", "artist": [{"id": "dir-incoming", "name": "Incoming"}]}]


def album_folder(album_id):
    """Dossier Subsonic d'un album ID3 (les notes sont posées sur les dossiers, comme dans Subsonic d'origine)."""
    return "dir-" + album_id


def _id3_album(album_id):
    for artist in ID3_ARTISTS.values():
        for album in artist["album"]:
            if album["id"] == album_id:
                return album
    return None


class FakeSubsonicId3(FakeSubsonic):
    """Le même faux serveur, avec l'API ID3 utilisée par l'édition PC (artistes, albums, notes, favoris).
    Fidèle au schéma Subsonic 1.16.1 : userRating / averageRating seulement sur les dossiers et les fichiers,
    setRating refuse un identifiant d'album ID3, playCount sur les albums ID3."""

    def __init__(self, address=LOCAL_ANY_PORT):
        super().__init__(address)
        self.ratings = {}                 # (utilisateur, dossier ou titre) -> note
        self.starred_albums = set()
        self.starred_folders = set()
        self.newest_albums = ["al3", "al1", "al2"]     # ordre de « newest »
        self.roles = {}                   # utilisateur -> droits changés ({"downloadRole": False}) ; sinon tous
        self.emails = {"alice": "Alice@Exemple.fr"}   # adresse e-mail du compte (getUser) ; les autres n'en ont pas
        self.downloads = []               # identifiants demandés à download

    def _song(self, song_id, album):
        parent = DISC_FOLDERS.get(song_id, album_folder(album["id"]))
        disc = parent.rsplit("-", 1)[1].upper() + "/" if parent != album_folder(album["id"]) else ""
        return dict(SONGS[song_id], album=album["name"], albumId=album["id"], artistId=album.get("artistId", ""),
                    suffix="flac", parent=parent,
                    path="%s/%s/%s%s.flac" % (album["artist"], album["name"], disc, song_id))     # chemin dans la musique

    def _rating_attributes(self, item_id, user):
        votes = [r for (u, i), r in self.ratings.items() if i == item_id]
        mine = self.ratings.get((user, item_id))
        return dict({"userRating": mine} if mine else {},
                    **({"averageRating": round(sum(votes) / len(votes), 2)} if votes else {}))

    def _folder(self, folder_id, user):
        """getMusicDirectory d'un dossier d'artiste (« dir-ar1 »), d'album (« dir-al1 ») ou de disque (« dir-al1-cd1 »)."""
        artist = ID3_ARTISTS.get(folder_id[len("dir-"):])
        if artist:
            return {"id": folder_id, "name": artist["name"], "starred": "2026-01-01" if folder_id in self.starred_folders else None,
                    "child": [{"id": album_folder(a["id"]), "isDir": True, "title": a["name"], "parent": folder_id,
                               "year": a.get("year"), "coverArt": a.get("coverArt"), "playCount": PLAY_COUNTS.get(a["id"], 0)}
                              for a in artist["album"]]}
        album_id, _, disc = folder_id[len("dir-"):].partition("-")
        album = _id3_album(album_id)
        if album is None:
            return None
        songs = [self._song(s, album) for s in ID3_SONGS.get(album_id, [])]
        if disc:
            children = [s for s in songs if s["parent"] == folder_id]
            directory = {"id": folder_id, "name": disc.upper(), "parent": album_folder(album_id), "child": children}
        else:
            discs = sorted({s["parent"] for s in songs if s["parent"] != folder_id})
            children = [{"id": d, "isDir": True, "title": d.rsplit("-", 1)[1].upper(), "parent": folder_id,
                         "path": "%s/%s/%s" % (album["artist"], album["name"], d.rsplit("-", 1)[1].upper())}
                        for d in discs] + [s for s in songs if s["parent"] == folder_id]
            directory = {"id": folder_id, "name": album["name"], "parent": "dir-" + album.get("artistId", ""),
                         "playCount": PLAY_COUNTS.get(album_id, 0), "child": children}
        directory.update(self._rating_attributes(folder_id, user))
        return directory

    def api_getMusicDirectory(self, h, p):
        if not (p.get("id") or "").startswith("dir-"):
            return super().api_getMusicDirectory(h, p)
        directory = self._folder(p["id"], p.get("u"))
        if directory is None:
            return h.reply_json({"status": "failed", "error": {"code": 70, "message": "introuvable"}})
        h.reply_json({"directory": directory})

    def api_getAlbumList(self, h, p):
        if p.get("type") != "highest":
            return super().api_getAlbumList(h, p)
        rated = []
        for artist in ID3_ARTISTS.values():
            for album in artist["album"]:
                folder = self._folder(album_folder(album["id"]), p.get("u"))
                if folder.get("averageRating"):
                    rated.append({"id": folder["id"], "parent": folder["parent"], "isDir": True,
                                  "title": album["name"], "album": album["name"], "artist": album["artist"],
                                  "year": album.get("year"), "coverArt": album.get("coverArt"),
                                  "playCount": folder["playCount"], **self._rating_attributes(folder["id"], p.get("u"))})
        rated.sort(key=lambda f: -f["averageRating"])
        h.reply_json({"albumList": {"album": rated[:int(p.get("size", "10"))]}})

    def api_getArtists(self, h, p):
        h.reply_json({"artists": {"index": [
            {"name": "A", "artist": [{"id": "ar1", "name": "ABBA", "albumCount": 2}]},
            {"name": "B", "artist": [{"id": "ar3", "name": "Björk", "albumCount": 1}]}]}})

    def api_getArtist(self, h, p):
        artist = ID3_ARTISTS.get(p.get("id"))
        if artist is None:
            return h.reply_json({"status": "failed", "error": {"code": 70, "message": "introuvable"}})
        h.reply_json({"artist": artist})

    def api_getAlbum(self, h, p):
        album = _id3_album(p.get("id"))
        if album is None:
            return h.reply_json({"status": "failed", "error": {"code": 70, "message": "introuvable"}})
        songs = [self._song(s, album) for s in ID3_SONGS[album["id"]]]
        h.reply_json({"album": dict(album, song=songs, duration=470,
                                    playCount=PLAY_COUNTS.get(album["id"], 0),
                                    starred="2026-01-01" if album["id"] in self.starred_albums else None)})

    def api_getAlbumList2(self, h, p):
        """Listes de Subsonic : ordre de newest_albums ; filtres par année et genre ; size et offset."""
        kind = p.get("type")
        albums = [dict(_id3_album(i), playCount=PLAY_COUNTS.get(i, 0)) for i in self.newest_albums]
        if kind == "frequent":
            albums.sort(key=lambda a: -a["playCount"])
        elif kind == "alphabeticalByName":
            albums.sort(key=lambda a: a["name"])
        elif kind == "starred":
            albums = [a for a in albums if a["id"] in self.starred_albums]
        elif kind == "byYear":
            low, high = int(p["fromYear"]), int(p["toYear"])
            albums = sorted((a for a in albums if low <= a["year"] <= high), key=lambda a: a["year"])
        elif kind == "byGenre":
            albums = [a for a in albums if a.get("genre") == p.get("genre")]
        offset, size = int(p.get("offset", "0")), int(p.get("size", "10"))
        h.reply_json({"albumList2": {"album": albums[offset:offset + size]}})

    def api_getGenres(self, h, p):
        counts = {}
        for artist in ID3_ARTISTS.values():
            for album in artist["album"]:
                counts[album.get("genre", "")] = counts.get(album.get("genre", ""), 0) + 1
        h.reply_json({"genres": {"genre": [{"value": g, "albumCount": n, "songCount": n} for g, n in counts.items()]
                                 + [{"value": "Vide", "albumCount": 0, "songCount": 0}]}})

    def api_search3(self, h, p):
        query = (p.get("query") or "").lower()
        artists = [{"id": a["id"], "name": a["name"]} for a in ID3_ARTISTS.values() if query in a["name"].lower()]
        albums = [al for a in ID3_ARTISTS.values() for al in a["album"] if query in al["name"].lower()]
        songs = [s for s in SONGS.values() if query in s["title"].lower()]
        h.reply_json({"searchResult3": {"artist": artists, "album": albums, "song": songs}})

    def api_getStarred2(self, h, p):
        h.reply_json({"starred2": {"album": [_id3_album(i) for i in sorted(self.starred_albums)], "song": []}})

    def api_setRating(self, h, p):
        """Comme Subsonic : seuls un dossier ou un fichier peuvent être notés (pas un album ID3)."""
        if not (p.get("id") or "").startswith("dir-") and p.get("id") not in SONGS:
            return h.reply_json({"status": "failed", "error": {"code": 70, "message": "Media file not found."}})
        rating = int(p.get("rating", "0"))
        if rating:
            self.ratings[(p.get("u"), p.get("id"))] = rating
        else:
            self.ratings.pop((p.get("u"), p.get("id")), None)
        h.reply_json({})

    def api_star(self, h, p):
        if p.get("albumId"):
            self.starred_albums.add(p["albumId"])
        h.reply_json({})

    def api_unstar(self, h, p):
        self.starred_albums.discard(p.get("albumId"))
        h.reply_json({})

    def api_getUser(self, h, p):
        """Comme Subsonic 1.16.1 : tous les droits (alice seule administratrice), sauf ceux retirés dans roles."""
        name = p.get("username")
        user = dict({role: True for role in USER_ROLES}, username=name, adminRole=name == "alice", scrobblingEnabled=True)
        if name in self.emails:
            user["email"] = self.emails[name]
        user.update(self.roles.get(name, {}))
        h.reply_json({"user": user})

    def api_download(self, h, p):
        """Un dossier : Subsonic l'envoie en zip ; un titre : le fichier d'origine."""
        self.downloads.append(p.get("id"))
        if p.get("id", "").startswith("dir-"):
            return h.reply(200, b"PK\x03\x04zip", "application/zip",
                           {"Content-Disposition": 'attachment; filename="%s.zip"' % p.get("id")})
        h.reply(200, AUDIO, "audio/flac", {"Content-Disposition": 'attachment; filename="%s.flac"' % p.get("id")})


# --- édition PC : mixes, Last.fm, playlists, écoute, marque-pages, file, radios, avatars ---
def _id3_song(song_id):
    """Titre avec son album, son style et son année (comme getSong de Subsonic)."""
    for artist in ID3_ARTISTS.values():
        for album in artist["album"]:
            if song_id in ID3_SONGS.get(album["id"], []):
                return dict(SONGS[song_id], album=album["name"], albumId=album["id"], artistId=album["artistId"],
                            genre=album.get("genre", ""), year=album.get("year"), suffix="flac",
                            coverArt=album.get("coverArt", ""),
                            parent=DISC_FOLDERS.get(song_id, album_folder(album["id"])))
    return None


def _all_id3_songs():
    return [s for s in (_id3_song(i) for ids in ID3_SONGS.values() for i in ids) if s]


SIMILAR_ARTISTS = {"ar1": ["ar3"], "ar3": ["ar1"]}       # ce que Last.fm renverrait
BIOGRAPHIES = {"ar3": "Björk Guðmundsdóttir is an Icelandic singer, songwriter and composer. "
                      "She rose to fame as the lead singer of the Sugarcubes. "
                      '<a href="https://www.last.fm/music/Bj%C3%B6rk">Read more on Last.fm</a>'}
RADIOS = [{"id": "1", "name": "FIP", "streamUrl": "/radio/fip", "homePageUrl": "https://www.radiofrance.fr/fip"},
          {"id": "2", "name": "Vieux format", "streamUrl": "ftp://radio.example/flux"}]


class FakeSubsonicFull(FakeSubsonicId3):
    """Faux Subsonic complet pour l'édition PC. lastfm=False : comme un serveur sans clé Last.fm
    (getSimilarSongs2, getTopSongs et getArtistInfo2 répondent, mais vides)."""

    def __init__(self, address=LOCAL_ANY_PORT):
        super().__init__(address)
        self.lastfm = True
        self.starred_songs = set()
        self.playlists = {}               # id -> {"id", "name", "owner", "public", "songs": [...]}
        self.scrobbles = []               # (utilisateur, titre, compté ?)
        self.now_playing = {}             # utilisateur -> titre
        self.bookmarks = {}               # (utilisateur, titre) -> (position ms, commentaire, n° d'ordre)
        self.play_queues = {}             # utilisateur -> {"ids", "current", "position"}
        self.avatars = {"bob": PNG}
        self.music_folders = {}           # utilisateur -> dossiers de musique visibles (absent : tous, [1, 2])
        self.last_scan = int(time.time() * 1000) - 3_600_000   # dernier scan (ms) : il y a une heure
        self.indexes = [dict(group) for group in PC_INDEXES]  # dossiers d'artistes (getIndexes)
        self.index_builds = 0             # getIndexes complets (sans ifModifiedSince) : la liste calculée

    def _failed(self, h, code=70, message="introuvable"):
        h.reply_json({"status": "failed", "error": {"code": code, "message": message}})

    # --- dossiers de musique, et « la bibliothèque a-t-elle changé ? » ---
    def api_getMusicFolders(self, h, p):
        ids = self.music_folders.get(p.get("u"), [1, 2])
        h.reply_json({"musicFolders": {"musicFolder": [{"id": i, "name": "Dossier %d" % i} for i in ids]}})

    def scan(self):
        """Nouveau scan de la bibliothèque, maintenant."""
        self.last_scan = int(time.time() * 1000)

    def api_getIndexes(self, h, p):
        """Comme Subsonic : rien (et tout de suite) si rien n'a été scanné depuis ifModifiedSince."""
        if not p.get("ifModifiedSince"):
            self.index_builds += 1
        elif int(p["ifModifiedSince"]) >= self.last_scan:
            return h.reply_json({"indexes": {}})
        h.reply_json({"indexes": {"lastModified": self.last_scan, "index": self.indexes}})

    # --- mixes ---
    def api_getRandomSongs(self, h, p):
        songs = _all_id3_songs()
        if p.get("genre"):
            songs = [s for s in songs if s["genre"] == p["genre"]]
        if p.get("fromYear"):
            songs = [s for s in songs if int(p["fromYear"]) <= (s["year"] or 0) <= int(p.get("toYear", "9999"))]
        h.reply_json({"randomSongs": {"song": songs[:int(p.get("size", "10"))]}})

    def api_getSong(self, h, p):
        song = _id3_song(p.get("id"))
        return h.reply_json({"song": song}) if song else self._failed(h)

    def api_getSimilarSongs2(self, h, p):
        if not self.lastfm:
            return h.reply_json({"similarSongs2": {}})
        h.reply_json({"similarSongs2": {"song": [s for s in _all_id3_songs() if s["id"] != p.get("id")]}})

    def api_getTopSongs(self, h, p):
        songs = [s for s in _all_id3_songs() if s["artist"].lower() == (p.get("artist") or "").lower()]
        h.reply_json({"topSongs": {"song": songs} if self.lastfm else {}})

    def api_getArtistInfo2(self, h, p):
        names = {a["id"]: a["name"] for a in ID3_ARTISTS.values()}
        similar = [{"id": i, "name": names[i]} for i in SIMILAR_ARTISTS.get(p.get("id"), [])] if self.lastfm else []
        info = {"similarArtist": similar}
        if self.lastfm and p.get("id") in BIOGRAPHIES:
            info.update(biography=BIOGRAPHIES[p["id"]], lastFmUrl="https://www.last.fm/music/" + names[p["id"]])
        h.reply_json({"artistInfo2": info})

    def api_getStarred2(self, h, p):
        h.reply_json({"starred2": {"album": [_id3_album(i) for i in sorted(self.starred_albums)],
                                   "song": [_id3_song(i) for i in sorted(self.starred_songs)]}})

    def api_star(self, h, p):
        if p.get("id"):                                   # un titre, ou un dossier (« dir-… »)
            (self.starred_folders if p["id"].startswith("dir-") else self.starred_songs).add(p["id"])
        super().api_star(h, p)

    def api_unstar(self, h, p):
        self.starred_songs.discard(p.get("id"))
        self.starred_folders.discard(p.get("id"))
        super().api_unstar(h, p)

    # --- playlists ---
    def _playlist(self, playlist, with_songs=False):
        card = {"id": playlist["id"], "name": playlist["name"], "owner": playlist["owner"],
                "public": playlist["public"], "songCount": len(playlist["songs"]), "duration": 0}
        if with_songs:
            card["entry"] = [_id3_song(s) for s in playlist["songs"]]
        return card

    def _visible(self, h, p, mine_only=False):
        playlist = self.playlists.get(p.get("id") or p.get("playlistId"))
        if playlist is None or (playlist["owner"] != p.get("u") and (mine_only or not playlist["public"])):
            self._failed(h, 50 if playlist else 70, "interdit" if playlist else "introuvable")
            return None
        return playlist

    def api_getPlaylists(self, h, p):
        h.reply_json({"playlists": {"playlist": [self._playlist(pl) for pl in self.playlists.values()
                                                 if pl["owner"] == p.get("u") or pl["public"]]}})

    def api_getPlaylist(self, h, p):
        playlist = self._visible(h, p)
        if playlist:
            h.reply_json({"playlist": self._playlist(playlist, True)})

    def api_createPlaylist(self, h, p):
        playlist_id = "pl%d" % (len(self.playlists) + 1)
        self.playlists[playlist_id] = {"id": playlist_id, "name": p["name"], "owner": p.get("u"), "public": False,
                                       "songs": h.values("songId")}
        h.reply_json({"playlist": self._playlist(self.playlists[playlist_id], True)})

    def api_updatePlaylist(self, h, p):
        playlist = self._visible(h, p, mine_only=True)
        if not playlist:
            return
        if p.get("name"):
            playlist["name"] = p["name"]
        if p.get("public"):
            playlist["public"] = p["public"] == "true"
        removed = {int(i) for i in h.values("songIndexToRemove")}
        playlist["songs"] = [s for i, s in enumerate(playlist["songs"]) if i not in removed] + h.values("songIdToAdd")
        h.reply_json({})

    def api_deletePlaylist(self, h, p):
        if self._visible(h, p, mine_only=True):
            del self.playlists[p["id"]]
            h.reply_json({})

    # --- écoute ---
    def api_scrobble(self, h, p):
        submission = p.get("submission", "true") == "true"
        self.scrobbles.append((p.get("u"), p.get("id"), submission))
        if not submission:
            self.now_playing[p.get("u")] = p.get("id")
        h.reply_json({})

    def api_getNowPlaying(self, h, p):
        h.reply_json({"nowPlaying": {"entry": [dict(_id3_song(s), username=u, minutesAgo=0, playerName="pimedia-web")
                                               for u, s in self.now_playing.items()]}})

    def api_getBookmarks(self, h, p):
        mine = [(song, value) for (user, song), value in self.bookmarks.items() if user == p.get("u")]
        h.reply_json({"bookmarks": {"bookmark": [
            {"entry": _id3_song(song), "position": position, "comment": comment, "username": p.get("u"),
             "created": "2026-10-%02dT10:00:00" % order, "changed": "2026-10-%02dT10:00:00" % order}
            for song, (position, comment, order) in mine]}})

    def api_createBookmark(self, h, p):
        if _id3_song(p.get("id")) is None:
            return self._failed(h)
        self.bookmarks[(p.get("u"), p["id"])] = (int(p["position"]), p.get("comment", ""), len(self.bookmarks) + 1)
        h.reply_json({})

    def api_deleteBookmark(self, h, p):
        self.bookmarks.pop((p.get("u"), p.get("id")), None)
        h.reply_json({})

    def api_getPlayQueue(self, h, p):
        queue = self.play_queues.get(p.get("u"))
        if not queue:
            return h.reply_json({})
        h.reply_json({"playQueue": {"entry": [_id3_song(s) for s in queue["ids"]], "current": queue["current"],
                                    "position": queue["position"], "username": p.get("u"),
                                    "changed": "2026-10-25T10:00:00", "changedBy": p.get("c", "")}})

    def api_savePlayQueue(self, h, p):
        self.play_queues[p.get("u")] = {"ids": h.values("id"), "current": p.get("current", ""),
                                        "position": int(p.get("position", "0"))}
        h.reply_json({})

    # --- radios Internet, avatars ---
    def api_getInternetRadioStations(self, h, p):
        stations = [dict(r, streamUrl=self.url + r["streamUrl"] if r["streamUrl"].startswith("/") else r["streamUrl"])
                    for r in RADIOS]
        h.reply_json({"internetRadioStations": {"internetRadioStation": stations}})

    def api_getAvatar(self, h, p):
        image = self.avatars.get(p.get("username"))
        if image is None:
            return h.reply(404, b"", "text/plain")
        h.reply(200, image, "image/png")
