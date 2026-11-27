"""Changer la pochette d'un album (droit Subsonic « upload ») : recherche Last.fm, puis écriture dans le dossier de l'album."""
from .base import get, ok, post
from .library import item_id


class CoverController:
    def __init__(self, covers):
        self.covers = covers

    def status(self, request, user):
        return ok(self.covers.status())

    def search(self, request, user):
        return ok({"covers": self.covers.search(request.param("artist"), request.param("album"))})

    def save(self, request, user, body):
        url = body.get("url")
        if not isinstance(url, str) or not 0 < len(url) <= 2000:
            raise ValueError("url")
        return ok(self.covers.save(user, item_id(body.get("albumId")), url.strip()))

    def routes(self):
        return [
            get("/api/cover/search", self.search, right="upload"),
            get("/api/cover/status", self.status, right="upload"),
            post("/api/cover/save", self.save, right="upload"),
        ]
