"""Mix et radios (titres calculés par le serveur à partir de Subsonic et de Last.fm, les mêmes pour tous)."""
from ..mixes import MixError, MixOptions
from .base import ok
from .library import item_id

SIMPLE_MIXES = ("random", "favorites", "discover", "newest")


def songs_or_error(songs):
    if not songs:
        raise MixError("mix.empty")
    return ok({"songs": songs})


class MixController:
    def __init__(self, mixes):
        self.mixes = mixes

    def simple(self, request, user):
        """Mix aléatoire (éventuellement d'un style), favoris, découverte (albums au hasard), derniers ajouts."""
        kind = request.param("kind", "random")
        if kind not in SIMPLE_MIXES:
            raise MixError("mix.invalid")
        if kind == "random":
            return songs_or_error(self.mixes.random_mix(user, request.param("genre")[:60]))
        if kind == "favorites":
            return songs_or_error(self.mixes.favorites_mix(user))
        return songs_or_error(self.mixes.albums_mix(user, "random" if kind == "discover" else "newest", 5))

    def song_radio(self, request, user):
        return songs_or_error(self.mixes.song_radio(user, item_id(request.param("id"))))

    def artist_radio(self, request, user):
        return songs_or_error(self.mixes.artist_radio(user, item_id(request.param("id")), request.param("name")[:200]))

    def genres(self, request, user):
        return ok({"genres": [g.to_api() for g in self.mixes.genre_groups(user)], "options": MixOptions.choices()})

    def build(self, request, user, body):
        options = MixOptions.parse(body)
        songs = self.mixes.build(user, options)
        if not songs:
            raise MixError("mix.empty")
        return ok({"songs": songs, "name": self.mixes.mix_name(user, options)})
