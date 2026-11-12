"""Discogs : session et paramètres HTTP, sans règle de catalogue ni de sélection."""
from .base import ok
from .library import item_id
from ..entities import ImportedTrack


class DiscogsController:
    def __init__(self, discogs, catalogs, discovery, exploration, artist_links):
        self.discogs, self.catalogs, self.discovery = discogs, catalogs, discovery
        self.exploration = exploration
        self.artist_links = artist_links

    def artist_link(self, request, user):
        link = self.artist_links.get(user, item_id(request.param("id")))
        return ok({"link": link.to_api() if link else None})

    def choose_artist(self, request, user, body):
        return ok(self.artist_links.choose(user, item_id(body.get("artistId")), body.get("discogsArtistId")).to_api())

    def refresh_artist(self, request, user, body):
        return ok(self.artist_links.refresh(user, item_id(body.get("artistId"))).to_api())

    def status(self, request, user):
        return ok(self.discovery.status())

    def search(self, request, user):
        return ok(self.discogs.search(request.param("kind"), request.param("name")).to_api())

    def identity(self, request, user):
        if request.param("kind") == "artist":
            return ok(self.discogs.artist(request.param("id")).to_api())
        if request.param("kind") == "label":
            return ok(self.discogs.label(request.param("id")).to_api())
        raise ValueError("kind")

    def album(self, request, user):
        return ok(self.exploration.album(user, item_id(request.param("id")), request.param("release")).to_api())

    def catalog(self, request, user):
        return ok(self.catalogs.page(request.param("kind"), request.param("id"),
                                     int(request.param("page") or 1)).to_api())

    def discover(self, request, user):
        return ok({"albums": [a.to_api() for a in self.discovery.discover(request.param("id"))]})

    def ranking(self, request, user):
        return ok(self.discovery.ranking(request.param("id"), request.param("source"),
                                         int(request.param("offset") or 0)).to_api())

    def tracks(self, request, user):
        return ok(self.discovery.tracks(user, request.param("id"), request.param("album"), request.param("mode")).to_api())

    def versions(self, request, user, body):
        return ok(self.discovery.versions(user, body.get("release"), ImportedTrack.from_api(body.get("track"))).to_api())
