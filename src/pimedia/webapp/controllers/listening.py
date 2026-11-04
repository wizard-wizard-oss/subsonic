"""Écoute : scrobble, en écoute maintenant, marque-pages, file d'attente partagée avec les applis."""
from .base import ok
from .library import item_id
from .playlists import song_ids


def seconds(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value < 100 * 3600:
        raise ValueError("position")
    return value


class ListeningController:
    def __init__(self, listening):
        self.listening = listening

    def scrobble(self, request, user, body):
        self.listening.scrobble(user, item_id(body.get("id")), body.get("submission") is True)
        return ok()

    def now_playing(self, request, user):
        return ok({"entries": self.listening.now_playing(user)})

    def bookmarks(self, request, user):
        return ok({"bookmarks": self.listening.bookmarks(user)})

    def save_bookmark(self, request, user, body):
        self.listening.save_bookmark(user, item_id(body.get("id")), seconds(body.get("position")), body.get("comment", ""))
        return ok()

    def delete_bookmark(self, request, user, body):
        self.listening.delete_bookmark(user, item_id(body.get("id")))
        return ok()

    def play_queue(self, request, user):
        return ok(self.listening.play_queue(user))

    def save_play_queue(self, request, user, body):
        current = body.get("current")
        self.listening.save_play_queue(user, song_ids(body.get("ids")), item_id(current) if current else "",
                                       seconds(body.get("position", 0)))
        return ok()
