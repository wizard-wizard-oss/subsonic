"""Musique d'ailleurs : sources disponibles, recherche, vidéo refusée et autre version, favoris de chacun."""
from .base import ok


class ExtMusicController:
    def __init__(self, extmusic, favorites):
        self.extmusic, self.favorites = extmusic, favorites

    def status(self, request, user):
        return ok(self.extmusic.status())

    def search(self, request, user):
        return ok({"items": self.extmusic.search(user, request.param("src"), request.param("q"))})

    def known(self, request, user):
        return ok({"items": self.extmusic.known(request.param("q"))})

    def alternative(self, request, user, body):
        return ok({"item": self.extmusic.alternative(user, body.get("id"), body.get("title"), body.get("artist"),
                                                     body.get("code", ""))})

    def unplayable(self, request, user, body):
        self.extmusic.mark_unplayable(body.get("id"), body.get("code", ""))
        return ok()

    def played(self, request, user, body):
        self.extmusic.mark_played(body.get("id"))
        return ok()

    def favorite_list(self, request, user):
        return ok({"items": self.favorites.all(user)})

    def favorite(self, request, user, body):
        """{item: titre d'ailleurs au format de la page, on: true|false} : le cœur."""
        self.favorites.set(user, body.get("item"), body.get("on"))
        return ok()

    def add_link(self, request, user, body):
        """{link} : vidéo ou playlist YouTube, titre SoundCloud."""
        return ok(self.favorites.add_link(user, body.get("link")))
