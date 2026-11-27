"""HTTP des sorties de la semaine : consultation par style (hors de la période synchronisée) et radar personnel."""
from .base import get, int_param, ok, post


class WeeklyReleasesController:
    def __init__(self, releases, radar=None):
        self.releases, self.radar_service = releases, radar

    # ---------- un style à la fois ----------
    def genres(self, request, user):
        return ok({"genres": [g.to_api() for g in self.releases.genres()],
                   "followed": [g.name for g in self.releases.followed(user)], "default": self.releases.DEFAULT_GENRE})

    def week(self, request, user):
        page = self.releases.week(request.param("genre"), request.param("monday"),
                                  int_param(request, "offset", strict=True) or 0)
        return ok(page.to_api())

    def follow(self, request, user, body):
        self.releases.follow(user, body.get("genre"), body.get("enabled"))
        return ok()

    # ---------- radar ----------
    def radar(self, request, user):
        return ok(self.radar_service.week(user, request.param("monday"), request.param("filter") or "all",
                                          int_param(request, "offset", strict=True) or 0).to_api())

    def sources(self, request, user):
        return ok(self.radar_service.settings(user).to_api())

    def add_source(self, request, user, body):
        return ok(self.radar_service.add_source(user, body.get("kind"), body.get("identity"),
                                                body.get("name")).to_api())

    def hide_source(self, request, user, body):
        self.radar_service.hide_source(user, body.get("id"))
        return ok()

    def discoveries(self, request, user, body):
        self.radar_service.set_discoveries(user, body.get("enabled"))
        return ok()

    def search(self, request, user):
        return ok(self.radar_service.search(request.param("kind"), request.param("q")).to_api())

    def refresh(self, request, user, body):
        return ok(self.radar_service.refresh(user).to_api())

    def routes(self):
        return [
            get("/api/news/releases", self.week),
            get("/api/news/releases/genres", self.genres),
            post("/api/news/releases/follow", self.follow),
            get("/api/news/releases/radar", self.radar),
            get("/api/news/releases/sources", self.sources),
            post("/api/news/releases/sources/add", self.add_source),
            post("/api/news/releases/sources/hide", self.hide_source),
            post("/api/news/releases/discoveries", self.discoveries),
            get("/api/news/releases/search", self.search),
            post("/api/news/releases/refresh", self.refresh),
        ]
