"""Paroles du titre en cours (affichées à droite, à la place du salon)."""
from .base import ok


class LyricsController:
    def __init__(self, lyrics):
        self.lyrics = lyrics

    def find(self, request, user):
        duration = request.param("duration", "0")
        return ok(self.lyrics.find(request.param("artist"), request.param("title"), request.param("album"),
                                   float(duration) if duration.replace(".", "", 1).isdigit() else 0))
