"""Biographie de l'artiste (page artiste) et anecdotes du titre en cours (panneau des paroles)."""
from .base import ok
from .library import item_id
from .library import item_id


def optional_id(value):
    return item_id(value) if value else ""


class FactsController:
    def __init__(self, facts, portraits):
        self.facts = facts
        self.portraits = portraits

    def artist_image(self, request, user):
        return ok(self.portraits.get(user, item_id(request.param("id"))).to_api())

    def artist_bio(self, request, user):
        return ok(self.facts.artist_bio(user, request.param("name"), optional_id(request.param("id"))))

    def song_facts(self, request, user):
        return ok(self.facts.song_facts(user, request.param("artist"), request.param("title"),
                                        optional_id(request.param("artistId")), request.param("album")))
