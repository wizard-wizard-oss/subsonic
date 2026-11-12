"""Bibliothèque, favoris, étoiles, pochettes et flux audio."""
import re

from ...server.transport import Reply, StreamReply
from ..subsonic import Credentials
from .base import ok

ITEM_ID = re.compile(r"^[\w-]{1,100}$")


class DownloadReply(StreamReply):
    """Fichier ou zip d'album relayé avec le nom donné par Subsonic."""
    COPIED_HEADERS = StreamReply.COPIED_HEADERS + ("Content-Disposition",)


def item_id(value):
    value = value or ""
    if not isinstance(value, str) or not ITEM_ID.fullmatch(value):
        raise ValueError("identifiant")
    return value


class LibraryController:
    def __init__(self, library, folders, artist_indexes, ratings, subsonic, statistics, upload_attribution):
        self.upload_attribution = upload_attribution
        self.library = library
        self.folders = folders
        self.artist_indexes = artist_indexes
        self.ratings = ratings
        self.subsonic = subsonic
        self.statistics = statistics

    def home(self, request, user):
        data = self.library.home(user)
        self.upload_attribution.annotate(user, data["newest"])
        statistics = self.statistics.get()
        return ok(dict(data, statistics=statistics.to_api() if statistics else None))

    def artists(self, request, user):
        index = self.artist_indexes.for_user(user)
        return ok({"index": index, "shortcuts": self.artist_indexes.shortcuts(index)})

    def artist(self, request, user):
        return ok(self.folders.artist(user, item_id(request.param("id"))))

    def top_songs(self, request, user):
        name = (request.param("name") or "").strip()
        if not name or len(name) > 200:
            raise ValueError("nom")
        return ok({"songs": self.library.top_songs(user, name)})

    def similar(self, request, user):
        return ok({"artists": self.library.similar_artists(user, item_id(request.param("id")))})

    def album(self, request, user):
        album = self.folders.album(user, item_id(request.param("id")))
        self.upload_attribution.annotate(user, [album])
        return ok(album)

    def albums(self, request, user):
        page = request.param("page", "0")
        return ok(self.library.albums(user, request.param("kind", "newest"), request.param("value"),
                                      int(page) if page.isdigit() else -1))

    def genres(self, request, user):
        return ok({"genres": self.library.genres(user)})

    def search(self, request, user):
        return ok(self.library.search(user, request.param("q")))

    def starred(self, request, user):
        return ok(self.library.starred(user))

    def favorite(self, request, user, body):
        kind = body.get("kind")
        if kind not in ("album", "artist", "song", "folder"):
            raise ValueError("type")
        return ok({"starred": self.library.set_favorite(user, kind, item_id(body.get("id")), bool(body.get("on")))})

    def rate(self, request, user, body):
        return ok({"rating": self.ratings.rate(user, item_id(body.get("albumId")), body.get("rating")).to_api()})

    # --- binaires relayés (le jeton Subsonic ne quitte jamais le serveur) ---
    def cover(self, request, user):
        size = request.param("size", "300")
        params = [("id", item_id(request.param("id"))), ("size", size if size.isdigit() else "300")]
        upstream = self.subsonic.open(Credentials.of(user), "getCoverArt", params)
        if upstream.status != 200:
            upstream.close()
            return Reply.not_found()
        reply = StreamReply(upstream, 200)
        return reply

    def download(self, request, user):
        """?album=… : Subsonic zippe le dossier de l'album (celui qui contient les disques) ; ?song=… : le fichier."""
        request.set_timeout(3600)
        if request.param("album"):
            target = self.ratings.folder_of(user, item_id(request.param("album")))
            if not target:
                return Reply.not_found()
        else:
            target = item_id(request.param("song"))
        upstream = self.subsonic.open(Credentials.of(user), "download", [("id", target)])
        if upstream.status != 200:
            upstream.close()
            return Reply.not_found()
        return DownloadReply(upstream, 200)

    def stream(self, request, user):
        request.set_timeout(3600)
        params = [("id", item_id(request.param("id")))]
        upstream = self.subsonic.open(Credentials.of(user), "stream", params,
                                      headers={"Range": request.header("Range")})
        if upstream.status not in (200, 206):
            upstream.close()
            return Reply.not_found()
        return StreamReply(upstream, upstream.status)
