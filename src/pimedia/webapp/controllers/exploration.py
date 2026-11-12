"""Exploration : lecture seulement, session obligatoire, paramètres validés avant l'accès aux sources."""
from .base import ok
from .library import item_id
from ..exploration import mbid


class ExplorationController:
    def __init__(self, exploration):
        self.exploration = exploration

    def album(self, request, user):
        release = request.param("release")
        if release:
            mbid(release)
        return ok(self.exploration.album(user, item_id(request.param("id")), release).to_api())

    def profile(self, request, user):
        offset = int(request.param("offset") or 0)
        return ok(self.exploration.profile(request.param("kind"), request.param("id"), offset).to_api())

    def artists(self, request, user):
        return ok(self.exploration.artists(request.param("name")).to_api())

    def connections(self, request, user):
        return ok(self.exploration.connections(request.param("id")).to_api())

    def local(self, request, user):
        return ok(self.exploration.local(user, request.param("title"), request.param("artist")))
