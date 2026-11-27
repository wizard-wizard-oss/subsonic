"""HTTP pour la consultation par semaine et les abonnements."""
from .base import get, int_param, ok, post


class WeeklyReleasesController:
    def __init__(self, releases):
        self.releases = releases

    def genres(self, request, user):
        return ok({"genres": [g.to_api() for g in self.releases.genres()],
                   "followed": [g.name for g in self.releases.followed(user)]})

    def week(self, request, user):
        page = self.releases.week(request.param("genre"), request.param("monday"),
                                  int_param(request, "offset", strict=True) or 0)
        return ok(page.to_api())

    def follow(self, request, user, body):
        self.releases.follow(user, body.get("genre"), body.get("enabled"))
        return ok()

    def routes(self):
        return [
            get("/api/news/releases", self.week),
            get("/api/news/releases/genres", self.genres),
            post("/api/news/releases/follow", self.follow),
        ]
