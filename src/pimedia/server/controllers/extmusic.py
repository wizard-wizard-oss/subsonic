"""Interface de programmation de la musique d'ailleurs et des playlists locales."""
from ..podcasts.directories import DirectoryError
from ...entities import Track
from ..transport import Reply

CSRF_VALUE = "pm"


def _refusal(message, status=400):
    return Reply.json({"error": message}, status)


def tracks_from(raw):
    """Liste de titres envoyée par la page -> entités Track (ValueError si la liste ou un titre est invalide)."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("liste de titres attendue")
    return [Track.from_api(t) for t in raw]


class ExtMusicController:
    def __init__(self, service):
        self.service = service

    # ---------- lecture ----------
    def status(self, request):
        return Reply.json(self.service.status())

    def search(self, request):
        try:
            return Reply.json(self.service.search(request.param("src"), request.param("q")))
        except DirectoryError as error:
            return _refusal(str(error), 502)

    def playlists(self, request):
        return Reply.json({"lists": [p.to_api() for p in self.service.playlists.overview()]})

    def alternative(self, request):
        try:
            found = self.service.alternative(request.param("id"), request.param("title"), request.param("artist"))
        except DirectoryError as error:
            return _refusal(str(error), 502)
        return Reply.json({"item": found})

    def favorites(self, request):
        return Reply.json({"songs": [t.to_api() for t in self.service.playlists.favorites()]})

    def playlist(self, request):
        try:
            return Reply.json(self.service.playlists.get(request.param("id")).to_api())
        except KeyError as error:
            return _refusal(error.args[0], 404)

    # ---------- écriture (POST JSON + en-tête anti-CSRF) ----------
    def settings(self, request):
        if not request.is_local:
            return _refusal("Réservé à l’écran du Pi", 403)
        return self._write(request, self.service.update)

    def unplayable(self, request):
        """Le lecteur intégré a refusé cette vidéo : elle ne sera plus proposée."""
        return self._write(request, lambda b: self.service.mark_unplayable(b.get("id")))

    def favorite(self, request):
        return self._write(request, lambda b: {"starred": self.service.playlists.toggle_favorite(Track.from_api(b.get("song")))})

    def create(self, request):
        return self._write(request, lambda b: {"id": self.service.playlists.create(b.get("name"), tracks_from(b.get("songs")))})

    def add(self, request):
        return self._write(request, lambda b: {"added": self.service.playlists.add(b.get("id", ""), tracks_from(b.get("songs")))})

    def remove(self, request):
        return self._write(request, lambda b: self.service.playlists.remove(b.get("id", ""), int(b.get("index", -1))))

    def delete(self, request):
        return self._write(request, lambda b: self.service.playlists.delete(b.get("id", "")))

    def _write(self, request, action):
        if request.header("X-Requested-With") != CSRF_VALUE:
            return _refusal("refus", 403)
        try:
            result = action(request.json_body(limit=262144)) or {}
        except KeyError as error:
            return _refusal(error.args[0], 404)
        except (ValueError, TypeError) as error:
            return _refusal(str(error))
        return Reply.json(dict(result, ok=True, status=self.service.status()))
