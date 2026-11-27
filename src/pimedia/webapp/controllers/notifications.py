"""Routes des notifications, session et CSRF gérés par Guard."""
from .base import get, int_param, ok, post


class NotificationController:
    def __init__(self, notifications):
        self.notifications = notifications

    def page(self, request, user):
        return ok(self.notifications.page(user, int_param(request, "before", strict=True)).to_api())

    def status(self, request, user):
        return ok(self.notifications.status(user).to_api())

    def recipients(self, request, user):
        return ok(dict(usernames=self.notifications.recipients(user)))

    def send(self, request, user, body):
        return ok(self.notifications.send(user, body.get("recipient"), body.get("title"), body.get("body"),
                                          body.get("requestId")).to_api())

    def mark_read(self, request, user, body):
        return ok(self.notifications.mark_read(user, body.get("id")).to_api())

    def routes(self):
        return [
            get("/api/notifications", self.page),
            get("/api/notifications/recipients", self.recipients, right="admin"),
            get("/api/notifications/status", self.status),
            post("/api/notifications/read", self.mark_read),
            post("/api/notifications/send", self.send, right="admin"),
        ]
