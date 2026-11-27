"""HTTP endpoints for listening bookmarks and recommendations."""
from .base import int_param, ok
from ..recommendations.service import READ_BATCH_SIZE
from ..recommendations.entities import COMMENT_MAX_LENGTH


class ListenLaterController:
    def __init__(self, bookmarks, recommendations):
        self.bookmarks, self.recommendations = bookmarks, recommendations

    def all(self, request, user):
        received = self.recommendations.received(user)
        return ok(dict(bookmarks=[entry.to_api() for entry in self.bookmarks.all(user)],
                       recommendations=[group.to_api() for group in received.groups],
                       recommendationsHaveMore=received.has_more,
                       readBatchSize=READ_BATCH_SIZE, commentMaxLength=COMMENT_MAX_LENGTH))

    def add(self, request, user, body):
        entry = self.bookmarks.add(user, body.get("kind"), body.get("source"), body.get("sourceId"))
        return ok(dict(bookmark=entry.to_api()))

    def remove(self, request, user, body):
        return ok(dict(removed=self.bookmarks.remove(user, body.get("id"))))

    def recommend(self, request, user, body):
        entry = self.recommendations.send(user, body.get("recipient"), body.get("kind"),
                                          body.get("source"), body.get("sourceId"), body.get("comment", ""))
        return ok(entry.to_api())

    def dismiss(self, request, user, body):
        return ok(dict(removed=self.recommendations.archive(user, body.get("kind"),
                                                               body.get("source"), body.get("sourceId"))))

    def status(self, request, user):
        return ok(self.recommendations.status(user).to_api())

    def mark_read(self, request, user, body):
        return ok(dict(unread=self.recommendations.mark_read(user, body.get("ids"))))

    def discussions(self, request, user):
        return ok(self.recommendations.discussions(user, request.param("scope", "sent"),
                                                   int_param(request, "before", strict=True)).to_api())

    def discussion(self, request, user):
        return ok(self.recommendations.discussion(user, int_param(request, "id", strict=True),
                                                  int_param(request, "before", strict=True), int_param(request, "after", strict=True)).to_api())

    def comment(self, request, user, body):
        comment = self.recommendations.comment(user, body.get("recommendationId"), body.get("body"),
                                               body.get("requestId"))
        return ok(dict(comment=comment.to_api()))

    def read_comments(self, request, user, body):
        return ok(dict(unread=self.recommendations.mark_comments_read(user, body.get("recommendationId"),
                                                                      body.get("commentId"))))
