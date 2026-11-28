"""Adaptation HTTP du catalogue visuel des playlists."""
from .base import get, int_param, ok


class PlaylistGalleryController:
    def __init__(self, gallery):
        self.gallery = gallery

    def page(self, request, user):
        return ok(self.gallery.page(user, int_param(request, "page", strict=True),
                                    request.param("q"), request.param("sort")).to_api())

    def routes(self):
        return [get("/api/playlists/page", self.page)]
