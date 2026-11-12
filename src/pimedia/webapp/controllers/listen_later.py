"""HTTP endpoints for listening bookmarks and recommendations."""
from .base import ok
from ..recommendations import READ_BATCH_SIZE


class ListenLaterController:
    def __init__(self, bookmarks, recommendations):
        self.bookmarks, self.recommendations = bookmarks, recommendations

    def all(self, request, user):
        return ok(dict(bookmarks=[entry.to_api() for entry in self.bookmarks.all(user)],
                       recommendations=[group.to_api() for group in self.recommendations.received(user)],
                       readBatchSize=READ_BATCH_SIZE))

    def add(self, request, user, body):
        entry = self.bookmarks.add(user, body.get("kind"), body.get("source"), body.get("sourceId"))
        return ok(dict(bookmark=entry.to_api()))

    def remove(self, request, user, body):
        return ok(dict(removed=self.bookmarks.remove(user, body.get("id"))))

    def recommend(self, request, user, body):
        entry = self.recommendations.send(user, body.get("recipient"), body.get("kind"),
                                          body.get("source"), body.get("sourceId"))
        return ok(dict(recommendation=entry.to_api()))

    def dismiss(self, request, user, body):
        return ok(dict(removed=self.recommendations.remove(user, body.get("kind"),
                                                               body.get("source"), body.get("sourceId"))))

    def status(self, request, user):
        return ok(dict(unread=self.recommendations.has_unread(user)))

    def mark_read(self, request, user, body):
        return ok(dict(unread=self.recommendations.mark_read(user, body.get("tokens"))))
