"""Page et interface de programmation des podcasts."""
from ..podcasts.directories import DirectoryError
from ..podcasts.feeds import FeedError
from ..transport import Reply

CSRF_VALUE = "pm"


def _refusal(message, status=502):
    return Reply.json({"error": message}, status)


class PodcastController:
    def __init__(self, config, service, pages):
        self.config = config
        self.service = service
        self.pages = pages

    # ---------- lecture ----------
    def page(self, request):
        return self.pages.page("podcasts.html", request)

    def status(self, request):
        return Reply.json(self.service.status())

    def home(self, request):
        return self._answer(self.service.home)

    def theme(self, request):
        return self._answer(self.service.theme, request.param("id"))

    def search(self, request):
        return self._answer(self.service.search, request.param("q"))

    def show(self, request):
        return self._answer(self.service.show, request.param("feed"))

    def similar(self, request):
        return self._answer(self.service.similar, request.param("feed"), request.param("genre"), request.param("title"))

    def library(self, request):
        return self._answer(self.service.library_view)

    def _answer(self, action, *args):
        try:
            return Reply.json(action(*args))
        except (FeedError, DirectoryError) as error:
            return _refusal(str(error))

    # ---------- écriture (POST JSON, avec l'en-tête anti-CSRF) ----------
    def subscribe(self, request):
        return self._write(request, lambda b: self.service.subscribe(
            b.get("feed", ""), b.get("title", ""), b.get("image", ""), b.get("author", "")))

    def unsubscribe(self, request):
        return self._write(request, lambda b: self.service.unsubscribe(b.get("feed", "")))

    def hide(self, request):
        return self._write(request, lambda b: self.service.hide(b.get("feed", "")))

    def progress(self, request):
        return self._write(request, self.service.save_progress)

    def played(self, request):
        return self._write(request, lambda b: self.service.mark_played(b.get("id", ""), bool(b.get("played", True))))

    def language(self, request):
        return self._write(request, lambda b: self.service.set_french_only(b.get("french", True)))

    def forget(self, request):
        return self._write(request, lambda b: self.service.forget(str(b.get("id", ""))))

    def save_key(self, request):
        """Clé Podcast Index saisie dans la page (depuis l'écran du Pi seulement). Vide = désactiver."""
        if not request.is_local:
            return _refusal("Réservé à l'écran du Pi", 403)

        def store(body):
            self.config.update(podcastindex_key=str(body.get("key", "")).strip(),
                               podcastindex_secret=str(body.get("secret", "")).strip())
        return self._write(request, store)

    def _write(self, request, action):
        if request.header("X-Requested-With") != CSRF_VALUE:
            return _refusal("refus", 403)
        try:
            action(request.json_body(limit=16384))
        except (FeedError, ValueError, KeyError) as error:
            return _refusal(str(error), 400)
        status = self.service.status()
        return Reply.json({"ok": True, "sources": status["sources"], "french": status["french"]})
