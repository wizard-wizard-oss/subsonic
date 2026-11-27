"""Envoi administratif et consultation privée des notifications de service."""
import re
import time

from .controllers.base import MissingRight
from .notification_entities import BODY_MAX_LENGTH, PAGE_SIZE, TITLE_MAX_LENGTH, NotificationError


class Notifications:
    def __init__(self, repository, users, hub, clock=time.time):
        self.repository, self.users, self.hub, self.clock = repository, users, hub, clock

    @staticmethod
    def check_admin(user):
        if not user.can("admin"):
            raise MissingRight("admin")

    def recipients(self, user):
        self.check_admin(user)
        return self.users.usernames()

    @staticmethod
    def _text(value, maximum):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum or "\x00" in value:
            raise NotificationError("notifications.invalid_message")
        return value.strip()

    def send(self, sender, recipient_name, title, body, request_id):
        self.check_admin(sender)
        title = self._text(title, TITLE_MAX_LENGTH)
        body = self._text(body, BODY_MAX_LENGTH)
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", request_id):
            raise NotificationError("notifications.invalid_request")
        if not isinstance(recipient_name, str) or not 1 <= len(recipient_name) <= 200:
            raise NotificationError("notifications.unknown_recipient")
        recipient = self.users.by_name(recipient_name)
        if recipient is None:
            raise NotificationError("notifications.unknown_recipient")
        delivery = self.repository.add(sender.id, recipient.id, title, body, request_id, int(self.clock()))
        if (delivery.notification.title, delivery.notification.body) != (title, body):
            raise NotificationError("notifications.request_conflict")
        if delivery.created:
            self.hub.publish("notifications", {}, to_user_id=recipient.id)
        return delivery.notification

    def page(self, user, before=None):
        if before is not None and (type(before) is not int or not 0 < before < 2 ** 63):
            raise NotificationError("notifications.invalid_request")
        entries = self.repository.page(user.id, before, PAGE_SIZE + 1)
        return dict(entries=[entry.to_api() for entry in entries[:PAGE_SIZE]],
                    before=entries[PAGE_SIZE - 1].id if len(entries) > PAGE_SIZE else None,
                    unread=self.repository.unread(user.id),
                    limits=dict(title=TITLE_MAX_LENGTH, body=BODY_MAX_LENGTH))

    def status(self, user):
        return dict(unread=self.repository.unread(user.id))

    def mark_read(self, user, identity):
        if type(identity) is not int or not 0 < identity < 2 ** 63:
            raise NotificationError("notifications.invalid_request")
        self.repository.mark_read(user.id, identity, int(self.clock()))
        self.hub.publish("notifications", {}, to_user_id=user.id)
        return self.status(user)
