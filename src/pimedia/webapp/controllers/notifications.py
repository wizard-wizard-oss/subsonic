"""Routes des notifications, session et CSRF gérés par Guard."""
from .base import int_param, ok


class NotificationController:
    def __init__(self, notifications):
        self.notifications = notifications

    def page(self, request, user):
        return ok(self.notifications.page(user, int_param(request, "before", strict=True)))

    def status(self, request, user):
        return ok(self.notifications.status(user))

    def recipients(self, request, user):
        return ok(dict(usernames=self.notifications.recipients(user)))

    def send(self, request, user, body):
        return ok(self.notifications.send(user, body.get("recipient"), body.get("title"), body.get("body"),
                                          body.get("requestId")).to_api())

    def mark_read(self, request, user, body):
        return ok(self.notifications.mark_read(user, body.get("id")))
