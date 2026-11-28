"""Actualité : articles des flux suivis, ceux qui parlent d'un artiste, ajout et retrait d'un flux."""
from .base import get, int_param, ok, post
from ...server.transport import Reply
from ...shared.providers.feeds import IMAGE_CACHE_SECONDS


class NewsController:
    def __init__(self, news):
        self.news = news

    def latest(self, request, user):
        """?feed=<id> pour un seul flux ; ?beforeDate=&beforeId= : la suite (« Afficher plus »)."""
        date, last = int_param(request, "beforeDate"), int_param(request, "beforeId")
        return ok(self.news.latest(user, int_param(request, "feed"), (date, last) if date is not None and last else None).to_api())

    def feeds(self, request, user):
        return ok(self.news.feeds(user).to_api())

    def about(self, request, user):
        return ok(self.news.about(user, request.param("name")).to_api())

    def add(self, request, user, body):
        return ok({"feed": self.news.add(user, body.get("address")).to_api()})

    def image(self, request, user):
        image = self.news.image(user, int_param(request, "id", strict=True))
        return (Reply(200, image.data, image.mime, {"Cache-Control": "private, max-age=%d" % IMAGE_CACHE_SECONDS})
                if image else Reply.not_found())

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

    def routes(self):
        return [
            get("/api/news", self.latest),
            get("/api/news/artist", self.about),
            get("/api/news/feeds", self.feeds),
            get("/api/news/image", self.image),
            post("/api/news/feed/add", self.add),
            post("/api/news/feed/remove", self.remove),
            post("/api/news/feed/show", self.show),
        ]
