"""HTTP de l’accueil personnel et des écoutes confirmées du site."""
from .base import get, int_param, ok, post
from .library import item_id


class PersonalHomeController:
    def __init__(self, home, history):
        self.home, self.history = home, history

    def page(self, request, user):
        return ok(self.home.page(user, int_param(request, "before", strict=True)).to_api())

    def record(self, request, user, body):
        return ok(self.history.record(user, item_id(body.get("id")), body.get("requestId")).to_api())

    def routes(self):
        return [get("/api/home/personal", self.page),
                post("/api/listening/history", self.record, right="stream")]
