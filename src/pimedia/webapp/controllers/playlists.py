"""Playlists Subsonic de la personne connectée, celles des autres rendues publiques (lecture) ou communautaires (ajout)."""
from ..playlists import PlaylistError
from .base import ok
from .library import item_id

MAX_SONGS = 500
MAX_ORDER = 5000                     # une playlist peut être bien plus longue que ce qu'on y ajoute d'un coup


def song_ids(value):
    if not isinstance(value, list) or len(value) > MAX_SONGS:
        raise PlaylistError("request.invalid")
    return [item_id(s) for s in value]


def ext_items(value):
    if not isinstance(value, list) or not value or len(value) > MAX_SONGS:
        raise PlaylistError("request.invalid")
    return value


def row_ids(value):
    if not isinstance(value, list) or len(value) > MAX_SONGS or not all(
            isinstance(r, int) and not isinstance(r, bool) and r > 0 for r in value):
        raise PlaylistError("request.invalid")
    return value


def positions(value):
    if not isinstance(value, list) or len(value) > MAX_SONGS or not all(
            isinstance(p, int) and not isinstance(p, bool) and p >= 0 for p in value):
        raise PlaylistError("request.invalid")
    return value


def order(value):
    """[{"position": rang chez Subsonic} | {"extId": ligne d'un titre d'ailleurs}]."""
    def valid(item):
        if not isinstance(item, dict) or len(item) != 1:
            return False
        (key, n), = item.items()
        return key in ("position", "extId") and isinstance(n, int) and not isinstance(n, bool) and n >= (key == "extId")
    if not isinstance(value, list) or len(value) > MAX_ORDER or not all(valid(i) for i in value):
        raise PlaylistError("request.invalid")
    return value


class PlaylistController:
    def __init__(self, playlists):
        self.playlists = playlists

    def all(self, request, user):
        return ok({"playlists": self.playlists.all(user)})

    def get(self, request, user):
        return ok(self.playlists.get(user, item_id(request.param("id"))))

    def create(self, request, user, body):
        community = body.get("community", False)
        if not isinstance(community, bool):
            raise PlaylistError("request.invalid")
        return ok({"playlist": self.playlists.create(user, body.get("name"), song_ids(body.get("songIds", [])),
                                                     community)})

    def community(self, request, user, body):
        if not isinstance(body.get("on"), bool):
            raise PlaylistError("request.invalid")
        self.playlists.set_community(user, item_id(body.get("id")), body["on"])
        return ok()

    def add(self, request, user, body):
        return ok({"added": self.playlists.add(user, item_id(body.get("id")), song_ids(body.get("songIds")))})

    def add_ext(self, request, user, body):
        """{id, items: titres d'ailleurs au format de la page}."""
        return ok({"added": self.playlists.add_ext(user, item_id(body.get("id")), ext_items(body.get("items")))})

    def remove_ext(self, request, user, body):
        """{id, extIds: lignes des titres d'ailleurs}."""
        self.playlists.remove_ext(user, item_id(body.get("id")), row_ids(body.get("extIds")))
        return ok()

    def remove(self, request, user, body):
        self.playlists.remove_positions(user, item_id(body.get("id")), positions(body.get("positions")))
        return ok()

    def reorder(self, request, user, body):
        """{id, order: tous les titres, dans le nouvel ordre}."""
        self.playlists.reorder(user, item_id(body.get("id")), order(body.get("order")))
        return ok()

    def rename(self, request, user, body):
        self.playlists.rename(user, item_id(body.get("id")), body.get("name"))
        return ok()

    def delete(self, request, user, body):
        self.playlists.delete(user, item_id(body.get("id")))
        return ok()
