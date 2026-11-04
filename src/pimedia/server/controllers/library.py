"""Relais des appels Subsonic (/rest/…), informations externes (/info/…) et gestion du cache (/cache/…)."""
from ..constants import API_VERSION, AUTH_PARAMS, BINARY_ENDPOINTS
from ..upstream import NotConfigured
from ..tasks import in_background
from ..transport import NO_STORE, Reply, StreamReply

COVER_HEADERS = {"Cache-Control": "max-age=604800"}


def failure_body(message):
    """Réponse Subsonic « échec », que l'interface sait afficher."""
    return {"subsonic-response": {"status": "failed", "version": API_VERSION,
                                  "error": {"code": 0, "message": message}}}


def endpoint_of(path):
    """« /rest/getArtists.view » -> « getArtists »."""
    name = path.rsplit("/", 1)[-1]
    return name[:-5] if name.endswith(".view") else name


class RestController:
    def __init__(self, api, covers, client):
        self.api = api
        self.covers = covers
        self.client = client

    def handle(self, request):
        endpoint = endpoint_of(request.path)
        params = [(k, v) for k, v in request.query if k not in AUTH_PARAMS]
        try:
            return self._route(request, endpoint, params)
        except NotConfigured:
            return Reply.json(failure_body("Serveur non configuré : lancez set-subsonic.sh"))
        except Exception as error:      # noqa: BLE001
            return Reply.json(failure_body("Serveur injoignable : %s" % error))

    def _route(self, request, endpoint, params):
        if endpoint == "getCoverArt":
            result = self.covers.get(params)
            return Reply(result.status, result.body, result.ctype, dict(COVER_HEADERS, **{"X-Cache": result.state}))
        if endpoint in BINARY_ENDPOINTS:
            return self._stream(request, endpoint, params)
        result = self.api.call(endpoint, params)
        return Reply(result.status, result.body, result.ctype, dict(NO_STORE, **{"X-Cache": result.state}))

    def _stream(self, request, endpoint, params):
        """Flux audio : pas de cache, relais direct avec prise en charge de Range."""
        range_header = request.header("Range")
        request.set_timeout(120)
        upstream = self.client.open(endpoint, params, {"Range": range_header} if range_header else None)
        status = getattr(upstream, "status", None) or upstream.code
        if status >= 400:
            print("flux Subsonic : HTTP %s (Range: %s)" % (status, range_header), flush=True)
        return StreamReply(upstream, status)


class InfoController:
    """Paroles, anecdotes et genres venant de sources externes."""

    def __init__(self, external):
        self.external = external

    def genres(self, request):
        artist = request.param("artist")
        return Reply.raw_json(self.external.genres(artist) if artist else b"{}")

    def lyrics(self, request):
        artist, title = request.param("artist"), request.param("title")
        if not artist or not title:
            return Reply.raw_json(b"{}")
        duration = int(float(request.param("duration") or 0))
        return Reply.raw_json(self.external.lyrics(artist, title, request.param("album"), duration))

    def facts(self, request):
        artist, title = request.param("artist"), request.param("title")
        if not artist or not title:
            return Reply.raw_json(b"{}")
        return Reply.raw_json(self.external.facts(artist, title, request.param("aid"), request.param("album")))


class CacheController:
    def __init__(self, cache, covers, library, watcher):
        self.cache = cache
        self.covers = covers
        self.library = library
        self.watcher = watcher

    def refresh_album(self, request):
        """Rafraîchit un seul album ou artiste (la pochette est rechargée : l'interface change l'adresse)."""
        album, artist = request.param("album"), request.param("artist")

        def stale(meta):
            wanted = (meta["ep"] == "getAlbum" and meta["q"].get("id") == album) or \
                     (meta["ep"] == "getArtist" and meta["q"].get("id") == artist)
            return wanted
        self.cache.invalidate(stale)
        return Reply.json({"ok": True})

    def clear(self, request):
        if request.param("all"):
            self.cache.clear()          # tout, pochettes, bios et paroles compris
            self.covers.clear()
        else:
            self.library.refresh()
            in_background(self.watcher.check_new, True)
        return Reply.json({"ok": True})
