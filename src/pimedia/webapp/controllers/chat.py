"""Salon global et commentaires d'albums ; flux d'événements temps réel."""
from ..events import EventStreamReply
from .base import int_param, ok


def number(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class ChatController:
    def __init__(self, chat, hub):
        self.chat = chat
        self.hub = hub

    def history(self, request, user):
        return ok(self.chat.history(user, request.param("topic", "general"), int_param(request, "before"),
                                    int_param(request, "after"), int_param(request, "limit") or 50))

    def search(self, request, user):
        return ok({"messages": self.chat.search(user, request.param("topic", "general"), request.param("q"))})

    def mentions(self, request, user):
        return ok({"messages": self.chat.mentions(user)})

    def online(self, request, user):
        return ok({"online": self.hub.online()})

    def post(self, request, user, body):
        message = self.chat.post(user, body.get("topic"), body.get("body"), number(body.get("replyTo")),
                                 body.get("attachment"))
        return ok({"message": message.to_api()})

    def edit(self, request, user, body):
        return ok({"message": self.chat.edit(user, number(body.get("id")), body.get("body")).to_api()})

    def delete(self, request, user, body):
        return ok({"message": self.chat.delete(user, number(body.get("id"))).to_api()})

    def react(self, request, user, body):
        return ok({"message": self.chat.react(user, number(body.get("id")), body.get("emoji")).to_api()})

    def typing(self, request, user, body):
        return ok({"sent": self.chat.typing(user, body.get("topic"))})

    def read(self, request, user, body):
        return ok({"unread": self.chat.mark_read(user, body.get("topic"), number(body.get("id")))})

    def events(self, request, user):
        request.set_timeout(None)
        return EventStreamReply(self.hub, user)
