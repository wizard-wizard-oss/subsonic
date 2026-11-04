"""Actualité : articles des flux suivis, ceux qui parlent d'un artiste, ajout et retrait d'un flux."""
from .base import int_param, ok


class NewsController:
    def __init__(self, news):
        self.news = news

    def latest(self, request, user):
        """?feed=<id> pour un seul flux ; ?beforeDate=&beforeId= : la suite (« Afficher plus »)."""
        date, last = int_param(request, "beforeDate"), int_param(request, "beforeId")
        return ok(self.news.latest(user, int_param(request, "feed"), (date, last) if date is not None and last else None))

    def feeds(self, request, user):
        return ok({"feeds": self.news.feeds(user)})

    def about(self, request, user):
        return ok({"articles": self.news.about(user, request.param("name"))})

    def add(self, request, user, body):
        return ok({"feed": self.news.add(user, body.get("address"))})

    def show(self, request, user, body):
        """{id, shown} : afficher ou masquer un flux pour soi."""
        feed_id, shown = body.get("id"), body.get("shown")
        if not isinstance(feed_id, int) or not isinstance(shown, bool):
            raise ValueError(feed_id)
        self.news.show(user, feed_id, shown)
        return ok()

    def remove(self, request, user, body):
        feed_id = body.get("id")
        if not isinstance(feed_id, int):
            raise ValueError(feed_id)
        self.news.remove(user, feed_id)
        return ok()
